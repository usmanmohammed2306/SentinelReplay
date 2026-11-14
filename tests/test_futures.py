from pathlib import Path

import pytest

from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.futures import simulate_future
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Policy


def test_simulated_future_preserves_verified_prefix_then_changes_only_declared_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = Pack(
        name="fork-test",
        files={},
        steps=(
            PackStep(action=Action(operation="write_file", resource="first.txt"), value="first"),
            PackStep(action=Action(operation="write_file", resource="last.txt"), value="last"),
        ),
    )
    source = tmp_path / "source"
    record_pack(pack, source, Policy(), decisions=["allowed"] * 2, decision_source="test_fixture")
    capsule = tmp_path / "original.sentinel"
    export_pack(source, capsule)
    # Mock only this unit's evaluator boundary, not measured enforcement evidence.
    monkeypatch.setattr("sentinel_replay.futures.evaluate_batch", lambda *a, **k: ["denied"] * 2)
    investigation = CapsuleInvestigation(capsule.read_bytes())
    result = simulate_future(investigation, Policy(), tmp_path / "future", fork_step=1)
    assert result["mode"] == "DETERMINISTIC_SIMULATION"
    assert result["verified_prefix"]["complete_run"] is False
    assert result["first_policy_decision_divergence"] == 1
    assert [row["path"] for row in result["world_diff"]] == ["last.txt"]
    assert (tmp_path / "future/branch/world/first.txt").read_text() == "first"
    assert not (tmp_path / "future/branch/world/last.txt").exists()
    assert result["future_replay"]["final_state_verified"]
    with pytest.raises(ValueError, match="outside"):
        simulate_future(investigation, Policy(), tmp_path / "invalid", fork_step=3)
