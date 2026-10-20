import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import sentinel_replay.signed_capsule as signed_capsule_module
from sentinel_replay.capsule import export_capsule, read_capsule_bytes, verify_capsule
from sentinel_replay.cli import app
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import (
    SignedCapsuleError,
    import_signed_capsule,
    sign_capsule,
    verify_signed_capsule,
    verify_signed_capsule_material,
)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    agent = tmp_path / "agent"
    agent.mkdir()
    journal = agent / "run.jsonl"
    Journal(journal).append({"kind": "tool", "result": "synthetic"})
    report = agent / "report.json"
    report.write_text('{"finding":"blocked"}\n')
    capsule = tmp_path / "run.sentinel"
    export_capsule("run-001", journal, capsule, {"report.json": report})
    private, public = create_keypair(tmp_path / "controller", agent)
    return agent, capsule, private, public, report


def test_signed_capsule_covers_every_archive_byte_and_is_put_once(tmp_path: Path) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    anchors = tmp_path / "anchors"
    attestation = sign_capsule(capsule, private, anchors, agent)
    assert verify_signed_capsule(capsule, attestation, public)
    assert verify_signed_capsule_material(
        capsule.read_bytes(), attestation.read_bytes(), public.read_bytes()
    )
    assert attestation.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        sign_capsule(capsule, private, anchors, agent)


def test_self_consistent_rewrite_passes_unsigned_but_fails_signed(tmp_path: Path) -> None:
    agent, capsule, private, public, report = _fixture(tmp_path)
    attestation = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    report.write_text('{"finding":"allowed"}\n')
    rewritten = tmp_path / "rewritten.sentinel"
    export_capsule("run-001", agent / "run.jsonl", rewritten, {"report.json": report})
    assert verify_capsule(rewritten) == verify_capsule(capsule)
    assert not verify_signed_capsule(rewritten, attestation, public)
    destination = tmp_path / "should-not-exist"
    with pytest.raises(SignedCapsuleError, match="invalid capsule signature"):
        import_signed_capsule(rewritten, attestation, public, destination)
    assert not destination.exists()


def test_wrong_key_and_tampered_attestation_fail(tmp_path: Path) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    attestation = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    _wrong_private, wrong_public = create_keypair(tmp_path / "other-controller", agent)
    assert not verify_signed_capsule(capsule, attestation, wrong_public)
    document = json.loads(attestation.read_text())
    document["signature_b64"] = "AAAA"
    attestation.write_text(json.dumps(document))
    assert not verify_signed_capsule(capsule, attestation, public)


def test_duplicate_signed_statement_json_keys_are_rejected(tmp_path: Path) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    attestation = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    data = attestation.read_text()
    attestation.write_text(
        data.replace('"run_id":"run-001"', '"run_id":"run-001","run_id":"run-001"')
    )
    with pytest.raises(SignedCapsuleError, match="duplicate JSON key"):
        verify_signed_capsule(capsule, attestation, public)


def test_symlink_and_agent_controlled_attestation_are_rejected(tmp_path: Path) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    with pytest.raises(SignedCapsuleError, match="outside the agent workspace"):
        sign_capsule(capsule, private, agent / "anchors", agent)
    attestation = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    alias = tmp_path / "alias.sentinel"
    alias.symlink_to(capsule)
    with pytest.raises(SignedCapsuleError, match="regular file"):
        verify_signed_capsule(alias, attestation, public)


def test_cli_signed_capsule_round_trip(tmp_path: Path) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    anchors = tmp_path / "anchors"
    runner = CliRunner()
    signed = runner.invoke(
        app,
        ["capsule", "sign-local", str(capsule), str(private), str(anchors), str(agent)],
    )
    assert signed.exit_code == 0, signed.output
    assert "DEV_LOCAL_CAPSULE_SIGNED" in signed.output
    attestation = anchors / "capsules" / "run-001" / (capsule.name + ".sig.json")
    verified = runner.invoke(
        app,
        ["capsule", "verify-signed", str(capsule), str(attestation), str(public)],
    )
    assert verified.exit_code == 0, verified.output
    assert "DEV_LOCAL_CAPSULE_SIGNATURE_VALID" in verified.output
    imported_dir = tmp_path / "signed-import"
    imported = runner.invoke(
        app,
        [
            "capsule",
            "import-signed",
            str(capsule),
            str(attestation),
            str(public),
            str(imported_dir),
        ],
    )
    assert imported.exit_code == 0, imported.output
    assert "DEV_LOCAL_SIGNED_CAPSULE_IMPORTED" in imported.output
    assert (imported_dir / "artifacts" / "report.json").read_text() == '{"finding":"blocked"}\n'


def test_signed_import_uses_exact_verified_bytes_after_source_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, capsule, private, public, _report = _fixture(tmp_path)
    attestation = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    original_reader = read_capsule_bytes

    def read_then_replace(path: Path) -> bytes:
        data = original_reader(path)
        path.write_bytes(b"replaced after bounded read")
        return data

    monkeypatch.setattr(signed_capsule_module, "read_capsule_bytes", read_then_replace)
    destination = tmp_path / "imported"
    result = import_signed_capsule(capsule, attestation, public, destination)
    assert result.run_id == "run-001"
    assert (destination / "artifacts" / "report.json").read_text() == '{"finding":"blocked"}\n'
