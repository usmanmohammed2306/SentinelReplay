"""Loopback-only UI test fixture; retained evidence, disposable SQLite index.

This is not the PostgreSQL deployment. No candidate, model, Docker or cloud call
is performed. The test token is explicitly synthetic and only grants access to
this temporary fixture; never reuse it for real evidence.
"""

import base64
import os
import tempfile
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sentinel_replay.api import ApiSettings, create_app
from sentinel_replay.database import metadata
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.experiment_capsule import export_experiment
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Policy
from sentinel_replay.signed_capsule import sign_capsule

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-ui-test-token-not-for-real-evidence-2026"


def main() -> None:
    os.chdir(ROOT)
    with tempfile.TemporaryDirectory(prefix="sentinel-ui-fixture-") as temporary:
        root = Path(temporary)
        agent = root / "declared-agent"
        agent.mkdir()
        private, public = create_keypair(root / "keys", agent)
        engine = create_engine(f"sqlite+pysqlite:///{root / 'metadata.db'}")
        metadata.create_all(engine)
        app = create_app(
            ApiSettings(str(engine.url), root / "evidence", public, TOKEN), engine=engine
        )
        capsule_paths = list(
            (ROOT / "benchmarks/results/isolated-branches-final-2026-11-13").glob(
                "*/controller/branch.sentinel"
            )
        )
        capsule_paths.append(
            ROOT
            / "benchmarks/results/live-isolated-branches-structured-tools-2026-11-13"
            / "protected_export--allow_both/controller/branch.sentinel"
        )
        experiment = root / "live-experiment.sentinel"
        export_experiment(
            ROOT / "benchmarks/results/live-isolated-branches-structured-tools-2026-11-13",
            experiment,
        )
        capsule_paths.append(experiment)
        pack = Pack(
            name="ui-proof",
            files={"secret.txt": "SYNTHETIC_ONLY"},
            steps=(
                PackStep(
                    action=Action(
                        operation="read_file", resource="secret.txt", sensitivity="secret"
                    )
                ),
                PackStep(
                    action=Action(
                        operation="http_post", resource="out.txt", host="outside.invalid"
                    ),
                    from_step=0,
                ),
                PackStep(
                    action=Action(operation="write_file", resource="report.txt"),
                    value="public-report",
                ),
            ),
        )
        pack_source = root / "pack"
        record_pack(
            pack, pack_source, Policy(), decisions=["allowed"] * 3, decision_source="test_fixture"
        )
        pack_capsule = root / "pack.sentinel"
        export_pack(pack_source, pack_capsule)
        capsule_paths.append(pack_capsule)
        capsule_paths.append(
            ROOT / "benchmarks/results/product-demo-final-2026-11-13/investigation.sentinel"
        )
        scale_pack = Pack(
            name="ui-scale-50000",
            files={},
            steps=tuple(
                PackStep(action=Action(operation="model_call"), value="frozen-stub")
                for _ in range(50000)
            ),
        )
        scale_source = root / "scale-pack"
        record_pack(
            scale_pack,
            scale_source,
            Policy(),
            decisions=["allowed"] * 50000,
            decision_source="UI_scale_fixture_fixed_vector_no_live_model_or_OPA",
        )
        scale_capsule = root / "scale.sentinel"
        export_pack(scale_source, scale_capsule)
        capsule_paths.append(scale_capsule)
        with TestClient(app) as client:
            for capsule in capsule_paths:
                statement = sign_capsule(capsule, private, root / "anchors", agent)
                response = client.post(
                    "/v1/runs/import",
                    content=capsule.read_bytes(),
                    headers={
                        "Authorization": "Bearer " + TOKEN,
                        "Content-Type": "application/octet-stream",
                        "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
                    },
                )
                if response.status_code != 201:
                    raise RuntimeError("fixture signed import failed")
        uvicorn.run(
            app, host="127.0.0.1", port=int(os.environ.get("SENTINEL_UI_FIXTURE_PORT", "18771"))
        )


if __name__ == "__main__":
    main()
