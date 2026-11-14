import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sentinel_replay.policy_search import pareto, search_policies


@given(st.lists(st.tuples(st.integers(0, 10), st.integers(0, 15), st.integers(0, 3)), max_size=50))
def test_frontier_contains_only_executed_nondominated_candidates(
    costs: list[tuple[int, int, int]],
) -> None:
    rows = [
        {
            "policy_digest": str(index),
            "feasible": True,
            "benign_tasks_lost": a,
            "rule_count": b,
            "unknown_cases": c,
        }
        for index, (a, b, c) in enumerate(costs)
    ]
    frontier = pareto(rows)
    for identifier in frontier:
        point = costs[int(identifier)]
        assert not any(
            all(a <= b for a, b in zip(other, point, strict=True)) and other != point
            for other in costs
        )
    assert set(frontier) <= {row["policy_digest"] for row in rows}


@pytest.mark.parametrize("field", ["legitimate_tasks", "supported_incident_baseline"])
def test_resume_does_not_trust_edited_score_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    # This fixture is not an OPA measurement; it only exercises receipt binding.
    monkeypatch.setattr(
        "sentinel_replay.policy_search.evaluate_batch",
        lambda policy, actions, **kwargs: ["allowed"] * len(actions),
    )
    result = search_policies(tmp_path / "search", max_candidates=1)
    assert len(result["scores"]) == 1
    assert result["partial"]
    progress = tmp_path / "search/progress.json"
    edited = json.loads(progress.read_text())
    edited["scores"][0][field] = 500
    progress.write_text(json.dumps(edited))
    with pytest.raises(ValueError, match="retained outcomes"):
        search_policies(tmp_path / "search", max_candidates=2, resume=True)
