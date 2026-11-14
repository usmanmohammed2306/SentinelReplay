"""Immutable versioned derived indexes; raw journals remain authoritative.

Pages contain only allowlisted redacted metadata. Queries use SQL indexes and
bounded CAS pages instead of rescanning the full archive for each interaction.
Strict replay and verification always reload the raw capsule independently.
"""

import json
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import insert, literal, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.database import StoredRun, dependency_edges, event_pages, run_indexes
from sentinel_replay.evidence_store import BlobRef, blob_digest
from sentinel_replay.investigation import CapsuleInvestigation

PAGE_SIZE = 500


class IndexStore(Protocol):
    def put(self, data: bytes) -> BlobRef: ...
    def get(self, ref: BlobRef) -> bytes: ...


def producer_digest() -> str:
    return event_digest(
        {
            "schema_version": 1,
            "sources": {
                name: blob_digest(Path(__file__).with_name(name).read_bytes())
                for name in (
                    "query_index.py",
                    "investigation.py",
                    "provenance.py",
                    "timeline.py",
                    "canonical.py",
                )
            },
        }
    )


class QueryIndex:
    def __init__(self, engine: Engine, store: IndexStore) -> None:
        self.engine, self.store = engine, store
        self.producer = producer_digest()

    def identifier(self, run: StoredRun, view_id: str = "root") -> str:
        return event_digest(
            {
                "run": run.run_id,
                "view": view_id,
                "capsule": run.capsule_digest,
                "producer": self.producer,
            }
        )

    def find(self, run: StoredRun, view_id: str = "root") -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(run_indexes).where(
                        run_indexes.c.index_id == self.identifier(run, view_id)
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        if (
            row["capsule_digest"] != run.capsule_digest
            or row["run_id"] != run.run_id
            or row["producer_digest"] != self.producer
            or (
                view_id == "root"
                and (row["journal_root"] != run.journal_root or row["records"] != run.records)
            )
        ):
            raise ValueError("derived index source binding mismatch")
        return dict(row)

    def build(
        self, run: StoredRun, source: CapsuleInvestigation, view_id: str = "root"
    ) -> dict[str, Any]:
        identifier = self.identifier(run, view_id)
        existing = self.find(run, view_id)
        if existing:
            return existing
        if view_id == "root" and (
            source.verified.run_id != run.run_id
            or source.verified.root != run.journal_root
            or source.verified.records != run.records
        ):
            raise ValueError("cannot index a different run")
        summary = source.summary()
        summary["index_basis"] = "derived_from_verified_capsule_at_build"
        phases = None
        with suppress(ValueError):
            phases = source.phases()
        try:
            edges, _, _, _ = source.dependency_index
            graph_supported = 1
        except ValueError:
            edges, graph_supported = [], 0
        page_rows = []
        for offset in range(0, len(source.events), PAGE_SIZE):
            page = source.timeline(offset=offset, limit=PAGE_SIZE)
            data = json.dumps(page["events"], separators=(",", ":"), sort_keys=True).encode()
            ref = self.store.put(data)
            page_rows.append(
                {
                    "index_id": identifier,
                    "first_step": offset,
                    "records": len(page["events"]),
                    "digest": ref.digest,
                    "size": ref.size,
                }
            )
        record = {
            "index_id": identifier,
            "run_id": run.run_id,
            "view_id": view_id,
            "producer_digest": self.producer,
            "capsule_digest": run.capsule_digest,
            "journal_root": source.verified.root,
            "records": source.verified.records,
            "summary": summary,
            "phases": phases,
            "incidents": source.incidents(),
            "graph_supported": graph_supported,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(run_indexes).values(**record))
                if page_rows:
                    connection.execute(insert(event_pages), page_rows)
                edge_rows = [{"index_id": identifier, **edge} for edge in edges]
                if edge_rows:
                    # Bound SQL parameter counts on SQLite and PostgreSQL drivers.
                    for start in range(0, len(edge_rows), 500):
                        connection.execute(insert(dependency_edges), edge_rows[start : start + 500])
        except IntegrityError:
            concurrent = self.find(run, view_id)
            if concurrent is None:
                raise
            return concurrent
        return record

    def timeline(
        self,
        index: dict[str, Any],
        *,
        offset: int = 0,
        limit: int = 100,
        expected_root: str | None = None,
    ) -> dict[str, Any]:
        if expected_root is not None and expected_root != index["journal_root"]:
            raise ValueError("timeline root mismatch")
        if not 0 <= offset <= index["records"] or not 1 <= limit <= PAGE_SIZE:
            raise ValueError("invalid timeline pagination")
        stop = min(offset + limit, index["records"])
        rows = self.events(index, list(range(offset, stop)))
        return {
            "journal_root": index["journal_root"],
            "total": index["records"],
            "offset": offset,
            "next_offset": stop if stop < index["records"] else None,
            "events": rows,
        }

    def events(self, index: dict[str, Any], steps: list[int]) -> list[dict[str, Any]]:
        if not steps:
            return []
        pages = sorted({step // PAGE_SIZE * PAGE_SIZE for step in steps})
        with self.engine.connect() as connection:
            references = (
                connection.execute(
                    select(event_pages).where(
                        event_pages.c.index_id == index["index_id"],
                        event_pages.c.first_step.in_(pages),
                    )
                )
                .mappings()
                .all()
            )
        if len(references) != len(pages):
            raise ValueError("derived event pages are incomplete")
        indexed = {}
        selected = set(steps)
        for row in references:
            page = load_json_unique(self.store.get(BlobRef(row["digest"], row["size"])).decode())
            if not isinstance(page, list) or len(page) != row["records"]:
                raise ValueError("derived event page shape mismatch")
            for position, event in enumerate(page):
                if not isinstance(event, dict) or event.get("step") != row["first_step"] + position:
                    raise ValueError("derived event page sequence differs")
                if event["step"] in selected:
                    indexed[event["step"]] = event
        return [indexed[step] for step in steps]

    def provenance(
        self, index: dict[str, Any], *, root_step: int = 0, depth: int = 2
    ) -> dict[str, Any]:
        if (
            not index["graph_supported"]
            or not 0 <= root_step < index["records"]
            or not 1 <= depth <= 5
        ):
            raise ValueError("unsupported graph root, schema or depth")
        reached, frontier = {root_step}, {root_step}
        with self.engine.connect() as connection:
            for _ in range(depth):
                query = (
                    select(dependency_edges)
                    .where(
                        dependency_edges.c.index_id == index["index_id"],
                        or_(
                            dependency_edges.c.source.in_(frontier),
                            dependency_edges.c.target.in_(frontier),
                        ),
                    )
                    .limit(2001)
                )
                rows = connection.execute(query).mappings().all()
                if len(rows) > 2000:
                    raise ValueError("dependency neighborhood exceeds edge budget")
                following = {
                    value for row in rows for value in (row["source"], row["target"])
                } - reached
                reached.update(following)
                if len(reached) > 500:
                    raise ValueError("dependency neighborhood exceeds node budget")
                frontier = following
                if not frontier:
                    break
            edges = (
                connection.execute(
                    select(dependency_edges)
                    .where(
                        dependency_edges.c.index_id == index["index_id"],
                        dependency_edges.c.source.in_(reached),
                        dependency_edges.c.target.in_(reached),
                    )
                    .limit(2001)
                )
                .mappings()
                .all()
            )
            if len(edges) > 2000:
                raise ValueError("dependency neighborhood exceeds edge budget")
            reachable = select(literal(root_step).label("step")).cte("reachable", recursive=True)
            reachable = reachable.union(
                select(dependency_edges.c.target.label("step")).where(
                    dependency_edges.c.index_id == index["index_id"],
                    dependency_edges.c.source == reachable.c.step,
                )
            )
            blast: list[int] = list(
                connection.execute(select(reachable.c.step).limit(5001)).scalars()
            )
        return {
            "journal_root": index["journal_root"],
            "mode": "DECLARED_PROVENANCE_PREVIEW",
            "root_step": root_step,
            "total_nodes": index["records"],
            "nodes": self.events(index, sorted(reached)),
            "edges": [
                {key: row[key] for key in ("source", "target", "kind", "rationale")}
                for row in edges
            ],
            "blast_radius": sorted(set(blast[:5000]) - {root_step}),
            "blast_radius_complete": len(blast) <= 5000,
            "limitation": (
                "Indexed recorder-declared dependencies; chronology is excluded. "
                "No independent causal or provenance-accuracy proof."
            ),
        }
