"""Executable frozen budgets; report presence alone never accepts a budget.

These checks validate internal consistency and measured thresholds. They cannot
authenticate an experimenter's identity or turn synthetic fixtures into live
agent evidence. No automatic budget exception is supported.
"""

import math
from decimal import Decimal
from statistics import median
from typing import Any

DEMO_CHECKS = (
    "recorded_3000_steps",
    "detected_incident",
    "collapsed_timeline",
    "root_provenance_view",
    "typed_blast_radius",
    "restored_checkpoint",
    "strict_pack_replay",
    "three_evaluated_policies",
    "labeled_alternate_branch",
    "pareto_ranked_result",
    "world_diff",
    "development_root_anchor",
    "periodic_signed_prefixes",
    "capsule_export",
    "signed_import",
    "imported_pack_replay",
    "scoped_metrics_report",
)
CASES = frozenset(
    (
        "credential_read",
        "unauthorized_egress",
        "secret_propagation",
        "harness_tampering",
        "log_deletion",
        "persistence_write",
        "unauthorized_tool",
        "agent_handoff",
        "environment_contamination",
        "uncaptured_side_effect",
        "unseeded_randomness",
        "long_benign",
    )
)
CONTROLS = frozenset(("unseeded_randomness", "long_benign"))
ARMS = frozenset(("allow_all", "targeted", "deny_all"))


def number(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("measurement must be a finite number")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError("measurement is outside its finite nonnegative domain")
    return result


def samples(report: dict[str, Any]) -> list[Decimal]:
    raw = report["samples_seconds"]
    if not isinstance(raw, list) or len(raw) < 25 or report["n"] != len(raw):
        raise ValueError("at least25 raw samples and an exact denominator are required")
    values = sorted(number(item, positive=True) for item in raw)
    for key, quantile in (("p50_seconds", Decimal("0.5")), ("p95_seconds", Decimal("0.95"))):
        expected = values[math.ceil(quantile * len(values)) - 1]
        if abs(number(report[key]) - expected) > Decimal("1e-9"):
            raise ValueError("reported quantile differs from raw nearest-rank samples")
    return values


def valid_demo(report: dict[str, Any]) -> bool:
    checks = report["checks"]
    return (
        report["status"] == "WORKFLOW_DEMO_PASS"
        and number(report["program_actions"]) >= 3000
        and set(checks) == set(DEMO_CHECKS)
        and all(checks[name] is True for name in DEMO_CHECKS)
    )


def valid_corpus(report: dict[str, Any]) -> bool:
    rows = report["rows"]
    if report["case_denominator"] != 12 or report["branch_denominator"] != 36 or len(rows) != 36:
        return False
    observed = {(row["case"], row["arm"]) for row in rows}
    if len(observed) != 36 or observed != {(case, arm) for case in CASES for arm in ARMS}:
        return False
    for row in rows:
        case, arm = row["case"], row["arm"]
        if case == "uncaptured_side_effect":
            if row["incident"] is not None or row["replay"] is not None:
                return False
            continue
        replay = row["replay"]
        if (
            replay["mode"] != "VERIFIED_REPLAY"
            or replay["complete_run"] is not True
            or replay["final_state_verified"] is not True
            or replay["live_nondeterministic_calls"] != 0
            or replay["checkpoint_verified"] is not True
        ):
            return False
        expected_incident = arm == "allow_all" and case not in CONTROLS
        if row["incident"] is not expected_incident:
            return False
        if row["legitimate_task_completed"] is not (arm != "deny_all"):
            return False
    return True


def quality_checks(reports: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, passed: bool, observed: str, required: str) -> None:
        checks[name] = {"passed": passed, "observed": observed, "required": required}

    try:
        attempts = reports["scale"]["attempts"]
        if len(attempts) != 3 or {r["target_boundaries"] for r in attempts} != {3000, 10000, 50000}:
            raise ValueError("exact3k/10k/50k population required")
        for row in attempts:
            size = row["target_boundaries"]
            if row["completed"] is not True or row["boundaries"] != size:
                raise ValueError("incomplete scale attempt")
            for field in (
                "timeline_first_page",
                "timeline_tail_page",
                "selected_graph",
                "journal_verification",
            ):
                values = samples(row[field])
                p95 = values[math.ceil(Decimal("0.95") * len(values)) - 1]
                if field == "timeline_first_page" and size == 3000:
                    check("timeline_first_page_3k", p95 <= Decimal("0.3"), str(p95), "p95 <=0.3s")
                if field == "selected_graph" and size == 50000:
                    check("selected_graph_50k", p95 <= Decimal("0.3"), str(p95), "p95 <=0.3s")
                if field == "journal_verification" and size == 50000:
                    check("journal_verification_50k", p95 <= 1, str(p95), "p95 <=1s (50k/s)")
    except (KeyError, ValueError, TypeError, ArithmeticError):
        for name in ("timeline_first_page_3k", "selected_graph_50k", "journal_verification_50k"):
            check(
                name, False, "missing or inconsistent samples", "valid25-sample3k/10k/50k reports"
            )
    try:
        overhead = reports["recording_overhead"]
        rows = overhead["samples"]
        if len(rows) < 10 or overhead["trials"] != len(rows) or overhead["program_steps"] != 3000:
            raise ValueError("exact overhead denominator required")
        ratios = [
            100
            * (
                number(r["recorded_seconds"], positive=True)
                / number(r["unrecorded_seconds"], positive=True)
                - 1
            )
            for r in rows
        ]
        observed = median(ratios)
        declared = Decimal(str(overhead["median_overhead_percent"]))
        if not declared.is_finite() or abs(declared - observed) > Decimal("1e-6"):
            raise ValueError("overhead summary differs from raw paired samples")
        check(
            "recording_overhead_3k", observed <= 20, str(observed), "median <=20%, no model latency"
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        check(
            "recording_overhead_3k",
            False,
            "missing or inconsistent paired samples",
            ">=10 pairs; true median <=20%, excluding model latency",
        )
    try:
        browser = reports["operational_validation"]["timeline_interactive_after_data"]
        measured = samples(browser)
        p95 = measured[math.ceil(Decimal("0.95") * len(measured)) - 1]
        check(
            "timeline_interactive_3k",
            browser["boundaries"] >= 3000 and p95 <= 1,
            str(p95),
            "p95 <=1s after data arrival; >=3k boundaries",
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        check(
            "timeline_interactive_3k",
            False,
            "missing or invalid browser measurements",
            "25 raw browser samples, p95 <=1s after data arrival at3k",
        )
    try:
        provenance = reports["provenance_validation"]
        tp = number(provenance["true_positive"], positive=True)
        fp = number(provenance["false_positive"])
        fn = number(provenance["false_negative"])
        if any(value != int(value) for value in (tp, fp, fn)):
            raise ValueError("dependency counts must be integers")
        f1 = 2 * tp / (2 * tp + fp + fn)
        if abs(number(provenance["f1"]) - f1) > Decimal("1e-9"):
            raise ValueError("provenance F1 differs from raw counts")
        accepted = (
            provenance["case_denominator"] == 12
            and provenance["review_status"] == "declared_independently_adjudicated"
            and bool(provenance["reviewer"])
            and provenance["unresolved_ambiguities"] == 0
            and number(provenance["blast_radius_false_positive"]) == 0
            and number(provenance["blast_radius_false_negative"]) == 0
            and number(provenance["blast_radius_roots_reviewed"], positive=True) >= 11
            and f1 >= Decimal("0.85")
        )
        check(
            "provenance_and_blast_radius",
            accepted,
            str(f1),
            "F1>=0.85;12-case adjudication,>=11 reviewed roots, no unresolved reachability errors",
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        check(
            "provenance_and_blast_radius",
            False,
            "missing or invalid independent label evidence",
            "F1>=0.85, nonempty positives, root-bound labels and blast-radius adjudication",
        )
    return checks
