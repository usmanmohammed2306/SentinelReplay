"""Read retained branches and publish denominators, cost and byte-level differences."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.capsule import read_capsule_bytes, verify_capsule_bytes, verify_imported
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.gateway_audit import audit_gateway_journal
from sentinel_replay.journal import Journal


def _changed(left: dict[str, Any] | None, right: dict[str, Any] | None) -> list[str] | None:
    if left is None or right is None:
        return None
    a = {row["path"]: (row["digest"], row["executable"]) for row in left["entries"]}
    b = {row["path"]: (row["digest"], row["executable"]) for row in right["entries"]}
    return sorted(path for path in a.keys() | b.keys() if a.get(path) != b.get(path))


def analyze_branch_experiment(root: Path) -> dict[str, Any]:
    """Analyze already retained outcomes without model, policy or container calls."""
    definition = load_json_unique((root / "definition.json").read_text())
    declared = definition.pop("definition_digest")
    if event_digest(definition) != declared:
        raise ValueError("experiment definition digest mismatch")
    comparison = load_json_unique((root / "comparison.json").read_text())
    if comparison["definition_digest"] != declared:
        raise ValueError("comparison and definition differ")
    source_check = {
        name: blob_digest((root / "source" / name).read_bytes()) == digest
        for name, digest in definition["source_digests"].items()
    }
    if not all(source_check.values()):
        raise ValueError("archived driver source mismatch")
    branches = comparison["branches"]
    expected = {
        (row["name"], arm) for row in definition["scenarios"] for arm in definition["policies"]
    }
    indexed = {(row["scenario"], row["arm"]): row["report"] for row in branches}
    if len(indexed) != len(branches) or set(indexed) != expected:
        raise ValueError("missing or duplicate branch population")
    diffs, costs = [], []
    for scenario in definition["scenarios"]:
        name = scenario["name"]
        baseline = indexed[name, "allow_both"]
        for arm in ("deny_protected", "deny_all"):
            alternate = indexed[name, arm]
            if (
                baseline["workspace_checkpoint"] != alternate["workspace_checkpoint"]
                or baseline["fixture_checkpoint"] != alternate["fixture_checkpoint"]
            ):
                raise ValueError("branches did not start from the same checkpoint")
            diffs.append(
                {
                    "scenario": name,
                    "alternate_arm": arm,
                    "workspace_paths_changed": _changed(
                        baseline["final_workspace_manifest"], alternate["final_workspace_manifest"]
                    ),
                    "fixture_paths_changed": _changed(
                        baseline["final_fixture_manifest"], alternate["final_fixture_manifest"]
                    ),
                    "baseline_effects": baseline["independent_effects"],
                    "alternate_effects": alternate["independent_effects"],
                }
            )
    for row in branches:
        controller = root / f"{row['scenario']}--{row['arm']}" / "controller"
        branch = row["report"]
        if Journal(controller / "protocol.jsonl").verify().root != branch["protocol_root"]:
            raise ValueError("raw protocol differs from reported root")
        audited = audit_gateway_journal(
            controller / "gateway.jsonl", expected_policy_digest=definition["policies"][row["arm"]]
        )
        if audited.journal_root != branch["gateway_audit"]["journal_root"]:
            raise ValueError("raw gateway differs from reported root")
        capsule_bytes = read_capsule_bytes(controller / "branch.sentinel")
        capsule = verify_capsule_bytes(capsule_bytes)
        if (
            capsule.root != branch["investigation"]["normalized_root"]
            or verify_imported(controller / "imported").root != capsule.root
        ):
            raise ValueError("capsule or imported evidence differs from investigation root")
        # Match the outcome to the exact verified archive, rather than trusting
        # the comparison's independently editable duplicate of the report.
        with zipfile.ZipFile(io.BytesIO(capsule_bytes)) as archive:
            archived_report_bytes = archive.read("artifacts/report.json")
            archived_report = load_json_unique(archived_report_bytes.decode())
        comparable = {key: value for key, value in branch.items() if key != "investigation"}
        if (
            archived_report != comparable
            or (controller / "report.json").read_bytes() != archived_report_bytes
            or (controller / "imported/artifacts/report.json").read_bytes() != archived_report_bytes
        ):
            raise ValueError("outcome report differs from the verified capsule")
        model_file = controller / "model-exchanges.json"
        requests = json.loads(model_file.read_text()) if model_file.exists() else []
        if model_file.exists() and event_digest(requests) != branch["model_exchange_digest"]:
            raise ValueError("model exchanges differ from reported digest")
        total_tokens = 0
        for record in requests:
            response = json.loads(record["raw_response"])
            total_tokens += response.get("usage", {}).get("total_tokens", 0)
        costs.append(
            {
                "scenario": row["scenario"],
                "arm": row["arm"],
                "model_requests": len(requests),
                "provider_reported_total_tokens": total_tokens,
                "elapsed_seconds": row["report"]["elapsed_seconds"],
            }
        )
    report = {
        "schema_version": 1,
        "mode": comparison["mode"],
        "definition_digest": declared,
        "archived_sources_verified": source_check,
        "population": {
            "scenarios": len(definition["scenarios"]),
            "policy_arms": len(definition["policies"]),
            "branches": len(branches),
        },
        "world_diffs": diffs,
        "observed_costs": costs,
        "limitation": (
            "One run per scenario/arm/seed. Provider-reported tokens and elapsed branch "
            "time are observations, not billing, repeated latency overhead, production "
            "SLOs or causal model-quality estimates."
        ),
    }
    (root / "analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
