import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.workspace_snapshot import (
    UnsafeWorkspace,
    capture_workspace,
    restore_workspace,
    verify_workspace,
)


def test_capture_restore_and_verify_declared_regular_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested").mkdir()
    (source / "nested" / "report.txt").write_text("before\n")
    (source / "run.sh").write_text("#!/bin/sh\n")
    (source / "run.sh").chmod(0o755)
    store = FileEvidenceStore(tmp_path / "blobs")

    manifest = capture_workspace(source, store)
    (source / "nested" / "report.txt").write_text("after\n")
    destination = tmp_path / "restored"
    restore_workspace(manifest, destination, store)

    assert (destination / "nested" / "report.txt").read_text() == "before\n"
    assert (destination / "run.sh").stat().st_mode & 0o111
    assert verify_workspace(manifest, destination)
    assert not verify_workspace(manifest, source)


def test_capture_refuses_symlink_and_uncovered_special_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "link").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(UnsafeWorkspace, match="symlink"):
        capture_workspace(source, FileEvidenceStore(tmp_path / "blobs"))


def test_capture_does_not_follow_swapped_nested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "file.txt").write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.txt").write_text("outside-secret")

    def enumerate_then_swap(_root: Path) -> list[Path]:
        (source / "nested").rename(source / "moved")
        (source / "nested").symlink_to(outside, target_is_directory=True)
        return [source / "nested" / "file.txt"]

    monkeypatch.setattr("sentinel_replay.workspace_snapshot._regular_files", enumerate_then_swap)
    store = FileEvidenceStore(tmp_path / "blobs")
    with pytest.raises(OSError):
        capture_workspace(source, store)
    assert not store.root.exists()


def test_verify_does_not_follow_swapped_nested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "file.txt").write_text("inside")
    manifest = capture_workspace(source, FileEvidenceStore(tmp_path / "blobs"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.txt").write_text("inside")

    def enumerate_then_swap(_root: Path) -> list[Path]:
        (source / "nested").rename(source / "moved")
        (source / "nested").symlink_to(outside, target_is_directory=True)
        return [source / "nested" / "file.txt"]

    monkeypatch.setattr("sentinel_replay.workspace_snapshot._regular_files", enumerate_then_swap)
    with pytest.raises(OSError):
        verify_workspace(manifest, source)


def test_restore_preflights_blob_corruption_before_creating_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("original")
    store = FileEvidenceStore(tmp_path / "blobs")
    manifest = capture_workspace(source, store)
    entry = manifest.entries[0]
    blob = store.root / "sha256" / entry.digest[7:9] / entry.digest[7:]
    blob.write_text("tampered")
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="mismatch"):
        restore_workspace(manifest, destination, store)
    assert not destination.exists()


def test_manifest_rejects_path_escape_before_restore(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("original")
    store = FileEvidenceStore(tmp_path / "blobs")
    manifest = capture_workspace(source, store)
    escaped = manifest.model_copy(
        update={"entries": (manifest.entries[0].model_copy(update={"path": "../escape"}),)}
    )
    destination = tmp_path / "restored"
    with pytest.raises(UnsafeWorkspace, match="unsafe path"):
        restore_workspace(escaped, destination, store)
    assert not destination.exists()


def test_restore_never_writes_through_swapped_nested_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "file.txt").write_text("covered")
    store = FileEvidenceStore(tmp_path / "blobs")
    manifest = capture_workspace(source, store)
    destination = tmp_path / "restored"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_mkdir = os.mkdir

    def swap_after_mkdir(path: str, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        original_mkdir(path, mode, dir_fd=dir_fd)
        if path == "nested" and dir_fd is not None:
            (destination / "nested").rmdir()
            (destination / "nested").symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(os, "mkdir", swap_after_mkdir)
    with pytest.raises(OSError):
        restore_workspace(manifest, destination, store)
    assert not (outside / "file.txt").exists()


def test_workspace_cli_snapshot_restore_verify(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("before")
    store = tmp_path / "store"
    manifest = tmp_path / "manifest.json"
    destination = tmp_path / "restored"
    runner = CliRunner()

    captured = runner.invoke(app, ["workspace", "snapshot", str(source), str(store), str(manifest)])
    restored = runner.invoke(
        app, ["workspace", "restore", str(manifest), str(store), str(destination)]
    )
    verified = runner.invoke(app, ["workspace", "verify", str(manifest), str(destination)])

    assert captured.exit_code == 0, captured.output
    assert restored.exit_code == 0, restored.output
    assert verified.exit_code == 0, verified.output
    assert "WORKSPACE_BYTES_VERIFIED files=1" in verified.stdout
    (destination / "note.txt").write_text("changed")
    changed = runner.invoke(app, ["workspace", "verify", str(manifest), str(destination)])
    assert changed.exit_code != 0


def test_capture_rejects_evidence_store_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("contents")
    with pytest.raises(UnsafeWorkspace, match="outside"):
        capture_workspace(source, FileEvidenceStore(source / "blobs"))


@given(st.binary(max_size=256))
def test_arbitrary_file_bytes_round_trip(data: bytes) -> None:
    with TemporaryDirectory(prefix="sentinel-property-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        (source / "payload.bin").write_bytes(data)
        store = FileEvidenceStore(root / "store")
        manifest = capture_workspace(source, store)
        destination = root / "restored"
        restore_workspace(manifest, destination, store)
        assert (destination / "payload.bin").read_bytes() == data
        assert verify_workspace(manifest, destination)
        (destination / "unexpected.txt").write_text("extra")
        assert not verify_workspace(manifest, destination)
