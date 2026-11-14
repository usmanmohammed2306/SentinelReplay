"""Stopped-controller reachability collection, with dry-run default and audit.

Retired runs become inaccessible immediately. Payload collection is a separate
offline operator operation; signed metadata/tombstones/access audit remain.
Backups are separate copies and are not erased by this collector.
"""

import fcntl
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.capsule import MAX_ARCHIVE_BYTES
from sentinel_replay.database import (
    RunRepository,
    event_pages,
    future_receipts,
    operation_events,
    operation_jobs,
    run_indexes,
    run_retirements,
    runs,
)
from sentinel_replay.encrypted_store import _MAGIC, EncryptedEvidenceStore
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import _regular_bytes


def _open_dir(path: Path) -> int:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.absolute().parts[1:]:
            if part in {".", ".."}:
                raise ValueError("unsafe directory component")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _inventory(root: Path, *, sharded: bool) -> list[tuple[str, int]]:
    if root.is_symlink():
        raise ValueError("store inventory refuses symlink roots")
    if not root.exists():
        return []
    result = []
    descriptor = _open_dir(root)
    try:
        with os.scandir(descriptor) as entries:
            for item in entries:
                pattern = r"[0-9a-f]{2}" if sharded else r"[0-9a-f]{64}"
                if re.fullmatch(pattern, item.name) is None:
                    raise ValueError("unexpected object store inventory entry")
                if sharded:
                    child = os.open(
                        item.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                    )
                    try:
                        with os.scandir(child) as leaves:
                            for leaf in leaves:
                                if (
                                    re.fullmatch(r"[0-9a-f]{64}", leaf.name) is None
                                    or not leaf.name.startswith(item.name)
                                    or not leaf.is_file(follow_symlinks=False)
                                ):
                                    raise ValueError("malformed or nonregular CAS leaf")
                                result.append(
                                    (
                                        item.name + "/" + leaf.name,
                                        leaf.stat(follow_symlinks=False).st_size,
                                    )
                                )
                    finally:
                        os.close(child)
                else:
                    if not item.is_file(follow_symlinks=False):
                        raise ValueError("nonregular ciphertext reference")
                    result.append((item.name, item.stat(follow_symlinks=False).st_size))
    finally:
        os.close(descriptor)
    return sorted(result)


def _unlink(root: Path, relative: str) -> None:
    descriptor = _open_dir(root)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("collection refuses a nonregular object")
        os.unlink(parts[-1], dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def collect_evidence(
    engine: Engine, root: Path, key: Path | None = None, *, apply: bool = False
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir() or not (root / "controller.lock").is_file():
        raise ValueError("collection requires an existing controller evidence root")
    root = root.resolve(strict=True)
    directory = _open_dir(root)
    try:
        descriptor = os.open("controller.lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError(
                "stop the controller and all evidence writers before collecting"
            ) from None
        return _collect(engine, root, key, apply=apply)
    finally:
        os.close(descriptor)


def _collect(engine: Engine, root: Path, key: Path | None, *, apply: bool) -> dict[str, Any]:
    encrypted = key is not None
    if not encrypted and (root / "ciphertext").exists():
        raise ValueError("encrypted collection requires the separate evidence key")
    store = (
        EncryptedEvidenceStore(root, key, max_bytes=MAX_ARCHIVE_BYTES)
        if key
        else FileEvidenceStore(root, max_bytes=MAX_ARCHIVE_BYTES)
    )
    object_root = root / "ciphertext/sha256" if encrypted else root / "sha256"
    inventory = _inventory(object_root, sharded=True)
    references = _inventory(root / "refs", sharded=False) if encrypted else []
    retained: dict[str, BlobRef] = {}
    active: dict[str, Any] = {}
    repository = RunRepository(engine)
    with engine.connect() as connection:
        retired: set[str] = set(connection.execute(select(run_retirements.c.run_id)).scalars())
        run_rows = connection.execute(select(runs)).mappings().all()
        for row in run_rows:
            if row["run_id"] not in retired:
                active[row["run_id"]] = dict(row)

    def add(ref: BlobRef) -> bytes:
        previous = retained.get(ref.digest)
        if previous is not None and previous.size != ref.size:
            raise ValueError("active reference size conflicts")
        data = store.get(ref)
        retained[ref.digest] = ref
        return data

    for row in active.values():
        add(BlobRef(row["capsule_digest"], row["capsule_size"]))
        ref = repository.attestation(row["run_id"])
        if ref:
            add(ref)
    with engine.connect() as connection:
        pages = (
            connection.execute(
                select(event_pages.c.digest, event_pages.c.size)
                .join(run_indexes, event_pages.c.index_id == run_indexes.c.index_id)
                .where(run_indexes.c.run_id.in_(active))
            )
            .mappings()
            .all()
        )
        futures = (
            connection.execute(select(future_receipts).where(future_receipts.c.run_id.in_(active)))
            .mappings()
            .all()
        )
        requests = (
            connection.execute(select(operation_jobs).where(operation_jobs.c.run_id.in_(active)))
            .mappings()
            .all()
        )
        results = (
            connection.execute(
                select(operation_jobs.c.run_id, operation_jobs.c.job_id, operation_events.c.body)
                .join(operation_events, operation_jobs.c.job_id == operation_events.c.job_id)
                .where(operation_jobs.c.run_id.in_(active), operation_events.c.state == "completed")
            )
            .mappings()
            .all()
        )
        retired_jobs: list[str] = list(
            connection.execute(
                select(operation_jobs.c.job_id).where(operation_jobs.c.run_id.in_(retired))
            ).scalars()
        )
    for row in pages:
        add(BlobRef(row["digest"], row["size"]))
    for row in requests:
        add(BlobRef(row["request_digest"], row["request_size"]))

    def future(ref: BlobRef, run_id: str) -> None:
        value = load_json_unique(add(ref).decode())
        if (
            value["kind"] != "finite_future_receipt"
            or value["parent_run_id"] != run_id
            or value["parent_capsule_digest"] != active[run_id]["capsule_digest"]
        ):
            raise ValueError("active future receipt binding differs")
        add(BlobRef(value["capsule_digest"], value["capsule_size"]))

    for row in futures:
        future(BlobRef(row["digest"], row["size"]), row["run_id"])
    for row in results:
        ref = row["body"]["result"]
        value = load_json_unique(add(BlobRef(ref["digest"], ref["size"])).decode())
        if (
            value["job_id"] != row["job_id"]
            or value["run_id"] != row["run_id"]
            or value["source_capsule_digest"] != active[row["run_id"]]["capsule_digest"]
        ):
            raise ValueError("active operation result binding differs")
        capsule = value["report"].get("capsule")
        if capsule:
            add(BlobRef(capsule["digest"], capsule["size"]))
    # Preserve valid historical future receipts even before structured receipt
    # rows were introduced. Audit entries carry no raw content or credentials.
    audit = root / "access-audit.jsonl"
    if audit.exists():

        def visit(_index: int, event: object) -> None:
            if (
                not isinstance(event, dict)
                or event.get("kind") != "future_created"
                or event.get("run_id") not in active
            ):
                return
            digest = event["receipt"]
            if digest in retained:
                return
            BlobRef(digest, 0)
            if encrypted:
                index = load_json_unique(_regular_bytes(root / "refs" / digest[7:], 1024).decode())
                size = index["size"] - len(_MAGIC) - 28
            else:
                size = (root / "sha256" / digest[7:9] / digest[7:]).lstat().st_size
            future(BlobRef(digest, size), event["run_id"])

        Journal(audit).scan_verified(visit)
    kept_objects = set()
    if encrypted:
        for digest in retained:
            index = load_json_unique(_regular_bytes(root / "refs" / digest[7:], 1024).decode())
            cipher_ref = BlobRef(index["digest"], index["size"])
            kept_objects.add(cipher_ref.digest[7:])
    else:
        kept_objects = {digest[7:] for digest in retained}
    garbage = [(path, size) for path, size in inventory if path.split("/")[-1] not in kept_objects]
    unused_refs = [(path, size) for path, size in references if "sha256:" + path not in retained]
    report: dict[str, Any] = {
        "schema_version": 1,
        "scope": "offline_reachability_collection",
        "apply": apply,
        "active_runs": len(active),
        "retired_runs": len(retired),
        "verified_live_references": len(retained),
        "candidate_objects": len(garbage),
        "candidate_reference_indexes": len(unused_refs),
        "candidate_physical_bytes": sum(size for _, size in [*garbage, *unused_refs]),
        "candidate_set_digest": event_digest({"objects": garbage, "references": unused_refs}),
        "objects_removed": 0,
        "indexes_removed": 0,
        "synthetic_job_directories_removed": 0,
        "limitation": (
            "Stopped cooperative writers required. Audit/tombstone metadata and separate backups "
            "remain; this is logical unlink, not secure SSD erasure."
        ),
    }
    if apply:
        with Journal(root / "collection-audit.jsonl").writer() as writer:
            writer.append({"kind": "collection_intent", **report})
            for path, _ in unused_refs:
                _unlink(root / "refs", path)
                report["indexes_removed"] += 1
            for path, _ in garbage:
                _unlink(object_root, path)
                report["objects_removed"] += 1
            jobs = root / "synthetic-policy-jobs"
            if jobs.exists():
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise ValueError("platform lacks safe directory-relative tree removal")
                jobs_fd = _open_dir(jobs)
                try:
                    for identifier in retired_jobs:
                        if re.fullmatch(r"[0-9a-f]{32}", identifier) is None:
                            raise ValueError("invalid retired synthetic job identifier")
                        try:
                            item = os.stat(identifier, dir_fd=jobs_fd, follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        if not stat.S_ISDIR(item.st_mode):
                            raise ValueError("retired job artifact is not a regular directory")
                        shutil.rmtree(identifier, dir_fd=jobs_fd)
                        report["synthetic_job_directories_removed"] += 1
                    os.fsync(jobs_fd)
                finally:
                    os.close(jobs_fd)
            writer.append({"kind": "collection_completed", **report})
    return report
