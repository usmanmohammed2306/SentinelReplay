from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.journal import Journal
from sentinel_replay.provenance import ProvenanceEdge, ProvenanceReport
from sentinel_replay.provenance_eval import (
    LabeledDependency,
    LabelError,
    ProvenanceLabels,
    score_provenance,
)

ROOT = "sha256:" + "a" * 64


def _report(edges: list[ProvenanceEdge]) -> ProvenanceReport:
    return ProvenanceReport(
        mode="DECLARED_PROVENANCE_PREVIEW",
        journal_root=ROOT,
        nodes=5,
        edges=edges,
        root_step=0,
        blast_radius=[],
        untyped_carrier_steps=[],
        limitation="synthetic test graph",
    )


def test_precision_recall_denominators_exclude_chronology() -> None:
    report = _report(
        [
            ProvenanceEdge(0, 1, "chronological", "order only"),
            ProvenanceEdge(1, 2, "chronological", "order only"),
            ProvenanceEdge(0, 2, "declared_carrier", "declared"),
            ProvenanceEdge(1, 3, "declared_control", "declared"),
            ProvenanceEdge(2, 4, "declared_control", "declared"),
        ]
    )
    labels = ProvenanceLabels(
        journal_root=ROOT,
        nodes=5,
        labeled_by="independent synthetic fixture",
        dependencies=(
            LabeledDependency(source=0, target=2, kind="dataflow"),
            LabeledDependency(source=1, target=3, kind="control"),
            LabeledDependency(source=3, target=4, kind="effect"),
        ),
    )
    result = score_provenance(report, labels)
    assert (result.true_positive, result.false_positive, result.false_negative) == (2, 1, 1)
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1 == pytest.approx(2 / 3)
    assert result.ignored_chronological == 2


def test_no_positive_denominator_is_unknown_not_perfect() -> None:
    result = score_provenance(
        _report([ProvenanceEdge(0, 1, "chronological", "order only")]),
        ProvenanceLabels(journal_root=ROOT, nodes=5, labeled_by="synthetic", dependencies=()),
    )
    assert result.predicted == result.labeled_positive == 0
    assert result.precision is result.recall is result.f1 is None


def test_mismatched_root_or_graph_size_cannot_be_scored() -> None:
    report = _report([])
    wrong = ProvenanceLabels(
        journal_root="sha256:" + "b" * 64,
        nodes=5,
        labeled_by="synthetic",
        dependencies=(),
    )
    with pytest.raises(LabelError, match="do not match"):
        score_provenance(report, wrong)
    with pytest.raises(LabelError, match="do not match"):
        score_provenance(
            report,
            ProvenanceLabels(journal_root=ROOT, nodes=4, labeled_by="synthetic", dependencies=()),
        )


def test_labels_reject_duplicate_or_out_of_range_pairs() -> None:
    duplicate = (
        LabeledDependency(source=0, target=2, kind="dataflow"),
        LabeledDependency(source=0, target=2, kind="control"),
    )
    with pytest.raises(ValidationError, match="unique and sorted"):
        ProvenanceLabels(journal_root=ROOT, nodes=5, labeled_by="synthetic", dependencies=duplicate)
    with pytest.raises(ValidationError, match="outside"):
        ProvenanceLabels(
            journal_root=ROOT,
            nodes=5,
            labeled_by="synthetic",
            dependencies=(LabeledDependency(source=2, target=6, kind="control"),),
        )


def test_cli_scores_separately_authored_synthetic_labels(tmp_path: Path) -> None:
    runner = CliRunner()
    journal = tmp_path / "run.jsonl"
    assert runner.invoke(app, ["mini", "record", "incident", str(journal)]).exit_code == 0
    labels = ProvenanceLabels(
        journal_root=Journal(journal).verify().root,
        nodes=5,
        labeled_by="synthetic test author",
        dependencies=(
            LabeledDependency(source=2, target=3, kind="dataflow"),
            LabeledDependency(source=3, target=4, kind="control"),
        ),
    )
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(labels.model_dump_json(), encoding="utf-8")
    output = tmp_path / "score.json"
    result = runner.invoke(
        app,
        ["provenance-score", str(journal), "2", str(labels_path), "--output", str(output)],
    )
    assert result.exit_code == 0, result.output
    assert "tp=2 fp=0 fn=0" in result.output
    assert '"ignored_chronological": 4' in output.read_text()
