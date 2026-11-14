import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sentinel_replay.release_quality import (
    DEMO_CHECKS,
    number,
    quality_checks,
    valid_corpus,
    valid_demo,
)


def distribution(seconds: str) -> dict[str, Any]:
    value = Decimal(seconds)
    return {"n": 25, "samples_seconds": [value] * 25, "p50_seconds": value, "p95_seconds": value}


def reports() -> dict[str, dict[str, Any]]:
    return {
        "scale": {
            "attempts": [
                {
                    "target_boundaries": size,
                    "boundaries": size,
                    "completed": True,
                    "timeline_first_page": distribution("0.2"),
                    "timeline_tail_page": distribution("0.2"),
                    "selected_graph": distribution("0.2"),
                    "journal_verification": distribution("0.9"),
                }
                for size in (3000, 10000, 50000)
            ]
        },
        "recording_overhead": {
            "trials": 10,
            "program_steps": 3000,
            "median_overhead_percent": 20,
            "samples": [{"recorded_seconds": Decimal("1.2"), "unrecorded_seconds": 1}] * 10,
        },
        "operational_validation": {
            "timeline_interactive_after_data": {**distribution("0.9"), "boundaries": 3000}
        },
        "provenance_validation": {
            "true_positive": 4,
            "false_positive": 0,
            "false_negative": 0,
            "f1": 1,
            "case_denominator": 12,
            "review_status": "declared_independently_adjudicated",
            "reviewer": "unit-test-only-not-a-real-review",
            "unresolved_ambiguities": 0,
            "blast_radius_false_positive": 0,
            "blast_radius_false_negative": 0,
            "blast_radius_roots_reviewed": 11,
        },
    }


def test_numeric_budgets_are_inclusive_and_use_raw_samples() -> None:
    values = reports()
    assert all(row["passed"] for row in quality_checks(values).values())
    values["recording_overhead"]["samples"][0] = {"recorded_seconds": 50, "unrecorded_seconds": 1}
    # A single outlier does not change the declared median; twenty percent remains exact.
    assert quality_checks(values)["recording_overhead_3k"]["passed"]
    values["recording_overhead"]["samples"] = [
        {"recorded_seconds": 50, "unrecorded_seconds": 1}
    ] * 10
    values["recording_overhead"]["median_overhead_percent"] = 4900
    assert not quality_checks(values)["recording_overhead_3k"]["passed"]
    values["recording_overhead"]["median_overhead_percent"] = 1  # Fabricated summary.
    assert not quality_checks(values)["recording_overhead_3k"]["passed"]


def test_forged_quantile_missing_population_and_browser_budget_fail() -> None:
    values = reports()
    values["scale"]["attempts"][-1]["selected_graph"]["samples_seconds"][-1] = Decimal("5")
    values["scale"]["attempts"][-1]["selected_graph"]["samples_seconds"][-2] = Decimal("5")
    assert not quality_checks(values)["selected_graph_50k"]["passed"]
    values = reports()
    values["scale"]["attempts"].pop()
    assert not quality_checks(values)["timeline_first_page_3k"]["passed"]
    values["operational_validation"]["timeline_interactive_after_data"] = {
        **distribution("1.01"),
        "boundaries": 3000,
    }
    assert not quality_checks(values)["timeline_interactive_3k"]["passed"]
    assert all(not row["passed"] for row in quality_checks({}).values())


def test_provenance_requires_nonvacuous_consistent_counts_and_adjudication() -> None:
    values = reports()
    values["provenance_validation"]["false_negative"] = 4
    assert not quality_checks(values)["provenance_and_blast_radius"]["passed"]
    values["provenance_validation"]["f1"] = Decimal(2) / 3
    assert not quality_checks(values)["provenance_and_blast_radius"]["passed"]
    values = reports()
    values["provenance_validation"]["true_positive"] = 0
    assert not quality_checks(values)["provenance_and_blast_radius"]["passed"]
    values = reports()
    values["provenance_validation"]["blast_radius_false_positive"] = 1
    assert not quality_checks(values)["provenance_and_blast_radius"]["passed"]
    values = reports()
    values["provenance_validation"]["review_status"] = "same_implementer_injected_labels"
    assert not quality_checks(values)["provenance_and_blast_radius"]["passed"]


@pytest.mark.parametrize("value", [True, False, "1", None, float("nan"), float("inf"), -1])
def test_invalid_numbers_cannot_satisfy_a_budget(value: Any) -> None:
    with pytest.raises(ValueError):
        number(value)


def test_demo_requires_exact_named_checks_not_arbitrary_true_flags() -> None:
    value = {
        "status": "WORKFLOW_DEMO_PASS",
        "program_actions": 3000,
        "checks": dict.fromkeys(DEMO_CHECKS, True),
    }
    assert valid_demo(value)
    value["checks"] = dict.fromkeys(range(17), True)
    assert not valid_demo(value)


def test_corpus_rejects_duplicate_rows_and_unknown_as_prevention() -> None:
    root = Path(__file__).parent.parent
    value = json.loads(
        (
            root / "benchmarks/results/environment-pack-corpus-final-2026-11-13/results.json"
        ).read_text()
    )
    assert valid_corpus(value)
    duplicate = copy.deepcopy(value)
    duplicate["rows"][-1] = duplicate["rows"][0]
    assert not valid_corpus(duplicate)
    for row in value["rows"]:
        if row["case"] == "uncaptured_side_effect":
            row["incident"] = False
    assert not valid_corpus(value)
