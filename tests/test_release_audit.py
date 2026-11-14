import json
from pathlib import Path
from typing import Any

from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.release_audit import audit_release, source_inventory


def test_changed_consumed_capsule_invalidates_a_frozen_release_source(tmp_path: Path) -> None:
    relative = "benchmarks/results/product-demo-final-2026-11-13/investigation.sentinel"
    capsule = tmp_path / relative
    capsule.parent.mkdir(parents=True)
    capsule.write_bytes(b"frozen test input")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"source_files": source_inventory(tmp_path), "artifacts": {}}))
    assert relative in source_inventory(tmp_path)
    assert audit_release(tmp_path, manifest)["source_mismatches"] == []
    capsule.write_bytes(b"different test input, unchanged test code")
    assert audit_release(tmp_path, manifest)["source_mismatches"] == [relative]


def test_release_audit_refuses_missing_results_changed_sources_and_forged_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src/example.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    manifest = tmp_path / "manifest.json"
    document: dict[str, Any] = {"source_files": source_inventory(tmp_path), "artifacts": {}}
    manifest.write_text(json.dumps(document))
    first = audit_release(tmp_path, manifest)
    assert first["status"] == "RELEASE_BLOCKED"
    assert not first["engineering_checks"]["local_tests"]["passed"]
    assert all(row["state"] == "PENDING" for row in first["review_gates"].values())
    source.write_text("value = 2\n")
    assert audit_release(tmp_path, manifest)["source_mismatches"] == ["src/example.py"]
    artifact = tmp_path / "demo.json"
    artifact.write_text('{"status":"WORKFLOW_DEMO_PASS"}')
    document["artifacts"] = {
        "product_demo": {"path": "demo.json", "digest": blob_digest(artifact.read_bytes())}
    }
    manifest.write_text(json.dumps(document))
    assert not audit_release(tmp_path, manifest)["engineering_checks"]["product_demo"]["passed"]
    artifact.write_text('{"changed":true}')
    assert not audit_release(tmp_path, manifest)["engineering_checks"]["product_demo"]["passed"]
    (tmp_path / "src/new.py").write_text("new = True\n")
    assert "src/new.py" in audit_release(tmp_path, manifest)["source_mismatches"]


def test_measurement_parser_accepts_finite_decimals_without_weakening_event_contract(
    tmp_path: Path,
) -> None:
    import pytest

    from sentinel_replay.canonical import event_digest
    from sentinel_replay.release_audit import load_report_json

    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.py").write_text("value = 1\n")
    sources = source_inventory(tmp_path)
    receipt = tmp_path / "result.json"
    receipt.write_text(
        json.dumps(
            {
                "exit_code": 0,
                "source_root": event_digest(sources),
                "command": ["make", "check"],
                "elapsed_seconds": 1.25,
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_files": sources,
                "artifacts": {
                    "local_tests": {
                        "path": "result.json",
                        "digest": blob_digest(receipt.read_bytes()),
                    }
                },
            }
        )
    )
    assert audit_release(tmp_path, manifest)["engineering_checks"]["local_tests"]["passed"]
    for malformed in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', "[" * 66 + "0" + "]" * 66):
        with pytest.raises(ValueError):
            load_report_json(malformed)
    with pytest.raises(ValueError):
        event_digest({"duration": 1.25})
