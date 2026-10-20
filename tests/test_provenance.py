from pathlib import Path

import pytest
from typer.testing import CliRunner

import sentinel_replay.provenance as provenance_module
from sentinel_replay.cli import app
from sentinel_replay.journal import Journal
from sentinel_replay.provenance import ProvenanceShapeError, build_provenance


def _append(
    journal: Journal,
    call_id: str,
    operation: str,
    **evidence: str,
) -> None:
    journal.append(
        {
            "sequence": journal.verify().records if journal.path.exists() else 0,
            "call_id": call_id,
            "kind": "tool",
            "evidence": {"operation": operation, **evidence},
            "response": {"synthetic": True},
        }
    )


def test_declared_carrier_and_control_edges_but_not_chronology(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = Journal(path)
    _append(journal, "unrelated", "clock")
    _append(
        journal,
        "read",
        "read_file",
        carrier="keyed-demo-marker",
        carrier_role="source",
        sensitivity="secret",
    )
    _append(journal, "unrelated-2", "write_file")
    _append(
        journal,
        "egress",
        "http_post",
        carrier="keyed-demo-marker",
        carrier_role="sink",
    )
    _append(journal, "report", "write_file", depends_on="egress")
    result = build_provenance(path, 1)
    assert result.blast_radius == [3, 4]
    assert [
        (edge.source, edge.target, edge.kind)
        for edge in result.edges
        if edge.kind != "chronological"
    ] == [
        (1, 3, "declared_carrier"),
        (3, 4, "declared_control"),
    ]
    assert result.journal_root == journal.verify().root
    assert "keyed-demo-marker" not in str(result.to_dict())


def test_untyped_carrier_is_a_gap_not_a_causal_edge(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = Journal(path)
    _append(journal, "read", "read_file", carrier="same-marker")
    _append(journal, "post", "http_post", carrier="same-marker")
    result = build_provenance(path, 0)
    assert result.blast_radius == []
    assert result.untyped_carrier_steps == [0, 1]


def test_duplicate_ids_and_future_dependency_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = Journal(path)
    _append(journal, "same", "read_file")
    _append(journal, "same", "http_post")
    with pytest.raises(ProvenanceShapeError, match="duplicate call ID"):
        build_provenance(path, 0)
    other = tmp_path / "other.jsonl"
    _append(Journal(other), "write", "write_file", depends_on="missing")
    with pytest.raises(ProvenanceShapeError, match="unresolved dependency"):
        build_provenance(other, 0)


def test_edge_budget_fails_instead_of_returning_a_partial_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "run.jsonl"
    journal = Journal(path)
    _append(journal, "source-1", "read_file", carrier="same", carrier_role="source")
    _append(journal, "source-2", "read_file", carrier="same", carrier_role="source")
    _append(journal, "sink-1", "http_post", carrier="same", carrier_role="sink")
    _append(journal, "sink-2", "http_post", carrier="same", carrier_role="sink")
    monkeypatch.setattr(provenance_module, "MAX_PROVENANCE_EDGES", 4)
    with pytest.raises(ProvenanceShapeError, match="edge limit"):
        build_provenance(path, 0)


def test_cli_provenance_report_is_redacted(tmp_path: Path) -> None:
    journal = tmp_path / "incident.jsonl"
    runner = CliRunner()
    assert runner.invoke(app, ["mini", "record", "incident", str(journal)]).exit_code == 0
    report = tmp_path / "graph.json"
    created = runner.invoke(app, ["provenance", str(journal), "2", "--output", str(report)])
    assert created.exit_code == 0, created.output
    assert "DECLARED_PROVENANCE_PREVIEW" in created.output
    content = report.read_text()
    assert "DEMO_TOKEN_001" not in content
    assert "keyed-demo-marker" not in content
    assert "declared_carrier" in content


def test_large_benign_journal_stays_within_edge_budget(tmp_path: Path) -> None:
    path = tmp_path / "large.jsonl"
    events = [
        {
            "sequence": index,
            "call_id": f"call-{index}",
            "kind": "tool",
            "evidence": {"operation": "clock"},
        }
        for index in range(3000)
    ]
    Journal(path).append_many(events)
    result = build_provenance(path, 0)
    assert result.nodes == 3000
    assert len(result.edges) == 2999
    assert result.blast_radius == []
