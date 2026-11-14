from pathlib import Path

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.policy_language import Action, Policy


def test_counted_binary_localization_agrees_with_actual_linear_restores(tmp_path: Path) -> None:
    steps = [PackStep(action=Action(operation="model_call")) for _ in range(32)]
    steps.insert(
        24,
        PackStep(action=Action(operation="write_file", resource="egress.txt"), value="synthetic"),
    )
    pack = Pack(name="bisect", files={}, steps=tuple(steps))
    record_pack(
        pack,
        tmp_path / "source",
        Policy(),
        decisions=["allowed"] * len(steps),
        decision_source="test_fixture",
    )
    result = localize_pack(
        tmp_path / "source",
        tmp_path / "localization",
        FilePredicate(kind="file_exists", path="egress.txt"),
    )
    assert result["first_true_prefix"] == 25
    assert result["incident_program_step"] == 24
    assert result["binary_restores"] < result["linear_restores"] == 26
    assert all(row["replay"]["final_state_verified"] for row in result["probes"])


def test_non_monotone_mutation_program_uses_linear_fallback(tmp_path: Path) -> None:
    pack = Pack(
        name="nonmonotone",
        files={},
        steps=(
            PackStep(action=Action(operation="write_file", resource="flag.txt"), value="yes"),
            PackStep(action=Action(operation="delete_file", resource="flag.txt")),
        ),
    )
    record_pack(
        pack,
        tmp_path / "source",
        Policy(),
        decisions=["allowed"] * 2,
        decision_source="test_fixture",
    )
    result = localize_pack(
        tmp_path / "source",
        tmp_path / "localization",
        FilePredicate(kind="file_exists", path="flag.txt"),
    )
    assert result["monotonicity"] == "unproven_linear_fallback"
    assert result["binary_restores"] == 0
    assert result["first_true_prefix"] == 1
