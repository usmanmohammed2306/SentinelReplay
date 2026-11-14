import json
from pathlib import Path

import pytest

from sentinel_replay.canonical import event_digest
from sentinel_replay.journal import Journal
from sentinel_replay.telemetry import RecordingTelemetry, merge_telemetry


def test_real_sdk_spans_enrich_exact_journal_without_changing_evidence(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    request = {"safe": "fixture"}
    events = [
        {"call_id": name, "request_digest": event_digest(request)} for name in ("first", "next")
    ]
    verified = Journal(journal).append_many(events)
    original = journal.read_bytes()
    telemetry = RecordingTelemetry()
    with telemetry.boundary("first", event_digest(request), None):
        pass
    with telemetry.boundary("next", event_digest(request), "first"):
        pass
    path = tmp_path / "spans.json"
    telemetry.finish(path)
    result = merge_telemetry(journal, path.read_bytes(), expected_root=verified.root)
    assert len(result["matched_spans"]) == 2
    assert result["structural_edges"][0]["kind"] == "trace_parent"
    assert result["structural_edges"][0]["source"] == 0
    assert journal.read_bytes() == original
    data = json.loads(path.read_bytes())
    span = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["attributes"][1]["value"]["stringValue"] = event_digest({"changed": True})
    with pytest.raises(ValueError, match="binding"):
        merge_telemetry(journal, json.dumps(data).encode(), expected_root=verified.root)
    with pytest.raises(ValueError, match="root"):
        merge_telemetry(journal, path.read_bytes(), expected_root="sha256:" + "0" * 64)


def test_unknown_spans_are_counted_and_attributes_redacted(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    verified = Journal(journal).append_many([{"call_id": "known", "request_digest": "safe"}])
    span = {
        "traceId": "1" * 32,
        "spanId": "2" * 16,
        "attributes": [{"key": "secret", "value": {"stringValue": "must-not-appear"}}],
    }
    data = json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}).encode()
    result = merge_telemetry(journal, data, expected_root=verified.root)
    assert result["unmatched_spans"] == 1
    assert "must-not-appear" not in json.dumps(result)
