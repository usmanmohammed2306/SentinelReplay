"""Run only against an explicitly disposable, migrated localhost database."""

import base64
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.capsule import export_capsule
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule


@pytest.mark.postgres_integration
def test_signed_capsule_round_trip_on_postgres_17(tmp_path: Path) -> None:
    url = os.environ.get("SENTINEL_TEST_DATABASE_URL")
    if os.environ.get("SENTINEL_TEST_DATABASE_DISPOSABLE") != "1" or not url:
        pytest.skip("requires an explicitly disposable PostgreSQL test URL")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or parsed.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("integration test refuses a non-local PostgreSQL URL")
    agent = tmp_path / "agent"
    agent.mkdir()
    journal = agent / "run.jsonl"
    Journal(journal).append({"kind": "tool", "response": "synthetic-postgres-integration"})
    private, public = create_keypair(tmp_path / "controller", agent)
    run_id = f"pg-{uuid4().hex}"
    capsule = tmp_path / "run.sentinel"
    export_capsule(run_id, journal, capsule)
    statement = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    token = "synthetic-integration-token-with-minimum-length"
    client = TestClient(
        create_app(
            ApiSettings(
                database_url=url,
                evidence_root=tmp_path / "evidence",
                trusted_public_key=public,
                api_token=token,
            )
        )
    )
    assert client.get("/healthz").status_code == 200
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode("ascii"),
    }
    imported = client.post("/v1/runs/import", content=capsule.read_bytes(), headers=headers)
    assert imported.status_code == 201, imported.text
    assert imported.json()["run_id"] == run_id
    assert (
        client.post("/v1/runs/import", content=capsule.read_bytes(), headers=headers).status_code
        == 200
    )
    retrieved = client.get(f"/v1/runs/{run_id}", headers={"Authorization": f"Bearer {token}"})
    assert retrieved.status_code == 200
    assert retrieved.json()["capsule_digest"] == imported.json()["capsule_digest"]
    assert "synthetic-postgres-integration" not in retrieved.text
    archive = client.get(f"/v1/runs/{run_id}/capsule", headers={"Authorization": f"Bearer {token}"})
    assert archive.status_code == 200
    assert archive.content == capsule.read_bytes()
