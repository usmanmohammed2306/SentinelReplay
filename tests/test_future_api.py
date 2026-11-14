import base64
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.database import metadata
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Policy
from sentinel_replay.signed_capsule import sign_capsule


def test_finite_future_receipt_is_bound_to_parent_and_JSON_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    private, public = create_keypair(tmp_path / "keys", agent)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    token = "synthetic-future-API-token-never-real-evidence"
    client = TestClient(
        create_app(ApiSettings(str(engine.url), tmp_path / "cas", public, token), engine=engine)
    )
    headers = {"Authorization": "Bearer " + token}
    runs = []
    for name in ("first", "second"):
        pack = Pack(name=name, files={}, steps=(PackStep(action=Action(operation="model_call")),))
        source = tmp_path / name
        record_pack(pack, source, Policy(), decisions=["allowed"], decision_source="test_fixture")
        capsule = tmp_path / f"{name}.sentinel"
        export_pack(source, capsule)
        statement = sign_capsule(capsule, private, tmp_path / "anchors", agent)
        response = client.post(
            "/v1/runs/import",
            content=capsule.read_bytes(),
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
                "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
            },
        )
        assert response.status_code == 201
        runs.append(response.json()["run_id"])
    # This checks API receipt flow; the deployed rehearsal separately uses native OPA.
    monkeypatch.setattr("sentinel_replay.futures.evaluate_batch", lambda *a, **k: ["allowed"])
    base = "/v1/runs/" + runs[0]
    response = client.post(
        base + "/fork", json={"policy": {"schema_version": 2, "rules": []}}, headers=headers
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["mode"] == "DETERMINISTIC_SIMULATION"
    assert value["future_replay"]["mode"] == "VERIFIED_REPLAY"
    tail = f"/futures/{value['future_id']}?size={value['receipt_size']}"
    assert client.get(base + tail, headers=headers).status_code == 200
    assert client.get("/v1/runs/" + runs[1] + tail, headers=headers).status_code == 404
    assert client.get(base + tail).status_code == 401
    response = client.post(
        base + "/fork", content=(b"x" * 32768 for _ in range(3)), headers=headers
    )
    assert response.status_code == 413
    assert client.get(base + "/telemetry", headers=headers).json()["matched_spans"] == 1
    with client:
        accepted = client.post(base + "/jobs", json={"kind": "replay"}, headers=headers)
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]
        job_path = base + "/jobs/" + job_id
        deadline = time.monotonic() + 10
        while True:
            job = client.get(job_path, headers=headers).json()
            if job["state"] in {"completed", "failed", "interrupted"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert job["state"] == "completed", job
        assert (
            client.get(job_path + "/result", headers=headers).json()["report"]["mode"]
            == "VERIFIED_REPLAY"
        )
        assert client.get(base + "/jobs", headers=headers).json()["jobs"][0]["job_id"] == job_id
        stream = client.get(
            job_path + "/events", headers={**headers, "Last-Event-ID": str(job["sequence"] - 1)}
        )
        assert stream.status_code == 200 and stream.text.startswith(f"id: {job['sequence']}\n")
        assert '"state": "completed"' in stream.text
        assert client.get(job_path).status_code == 401
        assert (
            client.get("/v1/runs/" + runs[1] + "/jobs/" + job_id, headers=headers).status_code
            == 404
        )
        assert client.get(job_path + "/events?after=99999", headers=headers).status_code == 409
