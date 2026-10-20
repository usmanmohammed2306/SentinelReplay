from pathlib import Path

from typer.testing import CliRunner

from sentinel_replay.cli import app

runner = CliRunner()


def test_version_reports_development_build() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout == "Sentinel Replay 0.1.0-dev\n"


def test_unknown_command_fails_with_a_useful_message() -> None:
    result = runner.invoke(app, ["not-a-command"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_hash_event_and_journal_commands(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text('{"kind":"read","actor":"agent"}')
    journal = tmp_path / "run.jsonl"

    hashed = runner.invoke(app, ["hash-event", str(event)])
    appended = runner.invoke(app, ["journal", "append", str(journal), str(event)])
    verified = runner.invoke(app, ["journal", "verify", str(journal)])

    assert hashed.exit_code == 0 and hashed.stdout.startswith("sha256:")
    assert appended.exit_code == 0 and "records=1" in appended.stdout
    assert verified.exit_code == 0 and "CHAIN VALID records=1" in verified.stdout


def test_boundary_demo_record_and_replay(tmp_path: Path) -> None:
    recording = tmp_path / "boundary.jsonl"
    recorded = runner.invoke(app, ["boundary-demo", "--record", str(recording)])
    replayed = runner.invoke(app, ["boundary-demo", "--replay", str(recording)])

    assert recorded.exit_code == 0 and "RECORDED" in recorded.stdout
    assert replayed.exit_code == 0 and "BOUNDARY_REPLAY_MATCHED" in replayed.stdout


def test_scripted_agent_records_and_strictly_replays(tmp_path: Path) -> None:
    result = runner.invoke(app, ["demo-mini", str(tmp_path / "mini")])
    assert result.exit_code == 0
    assert "BOUNDARY_REPLAY_MATCHED scenario=incident" in result.stdout
    assert "BOUNDARY_REPLAY_MATCHED scenario=benign" in result.stdout
    assert "replays=2" in result.stdout
    assert (tmp_path / "mini" / "incident.jsonl").exists()
    assert (tmp_path / "mini" / "benign.jsonl").exists()


def test_mini_record_inspect_and_replay_without_exposing_response(tmp_path: Path) -> None:
    path = tmp_path / "incident.jsonl"
    recorded = runner.invoke(app, ["mini", "record", "incident", str(path)])
    inspected = runner.invoke(app, ["mini", "inspect", str(path)])
    replayed = runner.invoke(app, ["mini", "replay", "incident", str(path)])

    assert recorded.exit_code == 0 and "RECORDED scenario=incident actions=5" in recorded.stdout
    assert inspected.exit_code == 0 and "records=5" in inspected.stdout
    assert "network-post-1" in inspected.stdout
    assert "DEMO_TOKEN_001" not in inspected.stdout
    assert replayed.exit_code == 0 and "BOUNDARY_REPLAY_MATCHED" in replayed.stdout


def test_mini_replay_wrong_scenario_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "incident.jsonl"
    assert runner.invoke(app, ["mini", "record", "incident", str(path)]).exit_code == 0
    result = runner.invoke(app, ["mini", "replay", "benign", str(path)])
    assert result.exit_code != 0
    assert "mismatch" in result.output
