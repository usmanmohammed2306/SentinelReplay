import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sentinel_replay.boundary import BoundarySession, ReplayMiss
from sentinel_replay.canonical import CanonicalizationError, event_digest
from sentinel_replay.journal import Journal, JournalCorruption


def test_event_digest_is_stable_and_domain_separated() -> None:
    assert event_digest({"b": 2, "a": 1}) == event_digest({"a": 1, "b": 2})
    assert event_digest([1, 2]) != event_digest([2, 1])


@given(st.dictionaries(st.text(max_size=12), st.integers(), max_size=12))
def test_map_insertion_order_never_changes_digest(data: dict[str, int]) -> None:
    assert event_digest(data) == event_digest(dict(reversed(list(data.items()))))


@given(st.integers(), st.integers())
def test_distinct_list_order_changes_digest(left: int, right: int) -> None:
    if left != right:
        assert event_digest([left, right]) != event_digest([right, left])


def test_unsupported_float_is_explained() -> None:
    with pytest.raises(CanonicalizationError, match="floating point"):
        event_digest({"bad": 1.2})


def test_journal_finds_first_tampered_record(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = Journal(path)
    journal.append({"kind": "read", "value": "secret"})
    journal.append({"kind": "post", "value": "secret"})
    assert journal.verify().records == 2

    rows = path.read_text().splitlines()
    rows[0] = rows[0].replace("secret", "altered")
    path.write_text("\n".join(rows) + "\n")
    with pytest.raises(JournalCorruption, match="record 1"):
        journal.verify()


def test_replay_never_invokes_live_fallback(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    recorder = BoundarySession.record(path)
    assert recorder.call("tool", "call-1", {"x": 1}, lambda: {"ok": True}) == {"ok": True}

    replay = BoundarySession.replay(path)
    invoked = False

    def forbidden_live_call() -> dict[str, bool]:
        nonlocal invoked
        invoked = True
        return {"ok": False}

    assert replay.call("tool", "call-1", {"x": 1}, forbidden_live_call) == {"ok": True}
    assert not invoked
    with pytest.raises(ReplayMiss, match="exhausted"):
        replay.call("tool", "call-2", {"x": 2}, forbidden_live_call)
    assert not invoked


def test_replay_detects_request_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    BoundarySession.record(path).call("tool", "call-1", {"x": 1}, lambda: 42)
    with pytest.raises(ReplayMiss, match="request digest"):
        BoundarySession.replay(path).call("tool", "call-1", {"x": 2})


def test_replay_detects_changed_safe_evidence_metadata(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    BoundarySession.record(path).call(
        "tool", "call-1", {"x": 1}, lambda: 42, evidence={"operation": "read_file"}
    )
    with pytest.raises(ReplayMiss, match="evidence mismatch"):
        BoundarySession.replay(path).call(
            "tool", "call-1", {"x": 1}, evidence={"operation": "http_post"}
        )


def test_recording_file_is_auditable_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    BoundarySession.record(path).call("tool", "call-1", {"x": 1}, lambda: "answer")
    row = json.loads(path.read_text().strip())
    assert row["event"]["call_id"] == "call-1"
    assert row["event"]["response"] == "answer"


def test_truncated_journal_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    BoundarySession.record(path).call("tool", "one", {"x": 1}, lambda: "ok")
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(JournalCorruption, match="unterminated line"):
        BoundarySession.replay(path)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    path.write_text('{"index":1,"index":1}\n')
    with pytest.raises(JournalCorruption, match="duplicate JSON key"):
        Journal(path).verify()


def test_repeated_calls_require_original_identity_and_order(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    recorder = BoundarySession.record(path)
    recorder.call("tool", "first", {"same": True}, lambda: "A")
    recorder.call("tool", "second", {"same": True}, lambda: "B")
    replay = BoundarySession.replay(path)
    assert replay.call("tool", "first", {"same": True}) == "A"
    with pytest.raises(ReplayMiss, match="call id mismatch"):
        replay.call("tool", "first", {"same": True})


def test_incomplete_replay_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    recorder = BoundarySession.record(path)
    recorder.call("tool", "first", {}, lambda: "A")
    recorder.call("tool", "second", {}, lambda: "B")
    replay = BoundarySession.replay(path)
    replay.call("tool", "first", {})
    with pytest.raises(ReplayMiss, match="stopped after 1 of 2"):
        replay.assert_complete()


def test_valid_chain_with_invalid_boundary_shape_fails_as_replay_miss(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    Journal(path).append(
        {
            "kind": "tool",
            "call_id": "one",
            "sequence": 0,
            "request_digest": event_digest({}),
        }
    )
    replay = BoundarySession.replay(path)
    with pytest.raises(ReplayMiss, match="missing response"):
        replay.call("tool", "one", {})


def test_append_rejects_an_existing_corrupt_chain(tmp_path: Path) -> None:
    path = tmp_path / "recordings.jsonl"
    journal = Journal(path)
    journal.append({"first": True})
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(JournalCorruption, match="unterminated line"):
        journal.append({"second": True})


@given(st.lists(st.dictionaries(st.text(max_size=8), st.integers(), max_size=4), max_size=30))
def test_batch_append_matches_individual_chain(events: list[dict[str, int]]) -> None:
    with tempfile.TemporaryDirectory() as directory:
        batch = Journal(Path(directory) / "batch.jsonl")
        individual = Journal(Path(directory) / "individual.jsonl")
        batched_result = batch.append_many(iter(events))
        for event in events:
            individual.append(event)
        if events:
            assert batched_result == individual.verify()
            assert batch.path.read_bytes() == individual.path.read_bytes()
        else:
            assert batched_result.records == 0


def test_batch_prevalidation_never_appends_half_valid_input(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "batch.jsonl")
    original = journal.append({"first": True})
    before = journal.path.read_bytes()
    with pytest.raises(CanonicalizationError, match="floating point"):
        journal.append_many([{"valid": 1}, {"invalid": 1.5}])
    assert journal.path.read_bytes() == before
    assert journal.verify() == original


def test_batch_rejects_corrupt_existing_chain_without_writing(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "batch.jsonl")
    journal.append({"first": True})
    journal.path.write_bytes(journal.path.read_bytes()[:-1])
    before = journal.path.read_bytes()
    with pytest.raises(JournalCorruption, match="unterminated line"):
        journal.append_many([{"second": True}, {"third": True}])
    assert journal.path.read_bytes() == before


def test_three_thousand_event_batch_verifies_and_preserves_order(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "long.jsonl")
    events = ({"step": index, "kind": "benign"} for index in range(3_000))
    result = journal.append_many(events)
    assert result == journal.verify()
    assert result.records == 3_000
    recorded = journal.events()
    assert recorded[0] == {"step": 0, "kind": "benign"}
    assert recorded[-1] == {"step": 2_999, "kind": "benign"}


def test_stream_writer_matches_batch_and_closes(tmp_path: Path) -> None:
    path = tmp_path / "stream.jsonl"
    writer = Journal(path).writer()
    with writer:
        assert writer.verification is not None
        assert writer.verification.records == 0
        for index in range(100):
            writer.append({"step": index})
    assert Journal(path).verify() == Journal(tmp_path / "batch.jsonl").append_many(
        {"step": index} for index in range(100)
    )
    with pytest.raises(RuntimeError, match="not open"):
        writer.append({"late": True})


def test_two_stream_writers_serialize_without_losing_events(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.jsonl"
    barrier = Barrier(2)

    def write_group(group: int) -> None:
        barrier.wait()
        with Journal(path).writer() as writer:
            for index in range(25):
                writer.append({"group": group, "index": index})

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(write_group, 1)
        right = pool.submit(write_group, 2)
        left.result(timeout=10)
        right.result(timeout=10)
    journal = Journal(path)
    assert journal.verify().records == 50
    events = journal.events()
    assert all(isinstance(event, dict) for event in events)
    assert {event.get("group") for event in events if isinstance(event, dict)} == {1, 2}


def test_stream_writer_refuses_corrupt_prior_chain(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.jsonl"
    Journal(path).append({"first": True})
    path.write_bytes(path.read_bytes()[:-1])
    before = path.read_bytes()
    with pytest.raises(JournalCorruption, match="unterminated line"), Journal(path).writer():
        pass
    assert path.read_bytes() == before


def test_journal_writers_refuse_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_bytes(b"user data\n")
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)
    with pytest.raises(OSError):
        Journal(link).append_many([{"event": 1}])
    with pytest.raises(OSError), Journal(link).writer():
        pass
    assert target.read_bytes() == b"user data\n"


def test_streaming_boundary_session_replays_exactly(tmp_path: Path) -> None:
    path = tmp_path / "recording.jsonl"
    with BoundarySession.record_stream(path) as session:
        for index in range(25):

            def live_value(value: int = index) -> int:
                return value

            assert session.call("tool", f"call-{index}", {"x": index}, live_value) == index
    replay = BoundarySession.replay(path)
    for index in range(25):
        assert replay.call("tool", f"call-{index}", {"x": index}) == index
    replay.assert_complete()


def test_excessive_nesting_is_a_controlled_evidence_error() -> None:
    from sentinel_replay.canonical import CanonicalizationError, canonical_bytes, load_json_unique

    value: object = "leaf"
    for _ in range(80):
        value = [value]
    with pytest.raises(CanonicalizationError, match="nesting"):
        canonical_bytes(value)
    with pytest.raises(CanonicalizationError, match="nesting"):
        load_json_unique("[" * 2000 + "0" + "]" * 2000)
