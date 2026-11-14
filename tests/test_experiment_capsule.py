import json
from pathlib import Path

import pytest

from sentinel_replay.experiment_capsule import comparison_view, export_experiment
from sentinel_replay.investigation import CapsuleInvestigation

RESULT = (
    Path(__file__).resolve().parents[1] / "benchmarks/results/isolated-branches-final-2026-11-13"
)


def test_portable_comparison_derives_scores_from_exact_nested_reports(tmp_path: Path) -> None:
    capsule = tmp_path / "experiment.sentinel"
    receipt = export_experiment(RESULT, capsule)
    view = comparison_view(CapsuleInvestigation(capsule.read_bytes()))
    assert receipt["branches"] == 9
    assert len(view["branches"]) == 9
    assert view["frontier"] == ["deny_protected"]
    assert [row["task_completions"] for row in view["scores"]] == [3, 0, 3]
    assert len(view["world_diffs"]) == 6
    investigation = CapsuleInvestigation(capsule.read_bytes())
    comparison = json.loads(investigation.artifacts["comparison.json"])
    comparison["branches"][0]["report"]["independent_effects"]["protected_outputs"] = []
    investigation.artifacts["comparison.json"] = json.dumps(comparison).encode()
    with pytest.raises(ValueError, match="nested branch"):
        comparison_view(investigation)
