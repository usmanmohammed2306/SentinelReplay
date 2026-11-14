"""Stored bytes, rather than UI claims, drive every investigation view."""

from pathlib import Path

import pytest

from sentinel_replay.investigation import CapsuleInvestigation

RESULT = Path(__file__).resolve().parents[1] / (
    "benchmarks/results/isolated-branches-final-2026-11-13"
    "/protected_export--allow_both/controller/branch.sentinel"
)


def test_actual_branch_has_redacted_timeline_dependencies_and_restorable_replay() -> None:
    investigation = CapsuleInvestigation(RESULT.read_bytes())
    summary = investigation.summary()
    assert summary["records"] > 0
    timeline = investigation.timeline(offset=0, limit=2)
    assert len(timeline["events"]) == 2
    assert timeline["next_offset"] == 2
    assert "SENTINEL_BRANCH_SYNTHETIC_ONLY" not in str(timeline)
    assert "request" not in timeline["events"][0]
    graph = investigation.provenance(root_step=2, depth=3)
    assert all(row["kind"] != "chronological" for row in graph["edges"])
    replay = investigation.replay()
    assert replay["mode"] == "BOUNDARY_REPLAY_MATCHED"
    assert replay["checkpoints"] == {"workspace": True, "fixture": True}


def test_pagination_root_binding_and_bad_archive_fail_closed() -> None:
    investigation = CapsuleInvestigation(RESULT.read_bytes())
    with pytest.raises(ValueError, match="pagination"):
        investigation.timeline(offset=-1, limit=5000)
    with pytest.raises(ValueError, match="root"):
        investigation.timeline(offset=0, limit=5, expected_root="sha256:" + "0" * 64)
    with pytest.raises(ValueError):
        CapsuleInvestigation(b"hostile archive")


def test_event_stream_has_ids_redacted_data_and_exact_resume() -> None:
    investigation = CapsuleInvestigation(RESULT.read_bytes())
    messages = list(investigation.stream(after=1, limit=2))
    assert len(messages) == 2
    assert messages[0].startswith("id: 2\nevent: boundary\ndata: ")
    assert "SENTINEL_BRANCH_SYNTHETIC_ONLY" not in "".join(messages)
    assert list(investigation.stream(after=investigation.verified.records - 1, limit=5)) == []
