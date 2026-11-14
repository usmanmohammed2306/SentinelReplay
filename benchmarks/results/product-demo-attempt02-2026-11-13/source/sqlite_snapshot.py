"""Consistent SQLite backup for a declared cooperative database boundary.

Use SQLite's backup API, including committed WAL state, rather than copying the
live main file. Hostile parent-path races, custom VFS/extensions and concurrent
agent filesystem replacement are outside this adapter's conformance contract.
"""

import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore, blob_digest
from sentinel_replay.local_anchor import _fsync_directory, _write_new

MAX_DATABASE_BYTES = 32 * 1024 * 1024


class SQLiteCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    adapter: Literal["sqlite-backup-v1"] = "sqlite-backup-v1"
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size: int = Field(ge=1, le=MAX_DATABASE_BYTES)
    sqlite_version: str
    adapter_source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    coverage: Literal["committed_sqlite_backup_cooperative_owner"] = (
        "committed_sqlite_backup_cooperative_owner"
    )


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    connection.enable_load_extension(False)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def capture_sqlite(
    path: Path, store: FileEvidenceStore, *, timeout_seconds: float = 5
) -> SQLiteCheckpoint:
    if not 0 < timeout_seconds <= 30 or path.is_symlink() or not path.is_file():
        raise ValueError("SQLite capture requires a regular database and bounded timeout")
    before = path.stat()
    started = time.monotonic()
    page_bytes = 4096
    with tempfile.TemporaryDirectory(prefix="sentinel-sqlite-") as directory:
        copied = Path(directory) / "checkpoint.db"

        def progress(status: int, remaining: int, total: int) -> None:
            if time.monotonic() - started > timeout_seconds:
                raise ValueError("SQLite backup exceeded its consistency/lock budget")
            if total * page_bytes > MAX_DATABASE_BYTES:
                raise ValueError("SQLite page estimate exceeds conservative byte budget")

        with closing(_readonly(path)) as source, closing(sqlite3.connect(copied)) as target:
            page_bytes = int(source.execute("PRAGMA page_size").fetchone()[0])
            source.backup(target, pages=128, progress=progress, sleep=0.01)
            if target.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("SQLite backup failed integrity verification")
        after = path.stat()
        if path.is_symlink() or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("SQLite source identity changed during capture")
        if copied.stat().st_size > MAX_DATABASE_BYTES:
            raise ValueError("SQLite backup exceeds byte budget")
        ref = store.put(copied.read_bytes())
    return SQLiteCheckpoint(
        digest=ref.digest,
        size=ref.size,
        sqlite_version=sqlite3.sqlite_version,
        adapter_source_digest=blob_digest(Path(__file__).read_bytes()),
    )


def restore_sqlite(
    checkpoint: SQLiteCheckpoint, destination: Path, store: FileEvidenceStore
) -> bool:
    if checkpoint.adapter_source_digest != blob_digest(Path(__file__).read_bytes()):
        raise ValueError("SQLite adapter identity differs from the checkpoint")
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError("SQLite restore requires a new file under an existing private directory")
    data = store.get(BlobRef(checkpoint.digest, checkpoint.size))
    _write_new(destination, data, 0o600)
    _fsync_directory(destination.parent)
    with closing(_readonly(destination)) as restored:
        if restored.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("restored SQLite checkpoint failed integrity verification")
    descriptor = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            if source.read(MAX_DATABASE_BYTES + 1) != data:
                raise ValueError("restored SQLite bytes changed during verification")
    finally:
        os.close(descriptor)
    return True
