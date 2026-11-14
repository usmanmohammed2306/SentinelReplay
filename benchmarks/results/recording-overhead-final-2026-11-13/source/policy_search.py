"""Resumable bounded deletion search; rank only actually executed policies.

The catalog is the frozen seed policy and its greedy one-rule-deletion
neighborhoods, plus allow-all and deny-all controls. Minimality is among tested
candidates on this known synthetic corpus, never global policy optimality.
"""

import json
import time
from pathlib import Path
from typing import Any

from sentinel_replay.canonical import event_digest
from sentinel_replay.environment_pack import record_pack
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.policy import PolicyUnavailable
from sentinel_replay.policy_language import Policy, evaluate_batch, policy_digest
from sentinel_replay.security_corpus import corpus_cases, incident_outcome, policies


def pareto(scores: list[dict[str, Any]]) -> list[str]:
    feasible = [row for row in scores if row["feasible"]]
    fields = ("benign_tasks_lost", "rule_count", "unknown_cases")
    return sorted(
        row["policy_digest"]
        for row in feasible
        if not any(
            all(other[field] <= row[field] for field in fields)
            and any(other[field] < row[field] for field in fields)
            for other in feasible
        )
    )


def search_policies(
    destination: Path,
    *,
    max_candidates: int = 128,
    time_budget_seconds: int = 600,
    resume: bool = False,
    opa_executable: Path | None = None,
) -> dict[str, Any]:
    if not 1 <= max_candidates <= 1000 or not 1 <= time_budget_seconds <= 600:
        raise ValueError("search budget must be1..1000 candidates and1..600 seconds")
    cases = corpus_cases()
    seeds = policies()
    definition: dict[str, Any] = {
        "schema_version": 1,
        "catalog": "controls_plus_greedy_single_rule_deletions_v1",
        "cases": [
            {"pack": case.pack.model_dump(), "predicate": case.predicate, "target": case.target}
            for case in cases
        ],
        "seed_policies": {name: policy.model_dump() for name, policy in seeds.items()},
        "costs": ["benign_tasks_lost", "rule_count", "unknown_cases"],
        "selection": (
            "Among feasible executed candidates, lexicographically minimize "
            "benign task loss, rule count and unknown cases; digest breaks ties."
        ),
        "source_digests": {
            name: blob_digest(Path(__file__).with_name(name).read_bytes())
            for name in (
                "policy_search.py",
                "security_corpus.py",
                "environment_pack.py",
                "policy_language.py",
            )
        },
        "evaluator": (
            {"kind": "native_OPA", "executable_digest": blob_digest(opa_executable.read_bytes())}
            if opa_executable is not None
            else {"kind": "pinned_network_disabled_Docker_OPA"}
        ),
    }
    digest = event_digest(definition)
    scores: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if resume:
        saved = json.loads((destination / "definition.json").read_text())
        if saved != json.loads(json.dumps(definition)):
            raise ValueError("search source, catalog or corpus changed; use a new directory")
        progress = json.loads((destination / "progress.json").read_text())
        if progress["definition_digest"] != digest:
            raise ValueError("search progress definition mismatch")
        scores, failures = progress["scores"], progress["failures"]
        baseline = next(
            (row["observed_incidents"] for row in scores if row["control"] == "allow_all"),
            None,
        )
        if len({row["policy_digest"] for row in scores}) != len(scores):
            raise ValueError("duplicate completed search candidate")
        for score in scores:
            receipt = destination / score["receipt"]
            relative = Path(score["receipt"])
            if (
                len(relative.parts) != 3
                or relative.parts[0] != score["policy_digest"].removeprefix("sha256:")
                or not relative.parts[1].startswith("attempt-")
                or relative.parts[2] != "receipt.json"
                or not receipt.resolve().is_relative_to(destination.resolve())
            ):
                raise ValueError("completed search receipt escapes its candidate")
            if blob_digest(receipt.read_bytes()) != score["receipt_digest"]:
                raise ValueError("completed search receipt changed")
            retained = json.loads(receipt.read_text())
            policy = Policy.model_validate(score["policy"])
            control = score["control"]
            if control not in {*seeds, "candidate"} or (
                control in seeds and policy != seeds[control]
            ):
                raise ValueError("completed search control differs from its frozen policy")
            case_names = [row["case"] for row in retained["cases"]]
            if len(case_names) != len(cases) or set(case_names) != {
                case.pack.name for case in cases
            }:
                raise ValueError("completed search corpus population differs")
            expected = {
                "policy_digest": policy_digest(policy),
                "observed_incidents": sum(row["incident"] is True for row in retained["cases"]),
                "unknown_cases": sum(row["incident"] is None for row in retained["cases"]),
                "benign_tasks_lost": sum(
                    row["predicate"] == "none" and not row["legitimate_task_completed"]
                    for row in retained["cases"]
                ),
                "legitimate_tasks": sum(
                    row["legitimate_task_completed"] for row in retained["cases"]
                ),
                "rule_count": len(policy.rules),
                "supported_incident_baseline": baseline,
            }
            feasible = (
                baseline is not None
                and baseline > 0
                and expected["observed_incidents"] == 0
                and all(
                    row["incident"] is not None
                    for row in retained["cases"]
                    if row["predicate"] not in {"none", "unsupported"}
                )
            )
            if (
                any(score[field] != value for field, value in expected.items())
                or score["feasible"] != feasible
                or retained["policy_digest"] != policy_digest(policy)
            ):
                raise ValueError("completed search score differs from retained outcomes")
            for row in retained["cases"]:
                source = receipt.parent / row["case"]
                report = json.loads((source / "report.json").read_text())
                from sentinel_replay.journal import Journal

                if (
                    report["journal_root"] != row["journal_root"]
                    or report["journal_root"] != Journal(source / "journal.jsonl").verify().root
                ):
                    raise ValueError("completed search journal changed")
    else:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        (destination / "definition.json").write_text(
            json.dumps(definition, indent=2, sort_keys=True) + "\n"
        )
        archive = destination / "source"
        archive.mkdir()
        for name in definition["source_digests"]:
            (archive / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    started = time.monotonic()
    stopped = False
    local_optimum = False
    baseline_count = next(
        (row["supported_incident_baseline"] for row in scores if row["control"] == "allow_all"),
        None,
    )
    evaluated = {row["policy_digest"]: row for row in scores}

    def persist() -> dict[str, Any]:
        frontier = pareto(scores)
        feasible = [row for row in scores if row["policy_digest"] in frontier]
        recommended = (
            min(
                feasible,
                key=lambda row: (
                    row["benign_tasks_lost"],
                    row["rule_count"],
                    row["unknown_cases"],
                    row["policy_digest"],
                ),
            )["policy_digest"]
            if feasible
            else None
        )
        result = {
            "schema_version": 1,
            "definition_digest": digest,
            "scores": scores,
            "failures": failures,
            "frontier": frontier,
            "recommended": recommended,
            "local_neighborhood_complete": local_optimum,
            "partial": not local_optimum,
            "max_candidates": max_candidates,
            "time_budget_seconds": time_budget_seconds,
            "selection": definition["selection"],
            "limitation": (
                "Known scripted corpus. Native-effect case remains unknown. "
                "No global minimality, blind attacks, live-agent efficacy "
                "or independent ground truth is claimed."
            ),
        }
        (destination / "progress.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        return result

    def evaluate(policy: Policy, control: str = "candidate") -> dict[str, Any] | None:
        nonlocal baseline_count, stopped
        identifier = policy_digest(policy)
        if identifier in evaluated:
            return evaluated[identifier]
        if (
            len(scores) + len(failures) >= max_candidates
            or time.monotonic() - started >= time_budget_seconds
        ):
            stopped = True
            return None
        directory = destination / identifier.removeprefix("sha256:")
        attempt = directory / f"attempt-{len(list(directory.glob('attempt-*'))):04d}"
        attempt.mkdir(mode=0o700, parents=True, exist_ok=False)
        (attempt / "policy.json").write_text(policy.model_dump_json(indent=2))
        rows = []
        try:
            actions = [step.action for case in cases for step in case.pack.steps]
            decisions = evaluate_batch(
                policy, actions, executable=str(opa_executable) if opa_executable else None
            )
            offset = 0
            for case in cases:
                count = len(case.pack.steps)
                source = attempt / case.pack.name
                report = record_pack(
                    case.pack,
                    source,
                    policy,
                    decisions=decisions[offset : offset + count],
                    decision_source="real_opa_batch_shared",
                )
                offset += count
                incident = incident_outcome(case, source, report)
                legitimate = (source / "world/report.txt").is_file() and (
                    source / "world/report.txt"
                ).read_text() == "public-report"
                rows.append(
                    {
                        "case": case.pack.name,
                        "predicate": case.predicate,
                        "incident": incident,
                        "legitimate_task_completed": legitimate,
                        "journal_root": report["journal_root"],
                    }
                )
        except (OSError, ValueError, PolicyUnavailable) as error:
            failures.append(
                {
                    "policy_digest": identifier,
                    "attempt": str(attempt.relative_to(destination)),
                    "error_type": type(error).__name__,
                }
            )
            stopped = True
            persist()
            return None
        incident_count = sum(row["incident"] is True for row in rows)
        if control == "allow_all":
            baseline_count = incident_count
        score = {
            "policy_digest": identifier,
            "control": control,
            "supported_incident_baseline": baseline_count,
            "observed_incidents": incident_count,
            "unknown_cases": sum(row["incident"] is None for row in rows),
            "benign_tasks_lost": sum(
                row["predicate"] == "none" and not row["legitimate_task_completed"] for row in rows
            ),
            "legitimate_tasks": sum(row["legitimate_task_completed"] for row in rows),
            "rule_count": len(policy.rules),
            "policy": policy.model_dump(mode="json"),
            "feasible": baseline_count is not None
            and baseline_count > 0
            and incident_count == 0
            and all(
                row["incident"] is not None
                for row in rows
                if row["predicate"] not in {"none", "unsupported"}
            ),
        }
        receipt = attempt / "receipt.json"
        receipt.write_text(
            json.dumps({"policy_digest": identifier, "cases": rows}, indent=2, sort_keys=True)
            + "\n"
        )
        score["receipt"] = str(receipt.relative_to(destination))
        score["receipt_digest"] = blob_digest(receipt.read_bytes())
        scores.append(score)
        evaluated[identifier] = score
        persist()
        return score

    persist()
    for control in ("allow_all", "deny_all", "targeted"):
        if evaluate(seeds[control], control) is None:
            return persist()
    current = seeds["targeted"]
    while not stopped:
        current_score = evaluated[policy_digest(current)]
        improvements = []
        for index in range(len(current.rules)):
            candidate = Policy(rules=current.rules[:index] + current.rules[index + 1 :])
            candidate_score = evaluate(candidate)
            if candidate_score is None:
                return persist()
            if (
                candidate_score["feasible"]
                and candidate_score["benign_tasks_lost"] <= current_score["benign_tasks_lost"]
            ):
                improvements.append(candidate)
        if not improvements:
            local_optimum = True
            break
        current = min(improvements, key=lambda value: (len(value.rules), policy_digest(value)))
    return persist()
