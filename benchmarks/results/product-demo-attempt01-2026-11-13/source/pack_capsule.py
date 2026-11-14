"""Portable exact environment-pack inputs, checkpoint blobs and effect receipts."""

import json
from pathlib import Path
from typing import Any

from sentinel_replay.capsule import export_capsule
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
    for path in sorted((source / "blobs/sha256").glob("*/*")):
        artifacts["blob-" + path.name] = path
    for name, path in (extra_artifacts or {}).items():
        if name in artifacts:
            raise ValueError("duplicate pack artifact")
        artifacts[name] = path
    result = export_capsule(
        "pack-" + report["definition_digest"][7:], source / "journal.jsonl", destination, artifacts
    )
    return {"run_id": result.run_id, "journal_root": result.root, "records": result.records}


def replay_imported_pack(artifacts: dict[str, bytes], journal: bytes, root: Path) -> dict[str, Any]:
    from sentinel_replay.evidence_store import FileEvidenceStore

    source = root / "pack-source"
    source.mkdir()
    (source / "definition.json").write_bytes(artifacts["pack-definition.json"])
    (source / "report.json").write_bytes(artifacts["report.json"])
    (source / "journal.jsonl").write_bytes(journal)
    store = FileEvidenceStore(source / "blobs")
    for name, value in artifacts.items():
        if name.startswith("blob-") and store.put(value).digest != "sha256:" + name[5:]:
            raise ValueError("pack checkpoint blob identity mismatch")
    result = replay_pack(source, root / "pack-replayed")
    result["checkpoints"] = {"workspace": result["checkpoint_verified"]}
    result["live_calls"] = result["live_nondeterministic_calls"]
    return result
