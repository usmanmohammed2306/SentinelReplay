import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import (
    LocalAnchorError,
    create_keypair,
    publish_anchor,
    sign_root,
    verify_anchor,
)


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    journal_path = agent_root / "run.jsonl"
    Journal(journal_path).append({"kind": "tool", "response": "synthetic"})
    private, public = create_keypair(tmp_path / "controller", agent_root)
    return agent_root, journal_path, private, public, tmp_path / "anchors"


def test_sign_publish_and_verify_exact_root(tmp_path: Path) -> None:
    agent_root, journal_path, private, public, anchors = _setup(tmp_path)
    verified = Journal(journal_path).verify()
    attestation = sign_root("run-001", verified, private, agent_root)
    path = publish_anchor(attestation, anchors, agent_root)
    assert path.exists()
    assert verify_anchor("run-001", verified, public, anchors)
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        publish_anchor(attestation, anchors, agent_root)


def test_changed_journal_or_signature_does_not_verify(tmp_path: Path) -> None:
    agent_root, journal_path, private, public, anchors = _setup(tmp_path)
    original = Journal(journal_path).verify()
    attestation = sign_root("run-001", original, private, agent_root)
    path = publish_anchor(attestation, anchors, agent_root)
    data = json.loads(path.read_text())
    data["signature_b64"] = "AAAA"
    path.write_text(json.dumps(data))
    assert not verify_anchor("run-001", original, public, anchors)
    Journal(journal_path).append({"kind": "tool", "response": "changed"})
    with pytest.raises(FileNotFoundError):
        verify_anchor("run-001", Journal(journal_path).verify(), public, anchors)


def test_duplicate_attestation_json_keys_are_rejected(tmp_path: Path) -> None:
    agent_root, journal_path, private, public, anchors = _setup(tmp_path)
    verified = Journal(journal_path).verify()
    path = publish_anchor(sign_root("run-001", verified, private, agent_root), anchors, agent_root)
    data = path.read_text()
    path.write_text(data.replace('"run_id":"run-001"', '"run_id":"run-001","run_id":"run-001"'))
    with pytest.raises(LocalAnchorError, match="duplicate JSON key"):
        verify_anchor("run-001", verified, public, anchors)


def test_wrong_public_key_and_unsafe_private_permissions_fail(tmp_path: Path) -> None:
    agent_root, journal_path, private, _public, anchors = _setup(tmp_path)
    other_private, other_public = create_keypair(tmp_path / "other-controller", agent_root)
    verified = Journal(journal_path).verify()
    publish_anchor(sign_root("run-001", verified, private, agent_root), anchors, agent_root)
    assert not verify_anchor("run-001", verified, other_public, anchors)
    private.chmod(0o644)
    with pytest.raises(LocalAnchorError, match="mode 0600"):
        sign_root("run-002", verified, private, agent_root)
    assert other_private.exists()


def test_symlinked_or_writable_anchor_directory_fails(tmp_path: Path) -> None:
    agent_root, journal_path, private, public, anchors = _setup(tmp_path)
    verified = Journal(journal_path).verify()
    publish_anchor(sign_root("run-001", verified, private, agent_root), anchors, agent_root)
    alias = tmp_path / "anchor-alias"
    alias.symlink_to(anchors, target_is_directory=True)
    with pytest.raises(LocalAnchorError, match="real directories"):
        verify_anchor("run-001", verified, public, alias)
    run_dir = anchors / "run-001"
    run_dir.chmod(0o777)
    with pytest.raises(LocalAnchorError, match="group/world writable"):
        verify_anchor("run-001", verified, public, anchors)


def test_controller_material_cannot_be_inside_declared_agent_root(tmp_path: Path) -> None:
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    with pytest.raises(LocalAnchorError, match="outside the agent workspace"):
        create_keypair(agent_root / "controller", agent_root)
    journal = Journal(agent_root / "run.jsonl")
    verified = journal.append({"event": "synthetic"})
    private, _public = create_keypair(tmp_path / "controller", agent_root)
    attestation = sign_root("run-001", verified, private, agent_root)
    with pytest.raises(LocalAnchorError, match="outside the agent workspace"):
        publish_anchor(attestation, agent_root / "anchors", agent_root)


def test_cli_local_anchor_round_trip(tmp_path: Path) -> None:
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    journal_path = agent_root / "run.jsonl"
    Journal(journal_path).append({"event": "synthetic"})
    controller = tmp_path / "controller"
    anchors = tmp_path / "anchors"
    runner = CliRunner()
    created = runner.invoke(app, ["local-anchor", "keygen", str(controller), str(agent_root)])
    assert created.exit_code == 0, created.output
    signed = runner.invoke(
        app,
        [
            "local-anchor",
            "sign",
            str(journal_path),
            "run-001",
            str(controller / "signing.ed25519.key"),
            str(anchors),
            str(agent_root),
        ],
    )
    assert signed.exit_code == 0, signed.output
    checked = runner.invoke(
        app,
        [
            "local-anchor",
            "verify",
            str(journal_path),
            "run-001",
            str(controller / "signing.ed25519.pub"),
            str(anchors),
        ],
    )
    assert checked.exit_code == 0, checked.output
    assert "DEV_LOCAL_ANCHOR_VALID" in checked.output
