import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.canonical import event_digest
from sentinel_replay.capsule import export_capsule
from sentinel_replay.database import metadata
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule
from sentinel_replay.trust_registry import TrustedKey, TrustRegistry


def test_rotation_retirement_revocation_and_epoch_rollback_are_distinct(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    first_private, first_public = create_keypair(tmp_path / "first-key", agent)
    second_private, second_public = create_keypair(tmp_path / "second-key", agent)

    def entry(path: Path, state: str) -> TrustedKey:
        raw = path.read_bytes()
        return TrustedKey.model_validate(
            {
                "key_id": blob_digest(raw),
                "public_key_b64": base64.b64encode(raw).decode(),
                "state": state,
            }
        )

    registry = tmp_path / "trust.json"

    def configure(epoch: int, state: str, include_second: bool = True) -> None:
        keys = [entry(first_public, state)]
        if include_second:
            keys.append(entry(second_public, "active"))
        registry.write_text(TrustRegistry(epoch=epoch, keys=tuple(keys)).model_dump_json())

    configure(1, "active", False)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    token = "synthetic-trust-registry-token-never-production"
    app = create_app(
        ApiSettings(
            str(engine.url), tmp_path / "cas", first_public, token, trust_registry=registry
        ),
        engine=engine,
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + token}
        paths = []
        for name, key in (("first", first_private), ("second", second_private)):
            journal = tmp_path / f"{name}.jsonl"
            request = {"fixture": name}
            Journal(journal).append(
                {
                    "kind": "tool",
                    "sequence": 0,
                    "call_id": "fixture-0",
                    "request": request,
                    "request_digest": event_digest(request),
                    "response": "fixture",
                    "evidence": {"operation": "model_call"},
                }
            )
            capsule = tmp_path / f"{name}.sentinel"
            export_capsule(name, journal, capsule)
            statement = sign_capsule(capsule, key, tmp_path / f"{name}-anchors", agent)
            paths.append((capsule, statement))

        def ingest(index: int) -> int:
            capsule, statement = paths[index]
            return client.post(
                "/v1/runs/import",
                content=capsule.read_bytes(),
                headers={
                    **headers,
                    "Content-Type": "application/octet-stream",
                    "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
                },
            ).status_code

        assert ingest(0) == 201
        assert ingest(1) == 422
        assert (
            client.get("/v1/runs/first/attestation", headers=headers).content
            == paths[0][1].read_bytes()
        )
        verification = client.get("/v1/runs/first/verification", headers=headers).json()
        assert verification["signature"] == "cryptographic_signature_valid"
        assert verification["signer_status"] == "active"
        configure(2, "retired")
        assert ingest(1) == 201
        assert ingest(0) == 422
        assert client.post("/v1/runs/first/replay", headers=headers).status_code == 200
        configure(1, "active", False)
        assert client.get("/v1/runs/first/verification", headers=headers).status_code == 503
        configure(2, "revoked")
        assert client.get("/v1/runs/first/verification", headers=headers).status_code == 503
        configure(3, "revoked")
        assert client.post("/v1/runs/first/replay", headers=headers).status_code == 409
        verification = client.get("/v1/runs/first/verification", headers=headers).json()
        assert verification["signature"] == "cryptographic_signature_valid"
        assert verification["signer_status"] == "revoked"


def test_expired_and_future_keys_cannot_authorize_new_ingest() -> None:
    raw = b"p" * 32
    key = TrustedKey(
        key_id=blob_digest(raw),
        public_key_b64=base64.b64encode(raw).decode(),
        not_after=datetime(2026, 1, 1, tzinfo=UTC),
    )
    registry = TrustRegistry(epoch=1, keys=(key,))
    assert registry.status(key.key_id, now=datetime(2026, 11, 13, tzinfo=UTC)) == "expired"
    with pytest.raises(ValueError, match="not active"):
        registry.import_key(key.key_id, now=datetime(2026, 11, 13, tzinfo=UTC))
