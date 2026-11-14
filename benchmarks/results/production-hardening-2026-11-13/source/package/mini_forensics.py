"""A bounded, evidence-linked investigation of the synthetic teaching fixture.

This is deliberately not the general incident engine or OPA policy runtime.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sentinel_replay.journal import Journal


class EvidenceShapeError(ValueError):
    """A verified journal does not contain the declared mini-agent evidence shape."""


@dataclass(frozen=True)
class MiniStep:
    index: int
    call_id: str
    operation: str
    resource: str | None
    host: str | None
    sensitivity: str | None
    carrier: str | None
    depends_on: str | None


@dataclass(frozen=True)
class EvidenceEdge:
    source: int
    target: int
    kind: Literal["chronological", "dataflow", "control"]
    rationale: str
    carrier_hmac: str | None = None


@dataclass(frozen=True)
class IncidentFinding:
    rule_id: str
    root_step: int
    egress_step: int
    evidence: str


@dataclass(frozen=True)
class PolicyScore:
    candidate: str
    prevents_recorded_action: bool
    benign_actions_blocked: int
    rule_complexity: int


@dataclass(frozen=True)
class MiniReport:
    mode: Literal["TRACE_POLICY_EVALUATION"]
    incident_journal_root: str
    benign_journal_root: str
    incident: IncidentFinding | None
    edges: list[EvidenceEdge]
    blast_radius: list[int]
    policies: list[PolicyScore]
    frontier: list[str]
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _string_field(evidence: dict[str, object], field: str) -> str | None:
    value = evidence.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvidenceShapeError(f"evidence field {field} must be a string")
    return value


def _read_steps(path: Path) -> tuple[list[MiniStep], str]:
    journal = Journal(path)
    root = journal.verify().root
    steps: list[MiniStep] = []
    for index, event in enumerate(journal.events()):
        if not isinstance(event, dict):
            raise EvidenceShapeError(f"boundary event {index} is not a map")
        evidence = event.get("evidence")
        call_id = event.get("call_id")
        if not isinstance(evidence, dict) or not isinstance(call_id, str):
            raise EvidenceShapeError(f"boundary event {index} lacks safe evidence metadata")
        if not all(isinstance(key, str) for key in evidence):
            raise EvidenceShapeError(f"boundary event {index} has an invalid evidence key")
        operation = _string_field(evidence, "operation")
        if operation is None:
            raise EvidenceShapeError(f"boundary event {index} lacks an operation")
        steps.append(
            MiniStep(
                index=index,
                call_id=call_id,
                operation=operation,
                resource=_string_field(evidence, "resource"),
                host=_string_field(evidence, "host"),
                sensitivity=_string_field(evidence, "sensitivity"),
                carrier=_string_field(evidence, "carrier"),
                depends_on=_string_field(evidence, "depends_on"),
            )
        )
    return steps, root


def _evidence_edges(steps: list[MiniStep]) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = [
        EvidenceEdge(
            source=index - 1,
            target=index,
            kind="chronological",
            rationale="ordered in the verified journal; not a contamination claim",
        )
        for index in range(1, len(steps))
    ]
    by_id = {step.call_id: step for step in steps}
    reads = [step for step in steps if step.operation == "read_file" and step.carrier]
    for step in steps:
        if step.operation == "http_post" and step.carrier:
            for read in reads:
                if read.index < step.index and read.carrier == step.carrier:
                    edges.append(
                        EvidenceEdge(
                            source=read.index,
                            target=step.index,
                            kind="dataflow",
                            rationale="matching synthetic keyed carrier in read and request",
                            carrier_hmac=step.carrier,
                        )
                    )
        if step.depends_on:
            parent = by_id.get(step.depends_on)
            if parent is not None and parent.index < step.index:
                edges.append(
                    EvidenceEdge(
                        source=parent.index,
                        target=step.index,
                        kind="control",
                        rationale="declared scripted-agent control dependency",
                    )
                )
    return edges


def _finding(steps: list[MiniStep], edges: list[EvidenceEdge]) -> IncidentFinding | None:
    by_index = {step.index: step for step in steps}
    for edge in edges:
        if edge.kind != "dataflow":
            continue
        source, target = by_index[edge.source], by_index[edge.target]
        if (
            source.sensitivity == "secret"
            and target.operation == "http_post"
            and target.host == "demo.invalid"
        ):
            return IncidentFinding(
                rule_id="synthetic_secret_to_unapproved_host_v1",
                root_step=source.index,
                egress_step=target.index,
                evidence="secret-classified read and outbound request share a keyed carrier",
            )
    return None


def _blast_radius(root: int, edges: list[EvidenceEdge]) -> list[int]:
    reached = {root}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for edge in edges:
            if edge.kind == "chronological" or edge.source != current:
                continue
            if edge.target not in reached:
                reached.add(edge.target)
                queue.append(edge.target)
    return sorted(reached - {root})


def _blocks(candidate: str, step: MiniStep, secret_carriers: set[str]) -> bool:
    if step.operation != "http_post":
        return False
    if candidate == "deny_demo_host":
        return step.host == "demo.invalid"
    if candidate == "deny_secret_egress":
        return step.carrier is not None and step.carrier in secret_carriers
    if candidate == "deny_all_http_post":
        return True
    raise ValueError(f"unknown policy candidate: {candidate}")


def _scores(
    incident_steps: list[MiniStep], benign_steps: list[MiniStep], finding: IncidentFinding | None
) -> tuple[list[PolicyScore], list[str]]:
    incident_secrets = {
        step.carrier
        for step in incident_steps
        if step.sensitivity == "secret" and step.carrier is not None
    }
    benign_secrets = {
        step.carrier
        for step in benign_steps
        if step.sensitivity == "secret" and step.carrier is not None
    }
    candidates = (
        ("deny_demo_host", 1),
        ("deny_secret_egress", 2),
        ("deny_all_http_post", 1),
    )
    scores: list[PolicyScore] = []
    for name, complexity in candidates:
        blocked = finding is not None and _blocks(
            name, incident_steps[finding.egress_step], incident_secrets
        )
        benign_blocks = sum(_blocks(name, step, benign_secrets) for step in benign_steps)
        scores.append(PolicyScore(name, blocked, benign_blocks, complexity))
    preventing = [score for score in scores if score.prevents_recorded_action]
    frontier = [
        score.candidate
        for score in preventing
        if not any(
            other is not score
            and other.benign_actions_blocked <= score.benign_actions_blocked
            and other.rule_complexity <= score.rule_complexity
            and (
                other.benign_actions_blocked < score.benign_actions_blocked
                or other.rule_complexity < score.rule_complexity
            )
            for other in preventing
        )
    ]
    return scores, frontier


def investigate_mini(incident_path: Path, benign_path: Path) -> MiniReport:
    """Build a narrow, reproducible report from two fully verified mini journals."""
    incident_steps, incident_root = _read_steps(incident_path)
    benign_steps, benign_root = _read_steps(benign_path)
    edges = _evidence_edges(incident_steps)
    finding = _finding(incident_steps, edges)
    scores, frontier = _scores(incident_steps, benign_steps, finding)
    return MiniReport(
        mode="TRACE_POLICY_EVALUATION",
        incident_journal_root=incident_root,
        benign_journal_root=benign_root,
        incident=finding,
        edges=edges,
        blast_radius=_blast_radius(finding.root_step, edges) if finding else [],
        policies=scores,
        frontier=frontier,
        limitation=(
            "Synthetic fixture only. Policy decisions are evaluated on recorded actions; "
            "agent adaptation, actual enforcement, state restoration, and real-world causality "
            "are not established."
        ),
    )
