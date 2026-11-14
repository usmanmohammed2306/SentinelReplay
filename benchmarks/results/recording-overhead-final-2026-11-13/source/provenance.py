"""Bounded declared-dependency graph over fully verified boundary metadata.

This reports evidence *claims* from the recorder. It does not infer causality
from time order, response bodies, or matching strings without explicit roles.
"""

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sentinel_replay.journal import Journal

MAX_PROVENANCE_STEPS = 100_000
MAX_PROVENANCE_EDGES = 200_000


class ProvenanceShapeError(ValueError):
    """Verified boundary metadata cannot support a declared graph."""


@dataclass(frozen=True)
class ProvenanceEdge:
    source: int
    target: int
    kind: Literal["chronological", "declared_carrier", "declared_control"]
    rationale: str


@dataclass(frozen=True)
class ProvenanceReport:
    mode: Literal["DECLARED_PROVENANCE_PREVIEW"]
    journal_root: str
    nodes: int
    edges: list[ProvenanceEdge]
    root_step: int
    blast_radius: list[int]
    untyped_carrier_steps: list[int]
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Step:
    call_id: str
    operation: str
    carrier: str | None
    carrier_role: str | None
    depends_on: str | None


def _optional_string(metadata: dict[str, object], key: str, index: int) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ProvenanceShapeError(f"boundary {index} has invalid {key}")
    return value


def _read_step(index: int, event: object) -> _Step:
    if not isinstance(event, dict):
        raise ProvenanceShapeError(f"boundary {index} is not an object")
    if type(event.get("sequence")) is not int or event["sequence"] != index:
        raise ProvenanceShapeError(f"boundary {index} has an invalid sequence")
    call_id = event.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        raise ProvenanceShapeError(f"boundary {index} has an invalid call ID")
    metadata = event.get("evidence")
    if not isinstance(metadata, dict) or not all(isinstance(key, str) for key in metadata):
        raise ProvenanceShapeError(f"boundary {index} lacks valid evidence metadata")
    operation = _optional_string(metadata, "operation", index)
    if operation is None:
        raise ProvenanceShapeError(f"boundary {index} lacks operation metadata")
    carrier = _optional_string(metadata, "carrier", index)
    role = _optional_string(metadata, "carrier_role", index)
    if role is not None and (role not in {"source", "sink"} or carrier is None):
        raise ProvenanceShapeError(f"boundary {index} has an invalid carrier role")
    return _Step(call_id, operation, carrier, role, _optional_string(metadata, "depends_on", index))


def build_provenance(journal_path: Path, root_step: int) -> ProvenanceReport:
    """Graph declared forward dependencies without treating chronology as dataflow."""
    if type(root_step) is not int or root_step < 0:
        raise ProvenanceShapeError("root step must be a nonnegative integer")
    steps: list[_Step] = []

    def visit(index: int, event: object) -> None:
        if index >= MAX_PROVENANCE_STEPS:
            raise ProvenanceShapeError("journal exceeds provenance step limit")
        steps.append(_read_step(index, event))

    verified = Journal(journal_path).scan_verified(visit)
    if root_step >= len(steps):
        raise ProvenanceShapeError("root step is outside the verified journal")

    edges: list[ProvenanceEdge] = []
    by_id: dict[str, int] = {}
    sources: dict[str, list[int]] = defaultdict(list)
    untyped: list[int] = []

    def add_edge(
        source: int,
        target: int,
        kind: Literal["chronological", "declared_carrier", "declared_control"],
        rationale: str,
    ) -> None:
        if len(edges) >= MAX_PROVENANCE_EDGES:
            raise ProvenanceShapeError("declared graph exceeds edge limit")
        edges.append(ProvenanceEdge(source, target, kind, rationale))

    for index, step in enumerate(steps):
        if step.call_id in by_id:
            raise ProvenanceShapeError(f"duplicate call ID at boundary {index}")
        if index:
            add_edge(
                index - 1,
                index,
                "chronological",
                "ordered in the verified journal; not a dependency claim",
            )
        if step.carrier is not None and step.carrier_role is None:
            untyped.append(index)
        if step.carrier is not None and step.carrier_role == "sink":
            for source in sources[step.carrier]:
                add_edge(
                    source,
                    index,
                    "declared_carrier",
                    "recorder-declared source and sink share a keyed carrier marker",
                )
        if step.depends_on is not None:
            parent = by_id.get(step.depends_on)
            if parent is None:
                raise ProvenanceShapeError(f"unresolved dependency at boundary {index}")
            add_edge(
                parent,
                index,
                "declared_control",
                "recorder-declared control dependency on an earlier call",
            )
        if step.carrier is not None and step.carrier_role == "source":
            sources[step.carrier].append(index)
        by_id[step.call_id] = index

    adjacency: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        if edge.kind != "chronological":
            adjacency[edge.source].append(edge.target)
    reached = {root_step}
    queue = deque([root_step])
    while queue:
        for target in adjacency[queue.popleft()]:
            if target not in reached:
                reached.add(target)
                queue.append(target)
    return ProvenanceReport(
        mode="DECLARED_PROVENANCE_PREVIEW",
        journal_root=verified.root,
        nodes=len(steps),
        edges=edges,
        root_step=root_step,
        blast_radius=sorted(reached - {root_step}),
        untyped_carrier_steps=untyped,
        limitation=(
            "Edges come from declared boundary metadata, not observed causal proof. "
            "Chronology is excluded from reachability; untyped carriers produce no dependency. "
            "Uninstrumented actions and agent adaptation remain outside this graph."
        ),
    )
