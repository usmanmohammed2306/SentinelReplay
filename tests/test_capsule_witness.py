import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.capsule import export_capsule
from sentinel_replay.capsule_witness import WitnessError, publish_witness, require_witness
from sentinel_replay.database import metadata
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule


def test_witness_pins_exact_signed_capsule_even_after_database_reset(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    journal = agent / "journal.jsonl"
    Journal(journal).append({"kind": "test", "value": "synthetic"})
    private, public = create_keypair(tmp_path / "signer", agent)
    capsule = tmp_path / "original.sentinel"
    export_capsule("witness-run", journal, capsule)
    statement = sign_capsule(capsule, private, tmp_path / "statements", agent)
    root = tmp_path / "operator-witness"
    path = publish_witness(capsule, statement, public, root, agent)
    assert path.stat().st_mode & 0o777 == 0o444
    assert publish_witness(capsule, statement, public, root, agent) == path
    assert require_witness(root, statement.read_bytes()).run_id == "witness-run"
    token = "test-token-with-at-least-thirty-two-characters"
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}")
    metadata.create_all(engine)
    client = TestClient(
        create_app(
            ApiSettings(
                database_url=str(engine.url),
                evidence_root=tmp_path / "cas",
                trusted_public_key=public,
                api_token=token,
                witness_root=root,
            ),
            engine=engine,
        )
    )

    def upload(archive: Path, signed: Path) -> int:
        return client.post(
            "/v1/runs/import",
            content=archive.read_bytes(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/octet-stream",
                "X-Sentinel-Attestation": base64.b64encode(signed.read_bytes()).decode(),
            },
        ).status_code

    assert upload(capsule, statement) == 201
    assert upload(capsule, statement) == 200
    metadata.drop_all(engine)
    metadata.create_all(engine)
    other = tmp_path / "other.sentinel"
    Journal(journal).append({"kind": "test", "value": "changed"})
    export_capsule("witness-run", journal, other)
    other_statement = sign_capsule(other, private, tmp_path / "statements", agent)
    assert upload(other, other_statement) == 422  # Valid key, wrong retained witness.
    with pytest.raises(WitnessError):
        publish_witness(other, other_statement, public, root, agent)
    assert upload(capsule, statement) == 201
    pinned = path.read_bytes()
    path.unlink()
    headers = {"Authorization": "Bearer " + token}
    assert client.post("/v1/runs/witness-run/replay", headers=headers).status_code == 503
    path.write_bytes(pinned)
    assert require_witness(root, statement.read_bytes()).run_id == "witness-run"


def test_witness_rejects_symlinks_unsafe_root_and_malformed_statement(tmp_path: Path) -> None:
    root = tmp_path / "witness"
    root.mkdir()
    with pytest.raises(WitnessError):
        require_witness(root, b'{"run_id":"../escape"}')
    root.chmod(0o777)
    with pytest.raises(WitnessError):
        require_witness(root, b"{}")
    root.chmod(0o755)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(WitnessError):
        require_witness(alias, b"{}")
