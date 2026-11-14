from pathlib import Path

import pytest
from sqlalchemy import create_engine

from sentinel_replay.database import RunRepository, StoredRun, metadata
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.query_index import QueryIndex

CAPSULE = Path(__file__).resolve().parents[1] / (
    "benchmarks/results/isolated-branches-final-2026-11-13/"
    "protected_export--allow_both/controller/branch.sentinel"
)


def test_indexed_views_match_source_without_reloading_raw_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    store = FileEvidenceStore(tmp_path / "cas")
    source = CapsuleInvestigation(CAPSULE.read_bytes())
    ref = store.put(source.data)
    run = StoredRun(
        source.verified.run_id,
        source.verified.root,
        source.verified.records,
        ref.digest,
        ref.size,
        "sha256:" + "a" * 64,
    )
    RunRepository(engine).insert_or_get(run)
    indexer = QueryIndex(engine, store)
    indexed = indexer.build(run, source)
    assert indexer.build(run, source)["index_id"] == indexed["index_id"]
    timeline = indexer.timeline(indexed, offset=1, limit=2)
    assert timeline == source.timeline(offset=1, limit=2)
    graph = indexer.provenance(indexed, root_step=1, depth=3)
    expected = source.provenance(root_step=1, depth=3)
    assert graph["nodes"] == expected["nodes"]
    assert {(r["source"], r["target"], r["kind"]) for r in graph["edges"]} == {
        (r["source"], r["target"], r["kind"]) for r in expected["edges"]
    }
    assert graph["blast_radius"] == expected["blast_radius"]
    assert graph["blast_radius_complete"]
    # Derived pages are enough for these views; verification/replay remain raw.
    store._path(ref.digest).unlink()
    assert indexer.timeline(indexed, limit=1)["events"]
    with pytest.raises(ValueError, match="root"):
        indexer.timeline(indexed, expected_root="wrong")


def test_tampered_derived_page_fails_its_own_content_digest(tmp_path: Path) -> None:
    from sqlalchemy import select

    from sentinel_replay.database import event_pages

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    store = FileEvidenceStore(tmp_path / "cas")
    source = CapsuleInvestigation(CAPSULE.read_bytes())
    ref = store.put(source.data)
    run = StoredRun(
        source.verified.run_id,
        source.verified.root,
        source.verified.records,
        ref.digest,
        ref.size,
        "sha256:" + "a" * 64,
    )
    RunRepository(engine).insert_or_get(run)
    indexer = QueryIndex(engine, store)
    indexed = indexer.build(run, source)
    with engine.connect() as connection:
        row = connection.execute(select(event_pages)).mappings().first()
        assert row is not None
        store._path(row["digest"]).write_bytes(b"edited")
    with pytest.raises(ValueError):
        indexer.timeline(indexed, limit=1)
