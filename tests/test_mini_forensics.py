import json
from pathlib import Path

from typer.testing import CliRunner

from sentinel_replay.boundary import BoundarySession
from sentinel_replay.cli import app
from sentinel_replay.mini_forensics import investigate_mini
from sentinel_replay.scripted_agent import run_scripted_agent


def _record_pair(root: Path) -> tuple[Path, Path]:
    incident = root / "incident.jsonl"
    benign = root / "benign.jsonl"
    run_scripted_agent(BoundarySession.record(incident), allow_live=True, scenario="incident")
    run_scripted_agent(BoundarySession.record(benign), allow_live=True, scenario="benign")
    return incident, benign


def test_mini_report_links_secret_read_to_egress_and_bounded_policy(tmp_path: Path) -> None:
    incident, benign = _record_pair(tmp_path)
    report = investigate_mini(incident, benign)

    assert report.mode == "TRACE_POLICY_EVALUATION"
    assert report.incident is not None
    assert report.incident.root_step == 2
    assert report.incident.egress_step == 3
    assert report.blast_radius == [3, 4]
    assert any(
        edge.kind == "dataflow" and edge.source == 2 and edge.target == 3 for edge in report.edges
    )
    assert report.frontier == ["deny_demo_host"]
    scores = {score.candidate: score for score in report.policies}
    assert scores["deny_demo_host"].prevents_recorded_action
    assert scores["deny_demo_host"].benign_actions_blocked == 0
    assert scores["deny_all_http_post"].benign_actions_blocked == 1
    assert "DEMO_TOKEN_001" not in json.dumps(report.to_dict())


def test_mini_report_does_not_invent_incident_for_benign_run(tmp_path: Path) -> None:
    _, benign = _record_pair(tmp_path)
    report = investigate_mini(benign, benign)
    assert report.incident is None
    assert report.blast_radius == []
    assert report.frontier == []


def test_mini_investigate_cli_writes_inspectable_redacted_report(tmp_path: Path) -> None:
    incident, benign = _record_pair(tmp_path)
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        app, ["mini", "investigate", str(incident), str(benign), "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert "TRACE_POLICY_EVALUATION" in result.stdout
    payload = json.loads(output.read_text())
    assert payload["incident"]["egress_step"] == 3
    assert payload["frontier"] == ["deny_demo_host"]
    assert "DEMO_TOKEN_001" not in output.read_text()
