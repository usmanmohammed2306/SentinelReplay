"""Portable exact environment-pack inputs, checkpoint blobs and effect receipts."""

import json
import tempfile
from pathlib import Path
from typing import Any

from sentinel_replay.blob_bank import restore_blob_bank, write_blob_bank
from sentinel_replay.capsule import export_capsule
from sentinel_replay.checkpoint_set import restore_checkpoint_set
from sentinel_replay.environment_pack import replay_pack
from sentinel_replay.journal import Journal


def export_pack(
    source: Path, destination: Path, extra_artifacts: dict[str, Path] | None = None
) -> dict[str, Any]:
    report = json.loads((source / "report.json").read_text())
    verified = Journal(source / "journal.jsonl").verify()
    if verified.root != report["journal_root"]:
        raise ValueError("pack journal differs from report")
    artifacts = {
        "pack-definition.json": source / "definition.json",
        "report.json": source / "report.json",
    }
    for name in (
        "telemetry.otlp.json",
        "telemetry-merge.json",
        "sqlite-manifest.json",
        "git-manifest.json",
    ):
        if (source / name).is_file():
            artifacts[name] = source / name
    for name, path in (extra_artifacts or {}).items():
        if name in artifacts:
            raise ValueError("duplicate pack artifact")
        artifacts[name] = path
    with tempfile.TemporaryDirectory(prefix="sentinel-blob-bank-") as directory:
        bank = write_blob_bank(source / "blobs", Path(directory))
        if set(bank) & set(artifacts):
            raise ValueError("duplicate checkpoint artifact")
        artifacts.update(bank)
        result = export_capsule(
            "pack-" + report["definition_digest"][7:],
            source / "journal.jsonl",
            destination,
            artifacts,
        )
    return {"run_id": result.run_id, "journal_root": result.root, "records": result.records}


def replay_imported_pack(artifacts: dict[str, bytes], journal: bytes, root: Path) -> dict[str, Any]:
    from sentinel_replay.evidence_store import FileEvidenceStore

    source = root / "pack-source"
    source.mkdir()
    (source / "definition.json").write_bytes(artifacts["pack-definition.json"])
    (source / "report.json").write_bytes(artifacts["report.json"])
    (source / "journal.jsonl").write_bytes(journal)
    store = FileEvidenceStore(source / "blobs", max_bytes=32 * 1024 * 1024)
    restore_blob_bank(artifacts, store)
    result = replay_pack(
        source,
        root / "pack-replayed",
        extra_restore=lambda target, expected: restore_checkpoint_set(artifacts, target, expected),
    )
    result["live_calls"] = result["live_nondeterministic_calls"]
    return result
