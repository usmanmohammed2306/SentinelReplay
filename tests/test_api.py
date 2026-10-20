import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.capsule import export_capsule
from sentinel_replay.database import metadata
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule

TOKEN = "synthetic-test-token-with-32-characters-minimum"


def _setup(tmp_path: Path) -> tuple[TestClient, Path, Path, Path, Path]:
    agent = tmp_path / "agent"
    agent.mkdir()
    journal = agent / "run.jsonl"
    Journal(journal).append({"kind": "tool", "response": "synthetic-only"})
    private, public = create_keypair(tmp_path / "controller", agent)
    capsule = tmp_path / "run.sentinel"
    export_capsule("run-001", journal, capsule)
    statement = sign_capsule(capsule, private, tmp_path / "anchors", agent)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    settings = ApiSettings(
        database_url=str(engine.url),
        evidence_root=tmp_path / "evidence",
        trusted_public_key=public,
        api_token=TOKEN,
    )
    return TestClient(create_app(settings, engine=engine)), capsule, statement, private, agent


def _headers(statement: Path, token: str = TOKEN) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode("ascii"),
        "Content-Type": "application/octet-stream",
    }


def test_signed_import_is_persistent_idempotent_and_private(tmp_path: Path) -> None:
    client, capsule, statement, _private, _agent = _setup(tmp_path)
    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/runs").status_code == 401
    imported = client.post(
        "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(statement)
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["run_id"] == "run-001"
    assert "synthetic-only" not in imported.text
    repeat = client.post(
        "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(statement)
    )
    assert repeat.status_code == 200
    listed = client.get("/v1/runs", headers={"Authorization": f"Bearer {TOKEN}"})
    assert listed.status_code == 200
    assert [run["run_id"] for run in listed.json()["runs"]] == ["run-001"]
    assert "synthetic-only" not in listed.text
    downloaded = client.get(
        "/v1/runs/run-001/capsule", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert downloaded.status_code == 200
    assert downloaded.content == capsule.read_bytes()
    assert downloaded.headers["cache-control"] == "no-store"
    assert client.get("/v1/runs/run-001/capsule").status_code == 401


def test_invalid_signature_and_conflicting_run_fail_closed(tmp_path: Path) -> None:
    client, capsule, statement, private, agent = _setup(tmp_path)
    bad_statement = tmp_path / "wrong.sig.json"
    bad_statement.write_text(statement.read_text().replace("Ed25519", "invalid-algorithm"))
    rejected = client.post(
        "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(bad_statement)
    )
    assert rejected.status_code == 422
    assert client.get("/v1/runs", headers={"Authorization": f"Bearer {TOKEN}"}).json()["runs"] == []

    assert (
        client.post(
            "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(statement)
        ).status_code
        == 201
    )
    report = agent / "different.json"
    report.write_text('{"result":"changed"}\n')
    different = tmp_path / "different.sentinel"
    export_capsule("run-001", agent / "run.jsonl", different, {"different.json": report})
    other_statement = sign_capsule(different, private, tmp_path / "anchors", agent)
    conflict = client.post(
        "/v1/runs/import", content=different.read_bytes(), headers=_headers(other_statement)
    )
    assert conflict.status_code == 409


def test_capsule_read_back_fails_closed_on_corruption(tmp_path: Path) -> None:
    client, capsule, statement, _private, _agent = _setup(tmp_path)
    imported = client.post(
        "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(statement)
    )
    assert imported.status_code == 201
    digest = imported.json()["capsule_digest"]
    path = FileEvidenceStore(tmp_path / "evidence")._path(digest)
    path.write_bytes(b"modified")
    response = client.get("/v1/runs/run-001/capsule", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert response.json() == {"detail": "stored evidence unavailable"}


def test_auth_and_body_limit_reject_before_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sentinel_replay.api as api_module

    client, capsule, statement, _private, _agent = _setup(tmp_path)
    wrong = client.post(
        "/v1/runs/import", content=capsule.read_bytes(), headers=_headers(statement, "wrong")
    )
    assert wrong.status_code == 401
    monkeypatch.setattr(api_module, "MAX_ARCHIVE_BYTES", 10)
    oversized = client.post("/v1/runs/import", content=b"x" * 11, headers=_headers(statement))
    assert oversized.status_code == 413
