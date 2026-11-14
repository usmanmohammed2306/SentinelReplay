"""Score declared dependency edges against separately authored ground truth.

The metric protocol does not make recorder declarations independent labels.
Public accuracy claims require a versioned corpus with human-audited truth.
"""

from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel_replay.provenance import ProvenanceReport


class LabelError(ValueError):
    """The labels do not match the graph or violate the scoring protocol."""


class LabeledDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: int = Field(ge=0)
    target: int = Field(ge=0)
    kind: Literal["dataflow", "filesystem", "effect", "trace_parent", "control"]

    @model_validator(mode="after")
    def forward(self) -> "LabeledDependency":
        if self.source >= self.target:
            raise ValueError("ground-truth dependencies must point forward")
        return self


class ProvenanceLabels(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    journal_root: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    nodes: int = Field(ge=0)
    labeled_by: str = Field(min_length=1, max_length=120)
    dependencies: tuple[LabeledDependency, ...]

    @model_validator(mode="after")
    def unique_pairs(self) -> "ProvenanceLabels":
        pairs = [(edge.source, edge.target) for edge in self.dependencies]
        if pairs != sorted(set(pairs)):
            raise ValueError("ground-truth dependency pairs must be unique and sorted")
        if any(edge.target >= self.nodes for edge in self.dependencies):
            raise ValueError("ground-truth dependency is outside the declared node count")
        return self


@dataclass(frozen=True)
class ProvenanceMetrics:
    mode: Literal["DECLARED_EDGE_SCORE"]
    journal_root: str
    nodes: int
    predicted: int
    labeled_positive: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None
    ignored_chronological: int
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_provenance(report: ProvenanceReport, labels: ProvenanceLabels) -> ProvenanceMetrics:
    """Count directed dependency pairs; chronology never enters the denominator."""
    if report.journal_root != labels.journal_root or report.nodes != labels.nodes:
        raise LabelError("labels do not match the verified journal graph")
    predicted_edges = [edge for edge in report.edges if edge.kind != "chronological"]
    predicted = {(edge.source, edge.target) for edge in predicted_edges}
    if len(predicted) != len(predicted_edges):
        raise LabelError("report contains duplicate dependency pairs")
    truth = {(edge.source, edge.target) for edge in labels.dependencies}
    tp = len(predicted & truth)
    fp = len(predicted - truth)
    fn = len(truth - predicted)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return ProvenanceMetrics(
        mode="DECLARED_EDGE_SCORE",
        journal_root=report.journal_root,
        nodes=report.nodes,
        predicted=len(predicted),
        labeled_positive=len(truth),
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        ignored_chronological=sum(edge.kind == "chronological" for edge in report.edges),
        limitation=(
            "This scores declared dependency pairs only. Labels must be independently "
            "audited for public accuracy claims; chronology is excluded."
        ),
    )
