"""Transactional metadata index for authenticated, immutable run imports."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    exists,
    insert,
    select,
)
from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from sentinel_replay.evidence_store import BlobRef

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("run_id", String(80), primary_key=True),
    Column("journal_root", String(71), nullable=False),
    Column("records", Integer, nullable=False),
    Column("capsule_digest", String(71), nullable=False),
    Column("capsule_size", BigInteger, nullable=False),
    Column("signer_key_id", String(71), nullable=False),
    CheckConstraint("records >= 0", name="ck_runs_records_nonnegative"),
    CheckConstraint("capsule_size >= 0", name="ck_runs_capsule_size_nonnegative"),
)

run_indexes = Table(
    "run_indexes",
    metadata,
    Column("index_id", String(71), primary_key=True),
    Column("run_id", String(80), ForeignKey("runs.run_id"), nullable=False),
    Column("view_id", String(20), nullable=False),
    Column("producer_digest", String(71), nullable=False),
    Column("capsule_digest", String(71), nullable=False),
    Column("journal_root", String(71), nullable=False),
    Column("records", Integer, nullable=False),
    Column("summary", JSON, nullable=False),
    Column("phases", JSON, nullable=True),
    Column("incidents", JSON, nullable=False),
    Column("graph_supported", Integer, nullable=False),
)
event_pages = Table(
    "event_pages",
    metadata,
    Column("index_id", String(71), ForeignKey("run_indexes.index_id"), primary_key=True),
    Column("first_step", Integer, primary_key=True),
    Column("records", Integer, nullable=False),
    Column("digest", String(71), nullable=False),
    Column("size", BigInteger, nullable=False),
    CheckConstraint(
        "first_step >= 0 AND records > 0 AND records <= 500", name="ck_event_page_bounds"
    ),
)
dependency_edges = Table(
    "dependency_edges",
    metadata,
    Column("index_id", String(71), ForeignKey("run_indexes.index_id"), primary_key=True),
    Column("source", Integer, primary_key=True),
    Column("target", Integer, primary_key=True),
    Column("kind", String(32), primary_key=True),
    Column("rationale", String(240), nullable=False),
    CheckConstraint("source >= 0 AND target > source", name="ck_dependency_forward"),
)
Index("ix_dependency_target", dependency_edges.c.index_id, dependency_edges.c.target)

operation_jobs = Table(
    "operation_jobs",
    metadata,
    Column("job_id", String(32), primary_key=True),
    Column("run_id", String(80), ForeignKey("runs.run_id"), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("request_digest", String(71), nullable=False),
    Column("request_size", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
)
operation_events = Table(
    "operation_events",
    metadata,
    Column("job_id", String(32), ForeignKey("operation_jobs.job_id"), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("state", String(24), nullable=False),
    Column("body", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("sequence >= 0", name="ck_operation_event_sequence"),
)
Index("ix_operation_run", operation_jobs.c.run_id, operation_jobs.c.job_id)

trust_epochs = Table(
    "trust_epochs",
    metadata,
    Column("epoch", Integer, primary_key=True, autoincrement=False),
    Column("digest", String(71), nullable=False),
    CheckConstraint("epoch >= 1", name="ck_trust_epoch_positive"),
)
run_attestations = Table(
    "run_attestations",
    metadata,
    Column("run_id", String(80), ForeignKey("runs.run_id"), primary_key=True),
    Column("digest", String(71), nullable=False),
    Column("size", Integer, nullable=False),
    CheckConstraint("size > 0 AND size <= 8192", name="ck_run_attestation_size"),
)
run_retirements = Table(
    "run_retirements",
    metadata,
    Column("run_id", String(80), ForeignKey("runs.run_id"), primary_key=True),
    Column("retired_at", String(40), nullable=False),
    Column("reason", String(32), nullable=False),
)
future_receipts = Table(
    "future_receipts",
    metadata,
    Column("digest", String(71), primary_key=True),
    Column("run_id", String(80), ForeignKey("runs.run_id"), nullable=False),
    Column("size", Integer, nullable=False),
    CheckConstraint("size > 0 AND size <= 1048576", name="ck_future_receipt_size"),
)


class RunConflict(ValueError):
    """A run ID was already bound to different authenticated evidence."""


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    journal_root: str
    records: int
    capsule_digest: str
    capsule_size: int
    signer_key_id: str


def _stored(row: Row[Any]) -> StoredRun:
    values = row._mapping
    return StoredRun(
        run_id=values["run_id"],
        journal_root=values["journal_root"],
        records=values["records"],
        capsule_digest=values["capsule_digest"],
        capsule_size=values["capsule_size"],
        signer_key_id=values["signer_key_id"],
    )


class RunRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def health(self) -> bool:
        with self.engine.connect() as connection:
            return connection.scalar(select(1)) == 1

    def get(self, run_id: str, *, include_retired: bool = False) -> StoredRun | None:
        query = select(runs).where(runs.c.run_id == run_id)
        if not include_retired:
            query = query.where(
                ~exists(
                    select(run_retirements.c.run_id).where(
                        run_retirements.c.run_id == runs.c.run_id
                    )
                )
            )
        with self.engine.connect() as connection:
            row = connection.execute(query).first()
        return _stored(row) if row is not None else None

    def retirement(self, run_id: str) -> dict[str, str] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(run_retirements).where(run_retirements.c.run_id == run_id)
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def retire(self, run_id: str, retired_at: str, reason: str) -> dict[str, str]:
        existing = self.retirement(run_id)
        if existing:
            if existing["reason"] != reason:
                raise RunConflict("retirement reason is already frozen")
            return existing
        if self.get(run_id, include_retired=True) is None:
            raise ValueError("run not found")
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(run_retirements).values(
                        run_id=run_id, retired_at=retired_at, reason=reason
                    )
                )
        except IntegrityError:
            return self.retire(run_id, retired_at, reason)
        return {"run_id": run_id, "retired_at": retired_at, "reason": reason}

    def list(
        self,
        *,
        limit: int = 50,
        after: str | None = None,
        allowed_runs: frozenset[str] | None = None,
    ) -> list[StoredRun]:
        query = (
            select(runs)
            .where(
                ~exists(
                    select(run_retirements.c.run_id).where(
                        run_retirements.c.run_id == runs.c.run_id
                    )
                )
            )
            .order_by(runs.c.run_id)
            .limit(limit)
        )
        if allowed_runs is not None:
            query = query.where(runs.c.run_id.in_(sorted(allowed_runs)))
        if after is not None:
            query = query.where(runs.c.run_id > after)
        with self.engine.connect() as connection:
            return [_stored(row) for row in connection.execute(query)]

    def attestation(self, run_id: str) -> BlobRef | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(run_attestations).where(run_attestations.c.run_id == run_id)
                )
                .mappings()
                .first()
            )
        return BlobRef(row["digest"], row["size"]) if row else None

    def insert_or_get(
        self, record: StoredRun, *, attestation: BlobRef | None = None
    ) -> tuple[StoredRun, bool]:
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(runs).values(**record.__dict__))
                if attestation is not None:
                    connection.execute(
                        insert(run_attestations).values(
                            run_id=record.run_id, digest=attestation.digest, size=attestation.size
                        )
                    )
            return record, True
        except IntegrityError as error:
            existing = self.get(record.run_id)
            if existing == record:
                if attestation is not None and self.attestation(record.run_id) is None:
                    try:
                        with self.engine.begin() as connection:
                            connection.execute(
                                insert(run_attestations).values(
                                    run_id=record.run_id,
                                    digest=attestation.digest,
                                    size=attestation.size,
                                )
                            )
                    except IntegrityError:
                        if self.attestation(record.run_id) is None:
                            raise
                return existing, False
            raise RunConflict("run ID is already bound to different evidence") from error
