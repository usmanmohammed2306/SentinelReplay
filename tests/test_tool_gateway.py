"""The covered MCP effect is denied before bytes are read or written."""

from pathlib import Path
from typing import cast

import pytest

from sentinel_replay.journal import Journal, JournalCorruption
from sentinel_replay.policy import PolicyAction, PolicyDenied, PolicySpec, PolicyUnavailable
from sentinel_replay.tool_gateway import GatewayError, ToolGateway


class FixedEvaluator:
    def __init__(self, answer: bool | Exception) -> None:
        self.answer = answer
        self.seen: list[PolicyAction] = []

    def evaluate(self, _policy: PolicySpec, action: PolicyAction) -> bool:
        self.seen.append(action)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def fixture_gateway(tmp_path: Path, evaluator: FixedEvaluator) -> tuple[ToolGateway, Path, Path]:
    root = tmp_path / "agent-fixtures"
    (root / "sources").mkdir(parents=True)
    (root / "outbox").mkdir()
    (root / "sources" / "public.txt").write_bytes(b"public\n")
    (root / "sources" / "credential.txt").write_bytes(b"synthetic-test-secret\n")
    journal_path = tmp_path / "controller" / "gateway.jsonl"
    gateway = ToolGateway(
        root=root,
        journal_path=journal_path,
        source_tools={"public.txt": "copy_public", "credential.txt": "copy_secret"},
        policy=PolicySpec(allow_tools=("copy_public",), deny_tools=("copy_secret",)),
        evaluator=evaluator,
    )
    return gateway, root, journal_path


def test_denial_is_durable_and_has_no_effect(tmp_path: Path) -> None:
    evaluator = FixedEvaluator(False)
    gateway, root, journal_path = fixture_gateway(tmp_path, evaluator)
    with pytest.raises(PolicyDenied):
        gateway.copy_named("credential.txt", "leak.txt")
    assert not (root / "outbox" / "leak.txt").exists()
    assert evaluator.seen == [PolicyAction(tool="copy_secret")]
    events, verification = Journal(journal_path).read_verified()
    assert all(isinstance(event, dict) for event in events)
    dict_events = [event for event in events if isinstance(event, dict)]
    assert verification.records == 2
    assert [event["kind"] for event in dict_events] == ["gateway_proposal", "gateway_decision"]
    assert dict_events[1]["state"] == "denied"
    assert "synthetic-test-secret" not in journal_path.read_text()


def test_allow_copies_and_records_digest_without_payload(tmp_path: Path) -> None:
    gateway, root, journal_path = fixture_gateway(tmp_path, FixedEvaluator(True))
    receipt = gateway.copy_named("public.txt", "copy.txt")
    assert (root / "outbox" / "copy.txt").read_bytes() == b"public\n"
    assert receipt["bytes"] == 7
    events, verification = Journal(journal_path).read_verified()
    assert all(isinstance(event, dict) for event in events)
    dict_events = [event for event in events if isinstance(event, dict)]
    assert verification.records == 4
    assert [event["kind"] for event in dict_events] == [
        "gateway_proposal",
        "gateway_decision",
        "gateway_effect_intent",
        "gateway_result",
    ]
    assert dict_events[2]["digest"] == receipt["digest"]
    assert dict_events[3]["state"] == "completed"
    assert dict_events[3]["digest"] == receipt["digest"]
    assert "public\\n" not in journal_path.read_text()


def test_engine_unavailable_fails_closed(tmp_path: Path) -> None:
    gateway, root, journal_path = fixture_gateway(
        tmp_path, FixedEvaluator(PolicyUnavailable("OPA offline"))
    )
    with pytest.raises(PolicyUnavailable):
        gateway.copy_named("public.txt", "copy.txt")
    assert not (root / "outbox" / "copy.txt").exists()
    events = Journal(journal_path).events()
    assert isinstance(events[1], dict)
    assert events[1]["state"] == "unavailable"


def test_non_boolean_decision_fails_closed(tmp_path: Path) -> None:
    gateway, root, journal_path = fixture_gateway(tmp_path, FixedEvaluator(cast(bool, "false")))
    with pytest.raises(PolicyUnavailable, match="boolean"):
        gateway.copy_named("public.txt", "copy.txt")
    assert not (root / "outbox" / "copy.txt").exists()
    events = Journal(journal_path).events()
    assert isinstance(events[1], dict)
    assert events[1]["state"] == "unavailable"


def test_bad_names_are_rejected_before_journal(tmp_path: Path) -> None:
    gateway, _root, journal_path = fixture_gateway(tmp_path, FixedEvaluator(True))
    for source, destination in (
        ("../credential.txt", "copy.txt"),
        ("public.txt", "../copy.txt"),
        ("public.txt", "."),
        ("other.txt", "copy.txt"),
    ):
        with pytest.raises(GatewayError):
            gateway.copy_named(source, destination)
    assert not journal_path.exists()


def test_symlink_source_is_refused_after_allow(tmp_path: Path) -> None:
    gateway, root, journal_path = fixture_gateway(tmp_path, FixedEvaluator(True))
    (root / "sources" / "public.txt").unlink()
    (root / "sources" / "public.txt").symlink_to(root / "sources" / "credential.txt")
    with pytest.raises(OSError):
        gateway.copy_named("public.txt", "copy.txt")
    assert not (root / "outbox" / "copy.txt").exists()
    last_event = Journal(journal_path).events()[-1]
    assert isinstance(last_event, dict)
    assert last_event["state"] == "failed_or_unknown"


def test_corrupt_journal_blocks_effect(tmp_path: Path) -> None:
    gateway, root, journal_path = fixture_gateway(tmp_path, FixedEvaluator(True))
    journal_path.parent.mkdir()
    journal_path.write_text("corrupt\n")
    with pytest.raises(JournalCorruption):
        gateway.copy_named("public.txt", "copy.txt")
    assert not (root / "outbox" / "copy.txt").exists()
