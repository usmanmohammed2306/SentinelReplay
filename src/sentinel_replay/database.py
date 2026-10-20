"""Transactional metadata index for authenticated, immutable run imports."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

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

    def get(self, run_id: str) -> StoredRun | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.run_id == run_id)).first()
        return _stored(row) if row is not None else None

    def list(self, *, limit: int = 50, after: str | None = None) -> list[StoredRun]:
        query = select(runs).order_by(runs.c.run_id).limit(limit)
        if after is not None:
            query = query.where(runs.c.run_id > after)
        with self.engine.connect() as connection:
            return [_stored(row) for row in connection.execute(query)]

    def insert_or_get(self, record: StoredRun) -> tuple[StoredRun, bool]:
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(runs).values(**record.__dict__))
            return record, True
        except IntegrityError as error:
            existing = self.get(record.run_id)
            if existing == record:
                return existing, False
            raise RunConflict("run ID is already bound to different evidence") from error
