"""Bounded, deterministic, unsigned portable evidence capsules.

An archive digest protects against accidental corruption. Authenticity requires a
trusted external root anchor or signature; this local format does not supply one.
"""

import errno
import json
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from sentinel_replay.canonical import CanonicalizationError, load_json_unique
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import Verification, verify_journal_bytes

MAX_ENTRIES = 64
MAX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


class CapsuleError(ValueError):
    """Capsule structure or evidence failed validation."""


@dataclass(frozen=True)
class CapsuleVerification:
    run_id: str
    records: int
    root: str
    artifacts: int


def _json(data: object) -> bytes:
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _safe_name(name: str) -> None:
    if not _NAME.fullmatch(name) or name in {".", ".."}:
        raise CapsuleError(f"invalid capsule name: {name}")


def _manifest(run_id: str, verified: Verification, entries: dict[str, bytes]) -> bytes:
    return _json(
        {
            "schema_version": 1,
            "integrity": "hash-chain-and-digests;unsigned",
            "run_id": run_id,
            "journal": {"records": verified.records, "root": verified.root},
            "entries": [
                {"path": name, "size": len(data), "digest": blob_digest(data)}
                for name, data in sorted(entries.items())
            ],
        }
    )


def export_capsule(
    run_id: str, journal: Path, destination: Path, artifacts: dict[str, Path] | None = None
) -> CapsuleVerification:
    """Create a deterministic ZIP without overwriting an existing capsule."""
    _safe_name(run_id)
    if destination.exists() or destination.is_symlink():
        raise CapsuleError("capsule destination already exists")
    sources = artifacts or {}
    if len(sources) + 1 > MAX_ENTRIES:
        raise CapsuleError("too many capsule entries")
    entries: dict[str, bytes] = {}
    for name, source in sorted(sources.items()):
        _safe_name(name)
        mode = source.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise CapsuleError(f"artifact must be a regular file: {name}")
        with source.open("rb") as artifact_file:
            data = artifact_file.read(MAX_ENTRY_BYTES + 1)
        if len(data) > MAX_ENTRY_BYTES:
            raise CapsuleError(f"artifact exceeds entry limit: {name}")
        entries[f"artifacts/{name}"] = data
    if not stat.S_ISREG(journal.lstat().st_mode):
        raise CapsuleError("journal must be a regular file")
    with journal.open("rb") as journal_file:
        journal_data = journal_file.read(MAX_ENTRY_BYTES + 1)
    if len(journal_data) > MAX_ENTRY_BYTES:
        raise CapsuleError("journal exceeds entry limit")
    verified = verify_journal_bytes(journal_data)
    entries["journal.jsonl"] = journal_data
    if sum(map(len, entries.values())) > MAX_TOTAL_BYTES:
        raise CapsuleError("capsule exceeds total evidence limit")
    manifest_data = _manifest(run_id, verified, entries)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted({"manifest.json": manifest_data, **entries}.items()):
                info = zipfile.ZipInfo(name, _ZIP_DATE)
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100600 << 16
                archive.writestr(info, data)
        if temp_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise CapsuleError("capsule archive exceeds byte limit")
        with temp_path.open("rb") as archived_file:
            os.fsync(archived_file.fileno())
        os.link(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return CapsuleVerification(run_id, verified.records, verified.root, len(sources))


def _validate_manifest(value: Any) -> tuple[str, Verification, dict[str, tuple[int, str]]]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "integrity",
        "run_id",
        "journal",
        "entries",
    }:
        raise CapsuleError("invalid capsule manifest shape")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise CapsuleError("unsupported capsule schema version")
    if value["integrity"] != "hash-chain-and-digests;unsigned":
        raise CapsuleError("unsupported capsule integrity contract")
    run_id = value["run_id"]
    if not isinstance(run_id, str):
        raise CapsuleError("invalid run ID")
    _safe_name(run_id)
    journal = value["journal"]
    if not isinstance(journal, dict) or set(journal) != {"records", "root"}:
        raise CapsuleError("invalid journal reference")
    if type(journal["records"]) is not int or journal["records"] < 0:
        raise CapsuleError("invalid journal count")
    if not isinstance(journal["root"], str) or not _DIGEST.fullmatch(journal["root"]):
        raise CapsuleError("invalid journal root")
    declared = value["entries"]
    if not isinstance(declared, list) or not 1 <= len(declared) <= MAX_ENTRIES:
        raise CapsuleError("invalid capsule entry list")
    entries: dict[str, tuple[int, str]] = {}
    for entry in declared:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "digest"}:
            raise CapsuleError("invalid capsule entry")
        path, size, digest = entry["path"], entry["size"], entry["digest"]
        if not isinstance(path, str) or not (
            path == "journal.jsonl"
            or (path.startswith("artifacts/") and "/" not in path[len("artifacts/") :])
        ):
            raise CapsuleError("unsafe capsule path")
        if path != "journal.jsonl":
            _safe_name(path.removeprefix("artifacts/"))
        if path in entries or type(size) is not int or not 0 <= size <= MAX_ENTRY_BYTES:
            raise CapsuleError("duplicate entry or invalid size")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise CapsuleError("invalid entry digest")
        entries[path] = (size, digest)
    if "journal.jsonl" not in entries or list(entries) != sorted(entries):
        raise CapsuleError("journal missing or entries not sorted")
    if sum(size for size, _ in entries.values()) > MAX_TOTAL_BYTES:
        raise CapsuleError("capsule exceeds total evidence limit")
    return run_id, Verification(journal["records"], journal["root"]), entries


def read_capsule_bytes(path: Path) -> bytes:
    """Read one bounded regular archive without following its final symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise CapsuleError("capsule must be a regular file") from error
        raise
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CapsuleError("capsule must be a regular file")
        if metadata.st_size > MAX_ARCHIVE_BYTES:
            raise CapsuleError("capsule archive exceeds byte limit")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise CapsuleError("capsule archive exceeds byte limit")
        return data
    finally:
        os.close(descriptor)


def _verified_contents(data: bytes) -> tuple[CapsuleVerification, dict[str, bytes]]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise CapsuleError("capsule archive exceeds byte limit")
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_ENTRIES + 1 or len(names) != len(set(names)):
                raise CapsuleError("too many or duplicate archive entries")
            if "manifest.json" not in names:
                raise CapsuleError("capsule manifest missing")
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if (
                    info.is_dir()
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.flag_bits & 0x1
                    or mode not in {0, stat.S_IFREG}
                    or info.file_size > MAX_ENTRY_BYTES
                    or info.compress_size != info.file_size
                ):
                    raise CapsuleError("unsupported or oversized archive entry")
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES + 1024 * 1024:
                raise CapsuleError("archive exceeds total byte limit")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 1024 * 1024:
                raise CapsuleError("manifest exceeds byte limit")
            manifest_raw = archive.read(manifest_info)
            manifest = load_json_unique(manifest_raw.decode("utf-8"))
            run_id, expected, declared = _validate_manifest(manifest)
            if set(names) != {"manifest.json", *declared}:
                raise CapsuleError("archive entries do not match manifest")
            contents: dict[str, bytes] = {}
            for name, (size, digest) in declared.items():
                data = archive.read(name)
                if len(data) != size or blob_digest(data) != digest:
                    raise CapsuleError(f"entry digest mismatch: {name}")
                contents[name] = data
            actual = verify_journal_bytes(contents["journal.jsonl"])
            if actual != expected:
                raise CapsuleError("journal chain differs from manifest")
            return CapsuleVerification(
                run_id, actual.records, actual.root, len(declared) - 1
            ), contents
    except (zipfile.BadZipFile, UnicodeDecodeError, CanonicalizationError) as error:
        raise CapsuleError(f"invalid capsule archive: {error}") from error


def verify_capsule(path: Path) -> CapsuleVerification:
    """Verify all bytes and the journal chain without extracting a file."""
    return verify_capsule_bytes(read_capsule_bytes(path))


def verify_capsule_bytes(data: bytes) -> CapsuleVerification:
    """Verify the exact bytes that a detached signature will cover."""
    return _verified_contents(data)[0]


def import_capsule(path: Path, destination: Path) -> CapsuleVerification:
    """Preflight the complete archive before creating a new import directory."""
    return import_capsule_bytes(read_capsule_bytes(path), destination)


def import_capsule_bytes(data: bytes, destination: Path) -> CapsuleVerification:
    """Import the same bounded bytes that a caller may have authenticated."""
    result, contents = _verified_contents(data)
    if destination.exists() or destination.is_symlink():
        raise CapsuleError("import destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    for name, data in contents.items():
        target = destination / name
        target.parent.mkdir(mode=0o700, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    (destination / "manifest.json").write_bytes(
        _manifest(result.run_id, Verification(result.records, result.root), contents)
    )
    return result


def verify_imported(destination: Path) -> CapsuleVerification:
    """Recheck imported files before any supported replay consumes their evidence."""
    if destination.is_symlink() or not destination.is_dir():
        raise CapsuleError("import must be a real directory")
    manifest_path = destination / "manifest.json"
    if not stat.S_ISREG(manifest_path.lstat().st_mode):
        raise CapsuleError("imported manifest must be a regular file")
    if manifest_path.stat().st_size > 1024 * 1024:
        raise CapsuleError("imported manifest exceeds byte limit")
    try:
        value = load_json_unique(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, CanonicalizationError) as error:
        raise CapsuleError(f"invalid imported manifest: {error}") from error
    run_id, expected, declared = _validate_manifest(value)
    actual_paths: set[str] = set()
    for count, path in enumerate(destination.rglob("*"), 1):
        if count > MAX_ENTRIES + 2:
            raise CapsuleError("import contains too many paths")
        if path.is_symlink():
            raise CapsuleError("import contains a symlink")
        if path.is_dir():
            if path.relative_to(destination).as_posix() != "artifacts":
                raise CapsuleError("import contains an unexpected directory")
        elif path.is_file():
            actual_paths.add(path.relative_to(destination).as_posix())
        else:
            raise CapsuleError("import contains a special file")
    if actual_paths != {"manifest.json", *declared}:
        raise CapsuleError("imported file set differs from manifest")
    journal_data = b""
    for name, (size, digest) in declared.items():
        with (destination / name).open("rb") as imported_file:
            data = imported_file.read(MAX_ENTRY_BYTES + 1)
        if len(data) != size or blob_digest(data) != digest:
            raise CapsuleError(f"imported entry digest mismatch: {name}")
        if name == "journal.jsonl":
            journal_data = data
    actual = verify_journal_bytes(journal_data)
    if actual != expected:
        raise CapsuleError("imported journal chain differs from manifest")
    return CapsuleVerification(run_id, actual.records, actual.root, len(declared) - 1)
