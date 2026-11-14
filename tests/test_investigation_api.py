"""Real signed branch data through authorization, queries and replay endpoints."""

import base64
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.access import AccessGrant, token_digest
from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.database import metadata
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule

CAPSULE = Path(__file__).resolve().parents[1] / (
    "benchmarks/results/isolated-branches-final-2026-11-13/"
    "protected_export--allow_both/controller/branch.sentinel"
)
ADMIN = "synthetic-administrator-token-for-tests-only"
READER = "synthetic-restricted-reader-token-for-tests-only"


@pytest.mark.parametrize("encrypted", [False, True])
def test_complete_investigation_api_with_scope_and_run_boundaries(
    tmp_path: Path, encrypted: bool
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    private, public = create_keypair(tmp_path / "keys", agent)
    statement = sign_capsule(CAPSULE, private, tmp_path / "anchors", agent)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    reader = AccessGrant(
        subject="fixture-reader",
        token_sha256=token_digest(READER),
        scopes=frozenset({"metadata", "evidence"}),
        runs=frozenset({"different-run"}),
    )
    encryption_key = None
    if encrypted:
        encryption_key = tmp_path / "storage.key"
        encryption_key.touch(mode=0o600)
        encryption_key.write_bytes(os.urandom(32))
    client = TestClient(
        create_app(
            ApiSettings(
                str(engine.url), tmp_path / "evidence", public, ADMIN, (reader,), encryption_key
            ),
            engine=engine,
        )
    )
    admin = {"Authorization": "Bearer " + ADMIN}
    imported = client.post(
        "/v1/runs/import",
        content=CAPSULE.read_bytes(),
        headers={
            **admin,
            "Content-Type": "application/octet-stream",
            "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
        },
    )
    assert imported.status_code == 201
    run_id = imported.json()["run_id"]
    base = "/v1/runs/" + run_id
    for route in ("investigation", "timeline", "phases", "incidents", "provenance", "verification"):
        response = client.get(base + "/" + route, headers=admin)
        assert response.status_code == 200, (route, response.text)
        assert "SENTINEL_BRANCH_SYNTHETIC_ONLY" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert client.get(base + "/" + route).status_code == 401
    stream = client.get(base + "/events", headers={**admin, "Last-Event-ID": "1"})
    assert stream.status_code == 200
    assert stream.text.startswith("id: 2\n")
    replay = client.post(base + "/replay", headers=admin)
    assert replay.status_code == 200
    assert replay.json()["mode"] == "BOUNDARY_REPLAY_MATCHED"
    assert replay.json()["checkpoints"] == {"workspace": True, "fixture": True}
    restricted = {"Authorization": "Bearer " + READER}
    assert client.get("/v1/runs", headers=restricted).json()["runs"] == []
    assert client.get("/v1/runs", headers=restricted).json()["next_cursor"] is None
    assert client.get(base, headers=restricted).status_code == 403
    assert client.get(base + "/timeline", headers=restricted).status_code == 403
    assert client.post(base + "/replay", headers=restricted).status_code == 403
    assert client.get(base + "/capsule", headers=restricted).status_code == 403
    assert client.get(base + "/timeline?root=wrong", headers=admin).status_code == 409
    assert client.get(base + "/events?after=99999", headers=admin).status_code == 409
    if encrypted:
        from sentinel_replay.capsule_privacy import unseal

        assert encryption_key is not None
        sealed = client.get(base + "/capsule?sealed=true", headers=admin)
        assert unseal(sealed.content, encryption_key) == CAPSULE.read_bytes()
    assert client.get(base + "/attestation", headers=admin).content == statement.read_bytes()
    assert (
        client.post(
            base + "/retire", json={"reason": "operator_deletion"}, headers=restricted
        ).status_code
        == 403
    )
    retirement = client.post(base + "/retire", json={"reason": "operator_deletion"}, headers=admin)
    assert retirement.status_code == 200
    assert retirement.json()["physical_deletion"] == "pending_offline_collection"
    assert (
        client.post(base + "/retire", json={"reason": "operator_deletion"}, headers=admin).json()
        == retirement.json()
    )
    assert client.get(base + "/capsule", headers=admin).status_code == 410
    assert client.post(base + "/replay", headers=admin).status_code == 410
    assert client.get("/v1/runs", headers=admin).json()["runs"] == []
