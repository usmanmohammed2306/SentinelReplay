import os
import subprocess
from pathlib import Path

import pytest

from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.git_snapshot import capture_git, restore_git


def git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Sentinel synthetic fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        env=env,
        text=True,
    ).strip()


def test_head_staged_unstaged_untracked_and_refs_survive_without_hooks(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    (root / "file.txt").write_text("committed")
    git(root, "add", "file.txt")
    git(root, "commit", "-m", "Synthetic snapshot fixture")
    expected_head = git(root, "rev-parse", "HEAD")
    (root / "file.txt").write_text("staged")
    git(root, "add", "file.txt")
    (root / "file.txt").write_text("unstaged")
    (root / "untracked.txt").write_text("untracked")
    marker = tmp_path / "must-not-execute"
    (root / ".git/hooks/post-checkout").write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    store = FileEvidenceStore(tmp_path / "cas")
    checkpoint = capture_git(root, store)
    restored = tmp_path / "restored"
    assert restore_git(checkpoint, restored, store)
    assert git(restored, "rev-parse", "HEAD") == expected_head
    assert git(restored, "show", "HEAD:file.txt") == "committed"
    assert git(restored, "show", ":file.txt") == "staged"
    assert (restored / "file.txt").read_text() == "unstaged"
    assert (restored / "untracked.txt").read_text() == "untracked"
    assert not (restored / ".git/hooks").exists()
    assert not marker.exists()
    assert git(restored, "fsck", "--no-reflogs", "--strict") == ""


def test_external_object_store_is_explicitly_unsupported(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    (root / ".git/objects/info/alternates").write_text("/outside/objects\n")
    with pytest.raises(ValueError, match="unsupported"):
        capture_git(root, FileEvidenceStore(tmp_path / "cas"))
