from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.gateway_audit import GatewayAuditError, audit_gateway_journal
from sentinel_replay.journal import Journal, JournalCorruption

POLICY = "sha256:" + "a" * 64
OUTPUT = "sha256:" + "b" * 64
REQUEST_1 = "1" * 32
REQUEST_2 = "2" * 32


def proposal(request_id: str) -> dict[str, object]:
    return {
        "kind": "gateway_proposal",
        "request_id": request_id,
        "source_alias": "public.txt",
        "destination_name": "copy.txt",
        "tool": "copy_public",
        "policy_digest": POLICY,
    }


def decision(request_id: str, state: str) -> dict[str, object]:
    return {"kind": "gateway_decision", "request_id": request_id, "state": state}


def result(request_id: str) -> dict[str, object]:
    return {
        "kind": "gateway_result",
        "request_id": request_id,
        "state": "completed",
        "bytes": 7,
        "digest": OUTPUT,
    }


def intent(request_id: str) -> dict[str, object]:
    return {
        "kind": "gateway_effect_intent",
        "request_id": request_id,
        "bytes": 7,
        "digest": OUTPUT,
    }


def test_audit_counts_only_completed_effects(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append_many(
        [
            proposal(REQUEST_1),
            decision(REQUEST_1, "denied"),
            proposal(REQUEST_2),
            decision(REQUEST_2, "allowed"),
            result(REQUEST_2),
        ]
    )
    report = audit_gateway_journal(path, expected_policy_digest=POLICY)
    assert report.journal_records == 5
    assert report.requests == 2
    assert (report.completed, report.denied, report.interrupted_unknown) == (1, 1, 0)
    assert report.replay_coverage == "unsupported"
    cli = CliRunner().invoke(app, ["gateway", "audit", str(path)])
    assert cli.exit_code == 0
    assert '"completed": 1' in cli.stdout


def test_allowed_without_result_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append_many([proposal(REQUEST_1), decision(REQUEST_1, "allowed")])
    report = audit_gateway_journal(path)
    assert report.completed == 0
    assert report.interrupted_unknown == 1


def test_intent_without_result_is_unknown_and_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append_many(
        [proposal(REQUEST_1), decision(REQUEST_1, "allowed"), intent(REQUEST_1)]
    )
    assert audit_gateway_journal(path).interrupted_unknown == 1
    bad = result(REQUEST_1)
    bad["digest"] = POLICY
    Journal(path).append(bad)
    with pytest.raises(GatewayAuditError, match="result does not match effect intent"):
        audit_gateway_journal(path)


def test_proposal_without_decision_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append(proposal(REQUEST_1))
    report = audit_gateway_journal(path)
    assert report.interrupted_unknown == 1
    assert report.denied == 0


@pytest.mark.parametrize(
    "events",
    [
        [result(REQUEST_1)],
        [proposal(REQUEST_1), result(REQUEST_1)],
        [proposal(REQUEST_1), decision(REQUEST_1, "denied"), result(REQUEST_1)],
        [proposal(REQUEST_1), proposal(REQUEST_1)],
        [proposal(REQUEST_1), decision(REQUEST_2, "allowed")],
    ],
)
def test_self_consistent_but_invalid_sequences_are_rejected(
    tmp_path: Path, events: list[dict[str, object]]
) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append_many(events)
    with pytest.raises(GatewayAuditError):
        audit_gateway_journal(path)


def test_policy_mismatch_and_corruption_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    Journal(path).append(proposal(REQUEST_1))
    with pytest.raises(GatewayAuditError, match="policy digest mismatch"):
        audit_gateway_journal(path, expected_policy_digest=OUTPUT)
    path.write_bytes(path.read_bytes() + b"torn")
    with pytest.raises(JournalCorruption):
        audit_gateway_journal(path)


def test_mixed_policy_digests_are_rejected_even_without_expected_policy(tmp_path: Path) -> None:
    path = tmp_path / "gateway.jsonl"
    changed = proposal(REQUEST_2)
    changed["policy_digest"] = OUTPUT
    Journal(path).append_many([proposal(REQUEST_1), decision(REQUEST_1, "denied"), changed])
    with pytest.raises(GatewayAuditError, match="mixes policy digests"):
        audit_gateway_journal(path)
