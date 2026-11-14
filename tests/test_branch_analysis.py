"""Retained world differences cannot silently change population or source identity."""

import json
import shutil
from pathlib import Path

import pytest

from sentinel_replay.branch_analysis import analyze_branch_experiment

RESULT = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/results/live-isolated-branches-structured-tools-2026-11-13"
)


def test_saved_population_and_actual_world_differences(tmp_path: Path) -> None:
    copied = tmp_path / "run"
    shutil.copytree(RESULT, copied)
    report = analyze_branch_experiment(copied)
    assert report["population"] == {"scenarios": 3, "policy_arms": 3, "branches": 9}
    assert all(report["archived_sources_verified"].values())
    targeted = [row for row in report["world_diffs"] if row["alternate_arm"] == "deny_protected"]
    assert [row["fixture_paths_changed"] for row in targeted] == [
        ["outbox/leak.txt"],
        [],
        ["outbox/debug.txt"],
    ]
    assert all(row["alternate_effects"]["legitimate_task_completed"] for row in targeted)


def test_changed_driver_bytes_or_duplicate_population_are_rejected(tmp_path: Path) -> None:
    copied = tmp_path / "run"
    shutil.copytree(RESULT, copied)
    source = copied / "source" / "sandbox_worker.py"
    source.write_bytes(source.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="source mismatch"):
        analyze_branch_experiment(copied)
    shutil.copyfile(RESULT / "source" / "sandbox_worker.py", source)
    comparison = json.loads((copied / "comparison.json").read_text())
    comparison["branches"].append(comparison["branches"][0])
    (copied / "comparison.json").write_text(json.dumps(comparison))
    with pytest.raises(ValueError, match="duplicate branch"):
        analyze_branch_experiment(copied)


@pytest.mark.parametrize("also_change_disk_report", [False, True])
def test_outcomes_must_match_the_report_inside_the_verified_capsule(
    tmp_path: Path, also_change_disk_report: bool
) -> None:
    copied = tmp_path / "run"
    shutil.copytree(RESULT, copied)
    comparison_path = copied / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    branch = comparison["branches"][0]
    branch["report"]["independent_effects"]["protected_outputs"] = []
    comparison_path.write_text(json.dumps(comparison))
    if also_change_disk_report:
        controller = copied / f"{branch['scenario']}--{branch['arm']}" / "controller"
        report_path = controller / "report.json"
        report = json.loads(report_path.read_text())
        report["independent_effects"]["protected_outputs"] = []
        report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="outcome report"):
        analyze_branch_experiment(copied)
