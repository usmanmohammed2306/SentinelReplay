import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.capsule import (
    CapsuleError,
    export_capsule,
    import_capsule,
    verify_capsule,
    verify_imported,
)
from sentinel_replay.cli import app
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import Journal


def _journal(path: Path) -> None:
    Journal(path).append({"kind": "tool", "response": "sensitive"})


def test_round_trip_and_deterministic_bytes(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    report = tmp_path / "report.json"
    report.write_text('{"finding":"blocked"}\n')
    first = tmp_path / "one.sentinel"
    second = tmp_path / "two.sentinel"
    expected = export_capsule("run-001", journal, first, {"report.json": report})
    export_capsule("run-001", journal, second, {"report.json": report})

    assert first.read_bytes() == second.read_bytes()
    assert verify_capsule(first) == expected
    restored = tmp_path / "restored"
    assert import_capsule(first, restored) == expected
    assert verify_imported(restored) == expected
    assert Journal(restored / "journal.jsonl").verify().root == expected.root
    assert (restored / "artifacts" / "report.json").read_bytes() == report.read_bytes()


def test_modified_entry_fails_before_import_directory_exists(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    capsule = tmp_path / "good.sentinel"
    export_capsule("run", journal, capsule)
    altered = tmp_path / "altered.sentinel"
    with zipfile.ZipFile(capsule) as source, zipfile.ZipFile(altered, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "journal.jsonl":
                data = data.replace(b"sensitive", b"tampered!")
            target.writestr(name, data)
    destination = tmp_path / "should-not-exist"
    with pytest.raises(CapsuleError, match="digest mismatch"):
        import_capsule(altered, destination)
    assert not destination.exists()


@pytest.mark.parametrize("extra", ["../escape", "artifacts/../../escape", "artifacts/x/y"])
def test_unlisted_or_traversing_paths_fail_before_extraction(tmp_path: Path, extra: str) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    capsule = tmp_path / "malicious.sentinel"
    with zipfile.ZipFile(capsule, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("journal.jsonl", journal.read_bytes())
        archive.writestr(extra, b"bad")
    destination = tmp_path / "imported"
    with pytest.raises(CapsuleError):
        import_capsule(capsule, destination)
    assert not destination.exists()


def test_duplicate_member_and_compressed_entry_rejected(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    for compressed in (False, True):
        capsule = tmp_path / f"bad-{compressed}.sentinel"
        with zipfile.ZipFile(capsule, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr(
                "journal.jsonl",
                journal.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED,
            )
            if not compressed:
                with pytest.warns(UserWarning, match="Duplicate name"):
                    archive.writestr("journal.jsonl", journal.read_bytes())
        with pytest.raises(CapsuleError):
            verify_capsule(capsule)


def test_manifest_traversal_and_unsupported_version_rejected(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    for malicious in ("artifacts/../escape", "artifacts/nested/file", "../escape"):
        capsule = tmp_path / f"bad-{len(malicious)}-{malicious.count('/')}"
        journal_data = journal.read_bytes()
        manifest = {
            "schema_version": 1,
            "integrity": "hash-chain-and-digests;unsigned",
            "run_id": "run",
            "journal": {"records": 1, "root": Journal(journal).verify().root},
            "entries": [
                {"path": malicious, "size": 1, "digest": blob_digest(b"x")},
                {
                    "path": "journal.jsonl",
                    "size": len(journal_data),
                    "digest": blob_digest(journal_data),
                },
            ],
        }
        with zipfile.ZipFile(capsule, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("journal.jsonl", journal_data)
            archive.writestr(malicious, b"x")
        with pytest.raises(CapsuleError, match="unsafe capsule path"):
            verify_capsule(capsule)
    manifest["schema_version"] = 2
    versioned = tmp_path / "version-2.sentinel"
    with zipfile.ZipFile(versioned, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("journal.jsonl", journal_data)
        archive.writestr(malicious, b"x")
    with pytest.raises(CapsuleError, match="unsupported capsule schema"):
        verify_capsule(versioned)


def test_conflict_and_unsafe_source_rejected(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    capsule = tmp_path / "run.sentinel"
    export_capsule("run", journal, capsule)
    with pytest.raises(CapsuleError, match="already exists"):
        export_capsule("run", journal, capsule)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(CapsuleError, match="already exists"):
        import_capsule(capsule, existing)
    symlink = tmp_path / "link"
    symlink.symlink_to(journal)
    with pytest.raises(CapsuleError, match="regular file"):
        export_capsule("run", symlink, tmp_path / "other.sentinel")


def test_cli_export_verify_import_and_imported_boundary_replay(tmp_path: Path) -> None:
    runner = CliRunner()
    recorded = tmp_path / "incident.jsonl"
    assert runner.invoke(app, ["mini", "record", "incident", str(recorded)]).exit_code == 0
    capsule = tmp_path / "incident.sentinel"
    result = runner.invoke(app, ["capsule", "export", "incident-001", str(recorded), str(capsule)])
    assert result.exit_code == 0, result.output
    assert "UNSIGNED_CAPSULE_EXPORTED" in result.output
    verified = runner.invoke(app, ["capsule", "verify", str(capsule)])
    assert verified.exit_code == 0, verified.output
    imported = tmp_path / "imported"
    assert runner.invoke(app, ["capsule", "import", str(capsule), str(imported)]).exit_code == 0
    replay = runner.invoke(app, ["capsule", "replay-imported", "incident", str(imported)])
    assert replay.exit_code == 0, replay.output
    assert "BOUNDARY_REPLAY_MATCHED" in replay.output
    manifest = json.loads((imported / "manifest.json").read_text())
    assert manifest["integrity"].endswith("unsigned")
    (imported / "journal.jsonl").write_bytes(b"tampered\n")
    rejected = runner.invoke(app, ["capsule", "replay-imported", "incident", str(imported)])
    assert rejected.exit_code != 0
    assert "digest mismatch" in rejected.output


def test_imported_extra_file_and_symlink_fail_closed(tmp_path: Path) -> None:
    journal = tmp_path / "source.jsonl"
    _journal(journal)
    capsule = tmp_path / "run.sentinel"
    export_capsule("run", journal, capsule)
    restored = tmp_path / "restored"
    import_capsule(capsule, restored)
    extra = restored / "extra.txt"
    extra.write_text("unlisted")
    with pytest.raises(CapsuleError, match="file set"):
        verify_imported(restored)
    extra.unlink()
    extra.symlink_to(journal)
    with pytest.raises(CapsuleError, match="symlink"):
        verify_imported(restored)
