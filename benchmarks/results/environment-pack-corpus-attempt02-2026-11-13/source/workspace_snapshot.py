"""Bounded regular-file checkpoints; not a general process or Git-state restore."""

import os
import stat
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import event_digest
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore, blob_digest

MAX_FILES = 1_000
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class UnsafeWorkspace(ValueError):
    """The covered path or manifest cannot be safely captured or restored."""


class FileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size: int = Field(ge=0)
    executable: bool


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    coverage: Literal["regular_files_only"] = "regular_files_only"
    entries: tuple[FileEntry, ...]
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _safe_relative(path: str) -> None:
    normalized = PurePosixPath(path)
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or normalized.as_posix() != path
        or any(part in {".", ".."} for part in normalized.parts)
    ):
        raise UnsafeWorkspace(f"unsafe path in workspace manifest: {path}")


def _digest_entries(entries: tuple[FileEntry, ...]) -> str:
    return event_digest(
        {
            "schema_version": 1,
            "coverage": "regular_files_only",
            "entries": [entry.model_dump() for entry in entries],
        }
    )


def _validated_manifest(manifest: WorkspaceManifest) -> None:
    if len(manifest.entries) > MAX_FILES:
        raise UnsafeWorkspace("workspace manifest exceeds file limit")
    if sum(entry.size for entry in manifest.entries) > MAX_TOTAL_BYTES:
        raise UnsafeWorkspace("workspace manifest exceeds total byte limit")
    paths = [entry.path for entry in manifest.entries]
    for path in paths:
        _safe_relative(path)
    if paths != sorted(set(paths)):
        raise UnsafeWorkspace("workspace paths must be unique and sorted")
    if manifest.manifest_digest != _digest_entries(manifest.entries):
        raise UnsafeWorkspace("workspace manifest digest mismatch")


def _regular_files(root: Path) -> list[Path]:
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or root.is_symlink():
        raise UnsafeWorkspace("workspace root must be a real directory")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise UnsafeWorkspace(f"workspace contains symlink: {path.relative_to(root)}")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise UnsafeWorkspace(f"workspace contains unsupported special file: {path}")
        files.append(path)
    return files


def _open_covered_file(root_fd: int, relative: str) -> int:
    """Open a file below an already-open root without following any path component."""
    parts = PurePosixPath(relative).parts
    directory_fd = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            child_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = child_fd
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def capture_workspace(root: Path, store: FileEvidenceStore) -> WorkspaceManifest:
    """Capture bounded regular files, refusing symlinks and obvious concurrent changes."""
    if store.root.resolve().is_relative_to(root.resolve()):
        raise UnsafeWorkspace("evidence store must be outside the captured workspace")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        files = _regular_files(root)
        if len(files) > MAX_FILES:
            raise UnsafeWorkspace("workspace exceeds file limit")
        entries: list[FileEntry] = []
        total = 0
        for path in files:
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative)
            descriptor = _open_covered_file(root_fd, relative)
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode):
                    raise UnsafeWorkspace(f"file changed type during capture: {relative}")
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    data = source.read(MAX_TOTAL_BYTES - total + 1)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            path_after = path.lstat()
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or (before.st_dev, before.st_ino) != (path_after.st_dev, path_after.st_ino):
                raise UnsafeWorkspace(f"file changed during capture: {relative}")
            total += len(data)
            if total > MAX_TOTAL_BYTES or len(data) != before.st_size:
                raise UnsafeWorkspace("workspace exceeds total byte limit or changed during read")
            reference = store.put(data)
            entries.append(
                FileEntry(
                    path=relative,
                    digest=reference.digest,
                    size=reference.size,
                    executable=bool(before.st_mode & 0o111),
                )
            )
        root_after = root.lstat()
        if (root_after.st_dev, root_after.st_ino) != (
            os.fstat(root_fd).st_dev,
            os.fstat(root_fd).st_ino,
        ):
            raise UnsafeWorkspace("workspace root changed during capture")
    finally:
        os.close(root_fd)
    ordered = tuple(sorted(entries, key=lambda entry: entry.path))
    return WorkspaceManifest(entries=ordered, manifest_digest=_digest_entries(ordered))


def verify_workspace(manifest: WorkspaceManifest, root: Path) -> bool:
    """Check exact declared file set, bytes, and executable flags; do not follow links."""
    _validated_manifest(manifest)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual_files = _regular_files(root)
        actual_paths = [path.relative_to(root).as_posix() for path in actual_files]
        if actual_paths != [entry.path for entry in manifest.entries]:
            return False
        for path, entry in zip(actual_files, manifest.entries, strict=True):
            descriptor = _open_covered_file(root_fd, entry.path)
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode):
                    return False
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    data = source.read(entry.size + 1)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            path_after = path.lstat()
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or (before.st_dev, before.st_ino) != (path_after.st_dev, path_after.st_ino):
                return False
            if (
                len(data) != entry.size
                or blob_digest(data) != entry.digest
                or bool(before.st_mode & 0o111) != entry.executable
            ):
                return False
        root_after = root.lstat()
        return (root_after.st_dev, root_after.st_ino) == (
            os.fstat(root_fd).st_dev,
            os.fstat(root_fd).st_ino,
        )
    finally:
        os.close(root_fd)


def restore_workspace(
    manifest: WorkspaceManifest, destination: Path, store: FileEvidenceStore
) -> None:
    """Preflight blobs, then create covered files through no-follow directory fds."""
    _validated_manifest(manifest)
    if destination.exists() or destination.is_symlink():
        raise UnsafeWorkspace("restore destination already exists")
    # Corrupt or missing evidence fails before a destination is created.
    content = {
        entry.path: store.get(BlobRef(entry.digest, entry.size)) for entry in manifest.entries
    }
    parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
        root_fd = os.open(
            destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        try:
            for entry in manifest.entries:
                parts = PurePosixPath(entry.path).parts
                directory_fd = os.dup(root_fd)
                try:
                    for component in parts[:-1]:
                        with suppress(FileExistsError):
                            os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                        child_fd = os.open(
                            component,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory_fd,
                        )
                        os.close(directory_fd)
                        directory_fd = child_fd
                    file_fd = os.open(
                        parts[-1],
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=directory_fd,
                    )
                    with os.fdopen(file_fd, "wb") as output:
                        output.write(content[entry.path])
                        output.flush()
                        os.fchmod(output.fileno(), 0o755 if entry.executable else 0o644)
                        os.fsync(output.fileno())
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    if not verify_workspace(manifest, destination):
        raise UnsafeWorkspace("post-restore verification failed")
