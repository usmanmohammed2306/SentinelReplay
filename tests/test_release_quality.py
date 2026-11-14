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
    recording_diagnostics,
    recording_statistics,
    valid_corpus,
    valid_demo,
)


def distribution(seconds: str) -> dict[str, Any]:
    value = Decimal(seconds)
    return {"n": 25, "samples_seconds": [value] * 25, "p50_seconds": value, "p95_seconds": value}


def recording_report() -> dict[str, Any]:
    recorded, unrecorded = Decimal("0.5"), Decimal("0.04985")
    return {
        "schema_version": 2,
        "qualification_profile": "adr-0004-fixed-stub-v1",
        "progress_signing": "not_enabled_in_either_arm",
        "trials": 25,
        "program_steps": 3000,
        "median_overhead_percent": 100 * (recorded / unrecorded - 1),
        "recording_summary": {
            "p95_recorded_seconds": recorded,
            "median_added_seconds_per_boundary": Decimal("0.00015"),
        },
        "samples": [
            {
                "trial": i,
                "order": ["unrecorded", "recorded"] if i % 2 == 0 else ["recorded", "unrecorded"],
                "recorded_seconds": recorded,
                "unrecorded_seconds": unrecorded,
                "journal_records": 3001,
                "unrecorded_boundary_calls": 3001,
            }
            for i in range(25)
        ],
    }


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
        "recording_overhead": recording_report(),
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


def test_approved_absolute_budgets_are_inclusive_without_hiding_relative_failure() -> None:
    values = reports()
    checks = quality_checks(values)
    assert all(row["passed"] for row in checks.values())
    legacy = recording_diagnostics(values)["legacy_recording_overhead_20pct"]
    assert legacy["passed"] is False
    assert legacy["binding"] is False
    assert legacy["superseded_by"] == "ADR-0004"


@pytest.mark.parametrize("field", ["journal_records", "unrecorded_boundary_calls"])
def test_inflated_or_boolean_record_denominator_cannot_pass(field: str) -> None:
    for invalid in (3000, 3002, 10**9, True):
        values = reports()
        values["recording_overhead"]["samples"][0][field] = invalid
        checks = quality_checks(values)
        assert not checks["recording_latency_3k"]["passed"]
        assert not checks["recording_added_time_per_boundary"]["passed"]


def test_recording_p95_detects_tail_slowdown_even_when_median_is_unchanged() -> None:
    values = reports()
    r = values["recording_overhead"]
    r["samples"][-1]["recorded_seconds"] = Decimal("0.6")
    # One outlier in 25 is beyond the nearest-rank p95; still publish it.
    assert quality_checks(values)["recording_latency_3k"]["passed"]
    r["samples"][-2]["recorded_seconds"] = Decimal("0.6")
    r["recording_summary"]["p95_recorded_seconds"] = Decimal("0.6")
    checks = quality_checks(values)
    assert not checks["recording_latency_3k"]["passed"]
    assert checks["recording_added_time_per_boundary"]["passed"]


def test_added_time_has_its_own_budget_and_does_not_use_ratio_of_medians() -> None:
    values = reports()
    r = values["recording_overhead"]
    for row in r["samples"]:
        row["recorded_seconds"], row["unrecorded_seconds"] = Decimal("0.49"), Decimal("0.01")
    r["median_overhead_percent"] = 4800
    r["recording_summary"] = {
        "p95_recorded_seconds": Decimal("0.49"),
        "median_added_seconds_per_boundary": Decimal("0.48") / 3001,
    }
    checks = quality_checks(values)
    assert checks["recording_latency_3k"]["passed"]
    assert not checks["recording_added_time_per_boundary"]["passed"]


@pytest.mark.parametrize(
    "mutation", ["short", "trial", "order", "ratio", "p95", "added", "profile", "signing"]
)
def test_missing_or_forged_recording_qualification_fails_closed(mutation: str) -> None:
    values = reports()
    r = values["recording_overhead"]
    if mutation == "short":
        r["samples"].pop()
        r["trials"] = len(r["samples"])
    elif mutation == "trial":
        r["samples"][-1]["trial"] = 0
    elif mutation == "order":
        r["samples"][0]["order"] = ["recorded", "unrecorded"]
    elif mutation == "ratio":
        r["median_overhead_percent"] = 1
    elif mutation == "p95":
        r["recording_summary"]["p95_recorded_seconds"] = Decimal("0.01")
    elif mutation == "added":
        r["recording_summary"]["median_added_seconds_per_boundary"] = 0
    elif mutation == "profile":
        r.pop("qualification_profile")
    else:
        r["progress_signing"] = "pretend_signed"
    checks = quality_checks(values)
    assert not checks["recording_latency_3k"]["passed"]
    assert not checks["recording_added_time_per_boundary"]["passed"]


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


def test_pair_medians_are_not_replaced_by_ratios_or_differences_of_medians() -> None:
    values = recording_report()
    pairs = [("0.4", "0.01")] * 9 + [("0.5", "0.2")] * 9 + [("0.3", "0.25")] * 7
    for row, (recorded, unrecorded) in zip(values["samples"], pairs, strict=True):
        row["recorded_seconds"] = Decimal(recorded)
        row["unrecorded_seconds"] = Decimal(unrecorded)
    values["median_overhead_percent"] = 150
    values["recording_summary"] = {
        "p95_recorded_seconds": Decimal("0.5"),
        "median_added_seconds_per_boundary": Decimal("0.3") / 3001,
    }
    observed = recording_statistics(values)
    assert observed["median_relative_overhead_percent"] == 150
    assert observed["median_added_seconds_per_boundary"] == Decimal("0.3") / 3001
    assert observed["median_added_seconds_per_boundary"] != Decimal("0.2") / 3001


@pytest.mark.parametrize("value", [True, "0.00015", None, float("nan"), float("inf")])
def test_invalid_summary_types_do_not_qualify_recording(value: Any) -> None:
    values = reports()
    values["recording_overhead"]["recording_summary"]["median_added_seconds_per_boundary"] = value
    assert not quality_checks(values)["recording_latency_3k"]["passed"]


def test_old_measurements_retain_diagnostic_without_qualifying_new_budget() -> None:
    values = reports()
    old = values["recording_overhead"]
    old["samples"] = old["samples"][:10]
    old["trials"] = 10
    old["schema_version"] = 1
    old.pop("qualification_profile")
    assert not quality_checks(values)["recording_latency_3k"]["passed"]
    diagnostic = recording_diagnostics(values)["legacy_recording_overhead_20pct"]
    assert diagnostic["binding"] is False
    assert diagnostic["passed"] is False
    assert Decimal(diagnostic["observed"]) > 20
