"""Deterministic, redacted phase compression over verified boundary metadata."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sentinel_replay.journal import Journal

MAX_TIMELINE_STEPS = 100_000
_OPERATIONS = {
    "read_file": "file_read",
    "write_file": "file_write",
    "delete_file": "file_delete",
    "http_get": "network_read",
    "http_post": "network_write",
    "handoff": "agent_handoff",
    "model_call": "model_call",
    "clock": "clock_read",
    "rng": "random_read",
}


class TimelineShapeError(ValueError):
    """Verified evidence does not match the supported boundary metadata schema."""


@dataclass(frozen=True)
class RuleFinding:
    step: int
    rule_id: str
    evidence: str


@dataclass(frozen=True)
class Phase:
    label: str
    first_step: int
    last_step: int
    actions: int
    finding_count: int


@dataclass(frozen=True)
class TimelineReport:
    mode: Literal["TRACE_CLASSIFICATION"]
    coverage: Literal["boundary_evidence_metadata_only"]
    journal_root: str
    actions: int
    phases: list[Phase]
    findings: list[RuleFinding]
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_string(metadata: dict[str, object], key: str, index: int) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TimelineShapeError(f"boundary {index} has non-string {key}")
    return value


def _step_metadata(event: object, index: int) -> tuple[str, str | None, str | None]:
    if not isinstance(event, dict):
        raise TimelineShapeError(f"boundary {index} is not an object")
    if "sequence" in event and (type(event["sequence"]) is not int or event["sequence"] != index):
        raise TimelineShapeError(f"boundary {index} has an invalid sequence")
    metadata = event.get("evidence")
    if not isinstance(metadata, dict) or not all(isinstance(key, str) for key in metadata):
        raise TimelineShapeError(f"boundary {index} lacks valid evidence metadata")
    operation = _optional_string(metadata, "operation", index)
    if operation is None:
        raise TimelineShapeError(f"boundary {index} lacks operation metadata")
    return (
        operation,
        _optional_string(metadata, "sensitivity", index),
        _optional_string(metadata, "host", index),
    )


def compress_timeline(
    journal_path: Path, *, approved_hosts: frozenset[str] | None = None
) -> TimelineReport:
    """Classify only supported metadata after verifying the entire journal chain."""
    findings: list[RuleFinding] = []
    phases: list[Phase] = []

    def visit(index: int, event: object) -> None:
        if index >= MAX_TIMELINE_STEPS:
            raise TimelineShapeError("journal exceeds timeline step limit")
        operation, sensitivity, host = _step_metadata(event, index)
        matches: list[RuleFinding] = []
        if operation == "read_file" and sensitivity == "secret":
            matches.append(
                RuleFinding(index, "secret_read_v1", "declared secret-classified file read")
            )
        if operation == "http_post" and approved_hosts is not None:
            if host is None:
                raise TimelineShapeError(f"boundary {index} lacks host for network policy")
            if host not in approved_hosts:
                matches.append(
                    RuleFinding(index, "unapproved_egress_v1", "host outside declared allowlist")
                )
        if operation == "delete_file" and sensitivity == "audit_log":
            matches.append(RuleFinding(index, "audit_log_delete_v1", "declared audit-log deletion"))
        findings.extend(matches)
        label = (
            "+".join(match.rule_id for match in matches)
            if matches
            else _OPERATIONS.get(operation, "other_action")
        )
        if phases and phases[-1].label == label:
            previous = phases[-1]
            phases[-1] = Phase(
                label,
                previous.first_step,
                index,
                previous.actions + 1,
                previous.finding_count + len(matches),
            )
        else:
            phases.append(Phase(label, index, index, 1, len(matches)))

    verified = Journal(journal_path).scan_verified(visit)
    return TimelineReport(
        mode="TRACE_CLASSIFICATION",
        coverage="boundary_evidence_metadata_only",
        journal_root=verified.root,
        actions=verified.records,
        phases=phases,
        findings=findings,
        limitation=(
            "Rules inspect declared boundary metadata only. A rule hit is not proof of intent, "
            "dataflow, policy violation, or downstream causation; absent hits do not prove safety."
        ),
    )
