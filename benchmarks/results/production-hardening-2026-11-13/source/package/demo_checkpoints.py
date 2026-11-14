"""Disposable, explicitly synthetic Git/SQLite fixtures for the product demo."""

import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any

from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.git_snapshot import capture_git
from sentinel_replay.sqlite_snapshot import capture_sqlite


def create_demo_checkpoints(destination: Path) -> tuple[dict[str, Any], FileEvidenceStore]:
    destination.mkdir(mode=0o700)
    store = FileEvidenceStore(destination / "blobs", max_bytes=32 * 1024 * 1024)
    database = destination / "agent.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence(value) VALUES('synthetic-initial-state')")
        connection.commit()
    worktree = destination / "repository"
    worktree.mkdir()
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("the integrated Git checkpoint demonstration requires local Git")
    env = {
        "PATH": os.defpath,
        "HOME": str(destination),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_AUTHOR_DATE": "2026-11-13T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-11-13T00:00:00Z",
    }

    def git(*args: str) -> None:
        subprocess.run(
            [
                executable,
                "-C",
                str(worktree),
                "-c",
                "user.name=Sentinel synthetic fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            env=env,
            capture_output=True,
            timeout=10,
            check=True,
        )

    git("init", "--initial-branch=main", "--object-format=sha1")
    (worktree / "agent.txt").write_text("committed synthetic state\n")
    git("add", "agent.txt")
    git("commit", "-m", "Synthetic demo checkpoint")
    (worktree / "agent.txt").write_text("staged synthetic state\n")
    git("add", "agent.txt")
    (worktree / "agent.txt").write_text("unstaged synthetic state\n")
    manifests = {"sqlite": capture_sqlite(database, store), "git": capture_git(worktree, store)}
    for name, manifest in manifests.items():
        (destination / f"{name}-manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifests, store
