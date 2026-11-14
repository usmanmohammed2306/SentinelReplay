"""Fail-closed local release evidence audit, separate from learner acceptance.

Hash consistency proves the supplied bytes, not the truth of an operator's review.
Review receipts remain declared external evidence and are labeled accordingly.
This command never publishes, accepts a learning slice or deploys anything.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.release_quality import quality_checks, valid_corpus, valid_demo


def load_report_json(text: str) -> Any:
    """Measurements permit finite decimals; canonical event data still forbids floats."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate report key")
            result[key] = value
        return result

    def decimal(value: str) -> Decimal:
        if len(value) > 128:
            raise ValueError("report number exceeds budget")
        return Decimal(value)

    def invalid(value: str) -> None:
        raise ValueError("nonfinite report number")

    try:
        result = json.loads(
            text, object_pairs_hook=unique, parse_float=decimal, parse_constant=invalid
        )
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 64:
                raise ValueError("report nesting exceeds budget")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
        return result
    except RecursionError as error:
        raise ValueError("report nesting exceeds parser budget") from error


REQUIRED = (
    "local_tests",
    "guarded_tests",
    "ui_build",
    "browser_tests",
    "product_demo",
    "corpus",
    "policy_search",
    "scale",
    "recording_overhead",
    "deployment_recovery",
    "postgres_http",
    "proof_video",
    "operational_validation",
    "provenance_validation",
)
REVIEWS = (
    "independent_provenance",
    "representative_recording_overhead",
    "end_to_end_load_and_latency",
    "clean_room_reproduction",
    "signer_boundary_and_freshness",
    "hosted_ci",
    "license_and_distribution",
    "owner_teach_back",
)


def source_inventory(root: Path) -> dict[str, str]:
    patterns = (
        "src/**/*.py",
        "migrations/**/*.py",
        "tests/*.py",
        "tests/fixtures/**/*",
        "scripts/*.py",
        "benchmarks/*.py",
        "ui/src/**/*.ts",
        "ui/src/**/*.tsx",
        "ui/src/**/*.css",
        "ui/scripts/*",
        "ui/tests/*.ts",
        "ui/*.json",
        "ui/*.ts",
        "ui/pnpm-lock.yaml",
        "Dockerfile",
        "ui/Dockerfile",
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        "alembic.ini",
        "deploy/local/compose.yaml",
        "deploy/local/.env.example",
        "deploy/local/**/*.sh",
        ".dockerignore",
        "ui/.dockerignore",
        ".github/workflows/*.yml",
        "docs/FROZEN_PRODUCT_CHARTER.md",
        "docs/SCOPE_TRACEABILITY.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    )
    files = sorted({path for pattern in patterns for path in root.glob(pattern) if path.is_file()})
    if any(path.is_symlink() for path in files):
        raise ValueError("source inventory contains a symlink")
    return {str(path.relative_to(root)): blob_digest(path.read_bytes()) for path in files}


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(min_length=1, max_length=1024)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _bytes(root: Path, reference: EvidenceRef) -> bytes:
    path = root / reference.path
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("release evidence escapes repository or is a symlink")
    with path.open("rb") as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or blob_digest(data) != reference.digest:
        raise ValueError("release evidence digest or byte budget differs")
    return data


def audit_release(repository: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_json_unique(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError("release manifest must be an object")
    sources = manifest.get("source_files", {})
    if not isinstance(sources, dict) or not sources:
        raise ValueError("release audit requires a nonempty frozen source inventory")
    source_root = event_digest(sources)
    source_failures = sorted(set(source_inventory(repository)) ^ set(sources))
    for path, digest in sources.items():
        try:
            _bytes(repository, EvidenceRef(path=path, digest=digest))
        except (OSError, ValueError):
            source_failures.append(path)
    artifacts, gates = manifest.get("artifacts", {}), {}
    reports: dict[str, dict[str, Any]] = {}
    for name in REQUIRED:
        try:
            value = load_report_json(
                _bytes(repository, EvidenceRef.model_validate(artifacts[name])).decode()
            )
            if not isinstance(value, dict):
                raise ValueError("release report must be a JSON object")
            reports[name] = value
            if name in {"local_tests", "guarded_tests", "ui_build"}:
                passed = (
                    value.get("exit_code") == 0
                    and value.get("source_root") == source_root
                    and bool(value.get("command"))
                )
            elif name == "browser_tests":
                stats = value["stats"]
                passed = (
                    stats["expected"] >= 3
                    and stats["unexpected"] == 0
                    and stats["flaky"] == 0
                    and not value["errors"]
                )
            elif name == "product_demo":
                passed = valid_demo(value)
            elif name == "corpus":
                passed = valid_corpus(value)
            elif name == "policy_search":
                passed = (
                    not value["partial"]
                    and not value["failures"]
                    and len(value["scores"]) >= 3
                    and bool(value["frontier"])
                )
            elif name == "scale":
                passed = {
                    row["target_boundaries"] for row in value["attempts"] if row["completed"]
                } == {3000, 10000, 50000} and all(
                    row["selected_graph"]["n"] >= 25 for row in value["attempts"]
                )
            elif name == "recording_overhead":
                passed = (
                    value["trials"] >= 10
                    and len(value["samples"]) == value["trials"]
                    and value["localization"]["linear_restores"] > 0
                )
            elif name == "deployment_recovery":
                passed = (
                    value["completed"]
                    and all(value["cleanup"].values())
                    and value["checks"]["restored"]["three_adapter_replay"]
                    and value["checks"]["stopped_writer_encrypted_backup"]
                )
            elif name == "postgres_http":
                passed = (
                    value["completed"]
                    and value["container_removed"]
                    and value["postgres_integration_passed"]
                    and not value["api_role"]["update"]
                    and not value["api_role"]["delete"]
                )
            elif name == "operational_validation":
                passed = (
                    value["completed"] is True
                    and value["failure_recovery_verified"] is True
                    and value["bounded_resources_verified"] is True
                    and value["declared_capacity"] >= 1
                )
            elif name == "provenance_validation":
                passed = (
                    value["scope"] == "frozen_synthetic_dependency_review"
                    and value["case_denominator"] == 12
                    and value["unknown_cases"] == ["uncaptured_side_effect"]
                    and bool(value["label_evidence"])
                )
                for item in value["label_evidence"]:
                    _bytes(repository, EvidenceRef.model_validate(item))
            else:
                video = _bytes(repository, EvidenceRef.model_validate(value["video"]))
                passed = (
                    value["continuous_capture"]
                    and 74.0 <= value["duration_seconds"] <= 77.0
                    and len(video) > 10000
                    and value["journal_root"]
                    == load_report_json(
                        _bytes(
                            repository, EvidenceRef.model_validate(artifacts["product_demo"])
                        ).decode()
                    )["journal_root"]
                )
            gates[name] = {"passed": bool(passed), "evidence": artifacts[name]}
        except (OSError, ValueError, TypeError, KeyError) as error:
            gates[name] = {
                "passed": False,
                "reason": type(error).__name__ + ": missing, changed or invalid evidence",
            }
    reviews = {}
    for name in REVIEWS:
        try:
            ref = EvidenceRef.model_validate(manifest.get("reviews", {})[name])
            review = load_json_unique(_bytes(repository, ref).decode())
            if (
                review["source_root"] != source_root
                or review["decision"] != "accepted"
                or not review["reviewer"]
                or not review["evidence"]
            ):
                raise ValueError("review is not accepted for these source bytes")
            for item in review["evidence"]:
                _bytes(repository, EvidenceRef.model_validate(item))
            reviews[name] = {
                "state": "DECLARED_EXTERNAL_REVIEW",
                "reviewer": review["reviewer"],
                "evidence": ref.model_dump(),
            }
        except (OSError, ValueError, TypeError, KeyError):
            reviews[name] = {"state": "PENDING"}
    budgets = quality_checks(reports)
    bindings = {}
    for name in REQUIRED:
        try:
            reference = EvidenceRef.model_validate(manifest["execution_receipts"][name])
            receipt = load_json_unique(_bytes(repository, reference).decode())
            log = EvidenceRef.model_validate(receipt["log"])
            _bytes(repository, log)
            passed = (
                receipt["source_root_before"] == source_root
                and receipt["source_root_after"] == source_root
                and receipt["exit_code"] == 0
                and bool(receipt["command"])
                and receipt["artifact"] == artifacts[name]
            )
            bindings[name] = {"passed": passed, "receipt": reference.model_dump()}
        except (OSError, ValueError, TypeError, KeyError):
            bindings[name] = {"passed": False, "reason": "missing current-source execution receipt"}
    traceability = {}
    rows = manifest.get("traceability", [])
    if isinstance(rows, list) and len(rows) == 43:
        for row in rows:
            try:
                identifier = row["section"]
                if type(identifier) is not int or identifier not in range(1, 44):
                    raise ValueError("unknown scope section")
                if str(identifier) in traceability:
                    raise ValueError("duplicate scope section")
                if not row["evidence"] or not row["checks"] or not row["title"]:
                    raise ValueError("empty scope evidence")
                for item in row["evidence"]:
                    _bytes(repository, EvidenceRef.model_validate(item))
                checks = {**gates, **budgets}
                passed = row["state"] == "verified" and all(
                    checks[name]["passed"] for name in row["checks"]
                )
                traceability[str(identifier)] = {"passed": passed, "title": row["title"]}
            except (OSError, ValueError, TypeError, KeyError):
                traceability["invalid"] = {"passed": False}
    for identifier in range(1, 44):
        traceability.setdefault(
            str(identifier), {"passed": False, "reason": "missing scope evidence"}
        )
    complete = (
        not source_failures
        and all(row["passed"] for row in gates.values())
        and all(row["passed"] for row in budgets.values())
        and all(row["passed"] for row in bindings.values())
        and len(traceability) == 43
        and all(row["passed"] for row in traceability.values())
        and all(row["state"] != "PENDING" for row in reviews.values())
    )
    return {
        "schema_version": 2,
        "source_root": source_root,
        "source_mismatches": source_failures,
        "engineering_checks": gates,
        "quality_budgets": budgets,
        "current_source_execution": bindings,
        "scope_traceability": traceability,
        "review_gates": reviews,
        "status": "READY_FOR_RELEASE_REVIEW" if complete else "RELEASE_BLOCKED",
        "accepted_student_slices": "unchanged_by_this_command",
        "limitation": (
            "Local artifact audit and declared reviews; not independent validation of reviewer "
            "identity, publication, latest-root freshness or a production safety guarantee."
        ),
    }
