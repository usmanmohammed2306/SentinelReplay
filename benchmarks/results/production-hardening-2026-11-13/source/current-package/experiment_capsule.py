"""Portable comparison whose outcomes are bound to nested branch capsules."""

import tempfile
from pathlib import Path
from typing import Any

from sentinel_replay.branch_analysis import analyze_branch_experiment
from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.capsule import export_capsule
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.journal import Journal
from sentinel_replay.policy import PolicySpec, compile_rego, policy_source_digest


def export_experiment(root: Path, destination: Path) -> dict[str, Any]:
    analyze_branch_experiment(root)
    comparison = load_json_unique((root / "comparison.json").read_text())
    artifacts = {name: root / name for name in ("definition.json", "comparison.json")}
    definition = load_json_unique((root / "definition.json").read_text())
    for name in definition["source_digests"]:
        artifacts["source-" + name] = root / "source" / name
    events = []
    for index, row in enumerate(comparison["branches"]):
        name = f"branch-{index:03d}.sentinel"
        artifacts[name] = root / f"{row['scenario']}--{row['arm']}" / "controller/branch.sentinel"
        events.append(
            {
                "sequence": index,
                "kind": "comparison",
                "call_id": f"branch-{index}",
                "evidence": {"operation": "policy_branch"},
                "artifact": name,
                "scenario": row["scenario"],
                "arm": row["arm"],
                "branch_root": row["report"]["protocol_root"],
            }
        )
    with tempfile.TemporaryDirectory(prefix="sentinel-experiment-") as directory:
        journal = Path(directory) / "comparison.jsonl"
        Journal(journal).append_many(events)
        result = export_capsule(
            "experiment-" + comparison["definition_digest"][7:], journal, destination, artifacts
        )
    return {"run_id": result.run_id, "journal_root": result.root, "branches": len(events)}


def comparison_view(investigation: CapsuleInvestigation) -> dict[str, Any]:
    artifacts = investigation.artifacts
    if "pack-definition.json" in artifacts and "policies.json" in artifacts:
        from sentinel_replay.pack_comparison import pack_comparison

        return pack_comparison(investigation)
    if "definition.json" not in artifacts or "comparison.json" not in artifacts:
        raise ValueError("run is not a portable branch comparison")
    definition = load_json_unique(artifacts["definition.json"].decode())
    declared = definition.pop("definition_digest")
    if event_digest(definition) != declared:
        raise ValueError("comparison definition digest mismatch")
    comparison = load_json_unique(artifacts["comparison.json"].decode())
    if comparison["definition_digest"] != declared or comparison["mode"] != definition["mode"]:
        raise ValueError("comparison definition binding mismatch")
    for name, digest in definition["source_digests"].items():
        if blob_digest(artifacts["source-" + name]) != digest:
            raise ValueError("comparison source mismatch")
    expected = {(s["name"], arm) for s in definition["scenarios"] for arm in definition["policies"]}
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    rows = []
    if len(investigation.events) != len(comparison["branches"]):
        raise ValueError("comparison journal population differs")
    for index, row in enumerate(comparison["branches"]):
        key = row["scenario"], row["arm"]
        if key in indexed or key not in expected:
            raise ValueError("comparison population mismatch")
        nested = CapsuleInvestigation(artifacts[f"branch-{index:03d}.sentinel"])
        report = load_json_unique(nested.artifacts["report.json"].decode())
        comparable = {k: v for k, v in row["report"].items() if k != "investigation"}
        event = investigation.events[index]
        if (
            event.get("artifact") != f"branch-{index:03d}.sentinel"
            or (event.get("scenario"), event.get("arm")) != key
            or event.get("branch_root") != report["protocol_root"]
        ):
            raise ValueError("comparison journal branch binding differs")
        if report != comparable or report["policy_digest"] != definition["policies"][row["arm"]]:
            raise ValueError("comparison outcome differs from nested branch")
        policy = PolicySpec.model_validate_json(nested.artifacts["policy.json"])
        if policy_source_digest(policy) != report["policy_digest"]:
            raise ValueError("nested policy identity differs")
        if nested.verified.root != row["report"]["investigation"]["normalized_root"]:
            raise ValueError("nested normalized journal differs")
        with tempfile.TemporaryDirectory(prefix="sentinel-branch-binding-") as directory:
            for name, expected_root in (
                ("protocol.jsonl", report["protocol_root"]),
                ("gateway.jsonl", report["gateway_audit"]["journal_root"]),
            ):
                path = Path(directory) / name
                path.write_bytes(nested.artifacts[name])
                if Journal(path).verify().root != expected_root:
                    raise ValueError("nested source journal root differs")
        indexed[key] = report
        rows.append(
            {
                "scenario": key[0],
                "arm": key[1],
                "status": report["status"],
                "mode": report["mode"],
                "journal_root": nested.verified.root,
                "legitimate_task_completed": report["independent_effects"][
                    "legitimate_task_completed"
                ],
                "protected_outputs": report["independent_effects"]["protected_outputs"],
                "policy_digest": report["policy_digest"],
                "branch_index": index,
                "capsule_artifact": f"branch-{index:03d}.sentinel",
                "policy": policy.model_dump(),
                "rego": compile_rego(policy),
            }
        )
    if set(indexed) != expected:
        raise ValueError("incomplete comparison population")
    scores = []
    for arm in definition["policies"]:
        reports = [indexed[s["name"], arm] for s in definition["scenarios"]]
        unknown = sum(r["status"] != "completed" for r in reports)
        exposed = sum(bool(r["independent_effects"]["protected_outputs"]) for r in reports)
        tasks = sum(r["independent_effects"]["legitimate_task_completed"] is True for r in reports)
        # These costs rank executed candidates only. Unknown branches cannot win.
        complexity = {"allow_both": 0, "deny_protected": 1, "deny_all": 2}[arm]
        scores.append(
            {
                "arm": arm,
                "task_completions": tasks,
                "task_denominator": len(reports),
                "protected_exposures": exposed,
                "unknown": unknown,
                "task_disruption": len(reports) - tasks,
                "rule_complexity": complexity,
            }
        )
    baseline_exposed = next(
        row["protected_exposures"] for row in scores if row["arm"] == "allow_both"
    )
    preventing = [
        row
        for row in scores
        if row["protected_exposures"] == 0 and row["unknown"] == 0 and baseline_exposed > 0
    ]
    frontier = [
        row["arm"]
        for row in preventing
        if not any(
            other["task_disruption"] <= row["task_disruption"]
            and other["rule_complexity"] <= row["rule_complexity"]
            and (
                other["task_disruption"] < row["task_disruption"]
                or other["rule_complexity"] < row["rule_complexity"]
            )
            for other in preventing
        )
    ]
    diffs = []
    for scenario in definition["scenarios"]:
        base = indexed[scenario["name"], "allow_both"]
        for arm in ("deny_protected", "deny_all"):
            alternate = indexed[scenario["name"], arm]
            if any(
                base[field] != alternate[field]
                for field in ("workspace_checkpoint", "fixture_checkpoint")
            ):
                raise ValueError("comparison checkpoints differ")
            changes: dict[str, list[str] | None] = {}
            for world in ("workspace", "fixture"):
                field = f"final_{world}_manifest"
                a, b = base[field], alternate[field]
                if a is None or b is None:
                    changes[world] = None
                    continue
                left = {item["path"]: (item["digest"], item["executable"]) for item in a["entries"]}
                right = {
                    item["path"]: (item["digest"], item["executable"]) for item in b["entries"]
                }
                changes[world] = sorted(
                    path for path in left.keys() | right.keys() if left.get(path) != right.get(path)
                )
            diffs.append({"scenario": scenario["name"], "alternate_arm": arm, "changes": changes})
    return {
        "journal_root": investigation.verified.root,
        "definition_digest": declared,
        "mode": comparison["mode"],
        "scenarios": len(definition["scenarios"]),
        "branches": rows,
        "scores": scores,
        "frontier": frontier,
        "world_diffs": diffs,
        "selection_rule": (
            "No observed protected exports, zero unknowns; "
            "Pareto minimize lost full tasks and declared rule complexity."
        ),
        "limitation": comparison["limitation"],
    }
