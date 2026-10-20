import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.boundary import BoundarySession
from sentinel_replay.cli import app
from sentinel_replay.journal import Journal, JournalCorruption
from sentinel_replay.scripted_agent import run_scripted_agent
from sentinel_replay.timeline import TimelineShapeError, compress_timeline


def _record(path: Path, scenario: str) -> None:
    run_scripted_agent(BoundarySession.record(path), allow_live=True, scenario=scenario)


def test_classifies_declared_secret_and_unapproved_egress_without_payload(tmp_path: Path) -> None:
    path = tmp_path / "incident.jsonl"
    _record(path, "incident")
    report = compress_timeline(path, approved_hosts=frozenset({"internal.demo.invalid"}))
    assert report.mode == "TRACE_CLASSIFICATION"
    assert report.actions == 5
    assert [(finding.step, finding.rule_id) for finding in report.findings] == [
        (2, "secret_read_v1"),
        (3, "unapproved_egress_v1"),
    ]
    assert "DEMO_TOKEN_001" not in json.dumps(report.to_dict())
    assert report.journal_root == Journal(path).verify().root


def test_network_violation_requires_an_explicit_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "incident.jsonl"
    _record(path, "incident")
    report = compress_timeline(path)
    assert [finding.rule_id for finding in report.findings] == ["secret_read_v1"]


def test_three_thousand_benign_actions_compress_to_one_phase(tmp_path: Path) -> None:
    path = tmp_path / "long.jsonl"
    Journal(path).append_many(
        {
            "sequence": index,
            "kind": "tool",
            "call_id": f"read-{index}",
            "evidence": {"operation": "read_file", "sensitivity": "public"},
            "response": {"private": "never print me"},
        }
        for index in range(3_000)
    )
    report = compress_timeline(path)
    assert report.actions == 3_000
    assert len(report.phases) == 1
    assert report.phases[0].first_step == 0
    assert report.phases[0].last_step == 2_999
    assert report.phases[0].actions == 3_000
    assert not report.findings
    assert "never print me" not in json.dumps(report.to_dict())


def test_malformed_metadata_fails_without_guessing(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    Journal(path).append({"sequence": 0, "evidence": {"operation": 123}})
    with pytest.raises(TimelineShapeError, match="non-string operation"):
        compress_timeline(path)


def test_corrupt_tail_never_returns_a_partial_timeline(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    Journal(path).append_many(
        {"sequence": index, "evidence": {"operation": "read_file"}} for index in range(3)
    )
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(JournalCorruption, match="record 3"):
        compress_timeline(path)


def test_cli_writes_redacted_report_and_rejects_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "incident.jsonl"
    _record(path, "incident")
    output = tmp_path / "timeline.json"
    runner = CliRunner()
    args = [
        "timeline",
        str(path),
        "--approved-host",
        "internal.demo.invalid",
        "--output",
        str(output),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "TRACE_CLASSIFICATION actions=5" in result.output
    data = json.loads(output.read_text())
    assert len(data["findings"]) == 2
    assert "DEMO_TOKEN_001" not in output.read_text()
    assert runner.invoke(app, args).exit_code != 0
