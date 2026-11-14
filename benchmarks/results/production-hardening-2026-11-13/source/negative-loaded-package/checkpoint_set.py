"""A closed adapter registry; capsule data cannot nominate executable code."""

from pathlib import Path
from typing import Any

from sentinel_replay.blob_bank import restore_blob_bank
from sentinel_replay.canonical import event_digest
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.git_snapshot import GitCheckpoint, restore_git
from sentinel_replay.sqlite_snapshot import SQLiteCheckpoint, restore_sqlite


def restore_checkpoint_set(
    artifacts: dict[str, bytes], root: Path, expected: dict[str, str] | None = None
) -> dict[str, bool]:
    names = {
        name
        for name, artifact in (("sqlite", "sqlite-manifest.json"), ("git", "git-manifest.json"))
        if artifact in artifacts
    }
    if expected is not None and names != set(expected):
        raise ValueError("checkpoint adapter inventory differs from the recorded definition")
    if not names:
        return {}
    store = FileEvidenceStore(root / "checkpoint-blobs", max_bytes=32 * 1024 * 1024)
    restore_blob_bank(artifacts, store)
    manifests: dict[str, Any] = {}
    if "sqlite" in names:
        manifests["sqlite"] = SQLiteCheckpoint.model_validate_json(
            artifacts["sqlite-manifest.json"]
        )
    if "git" in names:
        manifests["git"] = GitCheckpoint.model_validate_json(artifacts["git-manifest.json"])
    if expected is not None and any(
        event_digest(manifest.model_dump()) != expected[name]
        for name, manifest in manifests.items()
    ):
        raise ValueError("checkpoint manifest differs from the frozen initial state")
    results = {}
    if "sqlite" in manifests:
        results["sqlite"] = restore_sqlite(manifests["sqlite"], root / "restored-sqlite.db", store)
    if "git" in manifests:
        results["git"] = restore_git(manifests["git"], root / "restored-git", store)
    return results
