"""Coverage reports never promote observed actions into a replay guarantee."""

from sentinel_replay.agent_coverage import assess_agent_coverage
from sentinel_replay.codex_trace import CodexObservation
from sentinel_replay.gateway_audit import GatewayAudit


def observation(*, commands: int = 0) -> CodexObservation:
    return CodexObservation(
        mode="AGENT_OBSERVATION_ONLY",
        trace_digest="sha256:" + "a" * 64,
        events=9,
        commands_started=commands,
        commands_completed=commands,
        file_changes_completed=0,
        other_item_events=2,
        other_events=5,
        turn_status="completed",
        replay_coverage="unsupported",
        limitation="observation only",
    )


def gateway() -> GatewayAudit:
    return GatewayAudit(
        journal_root="sha256:" + "b" * 64,
        journal_records=5,
        requests=2,
        completed=1,
        denied=1,
        unavailable=0,
        failed_or_unknown=0,
        interrupted_unknown=0,
    )


def test_cooperative_gateway_run_is_still_partial_not_verified_replay() -> None:
    report = assess_agent_coverage(observation(), gateway())
    assert report.gateway_requests == 2
    assert report.observed_native_commands == 0
    assert report.action_coverage == "partial"
    assert report.strict_replay_eligible is False
    assert any("lack a shared authenticated call identity" in gap for gap in report.gaps)


def test_native_command_bypasses_covered_gateway() -> None:
    report = assess_agent_coverage(observation(commands=1), gateway())
    assert report.observed_native_commands == 1
    assert report.strict_replay_eligible is False
    assert "unsupported native action observed in this trace" in report.gaps


def test_observation_without_gateway_has_no_enforcement_coverage() -> None:
    report = assess_agent_coverage(observation(commands=1))
    assert report.action_coverage == "unsupported"
    assert report.gateway_journal_root is None
    assert report.gateway_requests == 0
