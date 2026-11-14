import sqlite3
from pathlib import Path

import pytest

from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.sqlite_snapshot import capture_sqlite, restore_sqlite


def test_committed_wal_state_restores_without_uncommitted_rows(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO evidence VALUES(1, 'committed')")
        writer.commit()
        writer.execute("INSERT INTO evidence VALUES(2, 'not committed')")
        store = FileEvidenceStore(tmp_path / "cas", max_bytes=32 * 1024 * 1024)
        checkpoint = capture_sqlite(source, store)
        destination = tmp_path / "restored.db"
        assert restore_sqlite(checkpoint, destination, store)
        with sqlite3.connect(destination) as restored:
            assert restored.execute("SELECT * FROM evidence").fetchall() == [(1, "committed")]


def test_restore_refuses_overwrite_and_symlink_source(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE data (value TEXT)")
    store = FileEvidenceStore(tmp_path / "cas")
    checkpoint = capture_sqlite(source, store)
    with pytest.raises(ValueError, match="new file"):
        restore_sqlite(checkpoint, source, store)
    alias = tmp_path / "alias.db"
    alias.symlink_to(source)
    with pytest.raises(ValueError, match="regular"):
        capture_sqlite(alias, store)
