import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_upgrade_and_downgrade_create_exact_run_columns(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    environment = {**os.environ, "SENTINEL_DATABASE_URL": database_url}
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "0001_runs" in upgraded.stderr
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("runs")} == {
        "run_id",
        "journal_root",
        "records",
        "capsule_digest",
        "capsule_size",
        "signer_key_id",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "runs" not in inspect(engine).get_table_names()
