import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.environment_pack import Pack, PackStep
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.policy_language import Action, Policy, Rule


def test_product_cli_records_signed_pack_exports_imports_replays_and_localizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real OPA has a separate guarded conformance suite. This test exercises the
    # installed command surface and actual portable restore/effect path.
    monkeypatch.setattr(
        "sentinel_replay.environment_pack.evaluate_batch",
        lambda policy, actions: ["allowed"] * len(actions),
    )
    agent = tmp_path / "agent"
    agent.mkdir()
    private, _ = create_keypair(tmp_path / "keys", agent)
    program = tmp_path / "program.json"
    program.write_text(
        Pack(
            name="cli",
            files={"public.txt": "public"},
            steps=(
                PackStep(action=Action(operation="read_file", resource="public.txt")),
                PackStep(action=Action(operation="write_file", resource="report.txt"), from_step=0),
            ),
        ).model_dump_json()
    )
    policy = tmp_path / "policy.json"
    policy.write_text(Policy(rules=(Rule(effect="allow"),)).model_dump_json())
    runner = CliRunner()
    recorded = runner.invoke(
        app,
        [
            "record",
            "--program",
            str(program),
            "--policy",
            str(policy),
            "--output",
            str(tmp_path / "recorded"),
            "--signing-key",
            str(private),
            "--anchor-root",
            str(tmp_path / "protected"),
        ],
    )
    assert recorded.exit_code == 0, recorded.output
    capsule = tmp_path / "portable.sentinel"
    exported = runner.invoke(app, ["pack", "export", str(tmp_path / "recorded"), str(capsule)])
    assert exported.exit_code == 0, exported.output
    replay = runner.invoke(app, ["replay", str(capsule), "--output", str(tmp_path / "replayed")])
    assert replay.exit_code == 0 and "VERIFIED_REPLAY" in replay.output, replay.output
    result = json.loads((tmp_path / "replayed/replay-report.json").read_text())
    assert result["final_state_verified"] and result["live_nondeterministic_calls"] == 0
    localized = runner.invoke(
        app,
        [
            "bisect",
            str(capsule),
            "--output",
            str(tmp_path / "bisected"),
            "--predicate",
            "file_exists:report.txt",
        ],
    )
    assert localized.exit_code == 0 and "first=2" in localized.output, localized.output
    refused = runner.invoke(
        app, ["record", "--adapter", "uncovered-shell", "--output", str(tmp_path / "unsafe")]
    )
    assert refused.exit_code == 2 and not (tmp_path / "unsafe").exists()
