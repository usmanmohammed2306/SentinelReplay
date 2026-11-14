"""Own-project local Compose, encrypted evidence and stopped-writer recovery proof.

Requires the two validation images already built. Never reuses a deployment,
pulls an image, publishes a service beyond loopback or removes another project.
All keys, passwords, backups and service logs stay in ignored local-controller.
"""

import argparse
import base64
import json
import math
import os
import secrets
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sentinel_replay.capsule import verify_capsule
from sentinel_replay.capsule_privacy import unseal
from sentinel_replay.capsule_witness import publish_witness
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule
from sentinel_replay.trust_registry import TrustedKey, TrustRegistry

API_IMAGE = "sentinel-replay-api:validation-20261113"
UI_IMAGE = "sentinel-replay-ui:validation-20261113"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def validate(
    capsule: Path, output: Path, *, browser_proof: bool = False, scale_capsule: Path | None = None
) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[1]
    if not output.resolve().is_relative_to(repository / ".local-controller"):
        raise ValueError("deployment receipts must be under the private local-controller root")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    agent = output / "declared-agent"
    agent.mkdir()
    private, public = create_keypair(output / "keys", agent)
    trust = output / "trust.json"
    trust.write_text(
        TrustRegistry(
            epoch=1,
            keys=(
                TrustedKey(
                    key_id=blob_digest(public.read_bytes()),
                    public_key_b64=base64.b64encode(public.read_bytes()).decode(),
                ),
            ),
        ).model_dump_json(indent=2)
    )
    key = output / "storage.key"
    key.touch(mode=0o600)
    key.write_bytes(secrets.token_bytes(32))
    statement = sign_capsule(capsule, private, output / "anchors", agent)
    witness_root = output / "operator-witness"
    witnessed = publish_witness(capsule, statement, public, witness_root, agent)
    verified = verify_capsule(capsule)
    token = secrets.token_urlsafe(32)
    api_port, ui_port = free_port(), free_port()
    env_file = output / "deployment.env"
    env_file.touch(mode=0o600)
    env_file.write_text(
        f"SENTINEL_DB_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"SENTINEL_APP_DB_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"SENTINEL_API_TOKEN={token}\n"
        f"SENTINEL_TRUSTED_PUBLIC_KEY_HOST={public}\n"
        f"SENTINEL_EVIDENCE_KEY_HOST={key}\n"
        f"SENTINEL_TRUST_REGISTRY_HOST={trust}\n"
        f"SENTINEL_WITNESS_ROOT_HOST={witness_root}\n"
    )
    override = output / "override.yaml"
    override.write_text(
        f"services:\n  migrate:\n    image: {API_IMAGE}\n"
        f"  init-evidence:\n    image: {API_IMAGE}\n"
        f"  api:\n    image: {API_IMAGE}\n"
        f"    ports: !override ['127.0.0.1:{api_port}:8000']\n"
        f"  ui:\n    image: {UI_IMAGE}\n"
        f"    ports: !override ['127.0.0.1:{ui_port}:3000']\n"
        f"    environment:\n      SENTINEL_UI_ORIGIN: http://127.0.0.1:{ui_port}\n"
    )
    projects = ["sentinel-proof-" + uuid4().hex[:16], "sentinel-restore-" + uuid4().hex[:16]]
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "scope": "disposable_local_Compose_encrypted_CAS_recovery",
        "api_image": API_IMAGE,
        "ui_image": UI_IMAGE,
        "run_id": verified.run_id,
        "journal_root": verified.root,
        "records": verified.records,
        "source_digests": {
            str(path.relative_to(repository)): blob_digest(path.read_bytes())
            for path in [
                repository / "Dockerfile",
                repository / "ui/Dockerfile",
                repository / "deploy/local/compose.yaml",
                Path(__file__),
            ]
        },
        "checks": {},
        "completed": False,
        "image_config_ids": {
            name: subprocess.check_output(
                ["docker", "image", "inspect", name, "--format", "{{.Id}}"], text=True
            ).strip()
            for name in (API_IMAGE, UI_IMAGE)
        },
    }
    log = (output / "deployment.log").open("xb")
    compose_base = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(repository / "deploy/local/compose.yaml"),
        "-f",
        str(override),
    ]

    def compose(
        project: str, *args: str, data: bytes | None = None, capture: bool = False
    ) -> bytes:
        result = subprocess.run(
            [*compose_base, "--project-name", project, *args],
            cwd=repository,
            input=data,
            stdout=subprocess.PIPE if capture else log,
            stderr=log,
            timeout=180,
            check=True,
        )
        return result.stdout or b""

    def http(
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{api_port}" + path,
                data=data,
                method=method,
                headers={"Authorization": "Bearer " + token, **(headers or {})},
            ),
            timeout=60,
        ) as response:
            return response.status, response.read()

    def wait_healthy() -> None:
        deadline = time.monotonic() + 60
        while True:
            try:
                if http("/healthz")[0] == 200:
                    with urlopen(f"http://127.0.0.1:{ui_port}", timeout=2) as response:
                        if response.status == 200:
                            return
            except (OSError, URLError):
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("own deployment did not become healthy")
            time.sleep(0.5)

    def exercise(stage: str) -> None:
        base = "/v1/runs/" + verified.run_id
        results: dict[str, Any] = {}
        for route in (
            "investigation",
            "timeline",
            "phases",
            "incidents",
            "provenance",
            "telemetry",
            "verification",
        ):
            status, data = http(base + "/" + route)
            if status != 200:
                raise ValueError("deployed investigation route failed")
            value = json.loads(data)
            if value["journal_root"] != verified.root:
                raise ValueError("deployed response changed journal binding")
            results[route] = status
        status, data = http(base + "/replay", method="POST", data=b"")
        replay = json.loads(data)
        if (
            status != 200
            or replay["mode"] != "VERIFIED_REPLAY"
            or replay["checkpoints"] != {"workspace": True, "git": True, "sqlite": True}
        ):
            raise ValueError("deployed imported replay did not restore all declared adapters")
        if http(base + "/capsule")[1] != capsule.read_bytes():
            raise ValueError("deployed capsule bytes differ")
        results["three_adapter_replay"] = True
        results["exact_decrypted_capsule"] = True
        if unseal(http(base + "/capsule?sealed=true")[1], key) != capsule.read_bytes():
            raise ValueError("sealed export differs after authenticated decryption")
        results["sealed_export_decrypted"] = True
        if stage == "original":
            status, data = http(
                base + "/jobs",
                method="POST",
                data=b'{"kind":"replay"}',
                headers={"Content-Type": "application/json"},
            )
            if status != 202:
                raise ValueError("persistent operation was not admitted")
            job_id = json.loads(data)["job_id"]
            deadline = time.monotonic() + 45
            while True:
                job = json.loads(http(base + "/jobs/" + job_id)[1])
                if job["state"] in {"completed", "failed", "interrupted"}:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError("deployed operation deadline exceeded")
                time.sleep(0.25)
            if job["state"] != "completed":
                raise ValueError("deployed background replay did not complete")
        else:
            job_id = receipt["checks"]["original"]["persistent_job_id"]
        result_data = http(base + "/jobs/" + job_id + "/result")[1]
        if json.loads(result_data)["report"]["journal_root"] != verified.root:
            raise ValueError("persistent operation result differs")
        events = http(base + "/jobs/" + job_id + "/events")[1]
        if b"completed" not in events or b"event: operation" not in events:
            raise ValueError("deployed operation stream omitted its terminal receipt")
        results["persistent_job_id"] = job_id
        results["persistent_job_result_digest"] = blob_digest(result_data)
        if (
            stage == "restored"
            and results["persistent_job_result_digest"]
            != receipt["checks"]["original"]["persistent_job_result_digest"]
        ):
            raise ValueError("restored background result bytes differ")
        results["persistent_job_and_terminal_SSE"] = True
        receipt["checks"][stage] = results

    try:
        compose(
            projects[0],
            "up",
            "--detach",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "90",
        )
        wait_healthy()
        headers = {
            "Content-Type": "application/octet-stream",
            "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
        }
        if (
            http("/v1/runs/import", method="POST", data=capsule.read_bytes(), headers=headers)[0]
            != 201
        ):
            raise ValueError("signed deployment import failed")
        if (
            http("/v1/runs/import", method="POST", data=capsule.read_bytes(), headers=headers)[0]
            != 200
        ):
            raise ValueError("deployed duplicate import is not idempotent")
        exercise("original")
        if scale_capsule is not None:
            scale_statement = sign_capsule(
                scale_capsule, private, output / "scale-statements", agent
            )
            publish_witness(scale_capsule, scale_statement, public, witness_root, agent)
            scale = verify_capsule(scale_capsule)
            if scale.records != 50000:
                raise ValueError("scale HTTP probe requires the declared50000-boundary capsule")
            status, _ = http(
                "/v1/runs/import",
                method="POST",
                data=scale_capsule.read_bytes(),
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Sentinel-Attestation": base64.b64encode(
                        scale_statement.read_bytes()
                    ).decode(),
                },
            )
            if status != 201:
                raise ValueError("scale capsule admission failed")
            paths = {
                "timeline_first_page": "/timeline?limit=100",
                "sparse_graph": "/provenance?root_step=49996&depth=3",
            }
            samples: dict[str, Any] = {}
            for label, suffix in paths.items():
                values = []
                for _ in range(25):
                    started = time.perf_counter()
                    status, body = http("/v1/runs/" + scale.run_id + suffix)
                    elapsed = time.perf_counter() - started
                    if status != 200 or json.loads(body)["journal_root"] != scale.root:
                        raise ValueError("scale HTTP query changed binding")
                    values.append(elapsed)
                ordered = sorted(values)
                samples[label] = {
                    "n": len(values),
                    "seconds": values,
                    "p50_seconds": ordered[12],
                    "p95_seconds": ordered[math.ceil(0.95 * len(values)) - 1],
                }

            def concurrent_query(_: int) -> int:
                try:
                    return http("/v1/runs/" + scale.run_id + paths["timeline_first_page"])[0]
                except HTTPError as error:
                    return error.code

            with ThreadPoolExecutor(max_workers=8) as clients:
                statuses = list(clients.map(concurrent_query, range(32)))
            if any(status not in {200, 429} for status in statuses) or 200 not in statuses:
                raise ValueError("bounded concurrency returned unexpected status")
            receipt["checks"]["HTTP_50k_scale"] = {
                "journal_root": scale.root,
                "query_samples": samples,
                "concurrent_clients": 8,
                "concurrent_requests": 32,
                "response_statuses": statuses,
                "cold_first_timeline_seconds": samples["timeline_first_page"]["seconds"][0],
                "scope": (
                    "same_host_loopback_Docker_PostgreSQL_sparse_graph; first timeline sample "
                    "includes cold index build, remaining samples warm; not UI or production SLO"
                ),
            }
        if browser_proof:
            subprocess.run(
                [
                    "node",
                    "scripts/record-proof.mjs",
                    f"http://127.0.0.1:{ui_port}",
                    str(env_file),
                    verified.run_id,
                    str(output / "browser-proof"),
                ],
                cwd=repository / "ui",
                env={
                    **os.environ,
                    "PLAYWRIGHT_BROWSERS_PATH": str(repository / ".local-controller/browsers"),
                },
                stdout=log,
                stderr=log,
                timeout=150,
                check=True,
            )
            receipt["checks"]["continuous_browser_capture"] = True
        fork_policy = {
            "schema_version": 2,
            "rules": [
                {"effect": "allow", "operation": "*"},
                {"effect": "deny", "operation": "http_post"},
            ],
        }
        _, data = http(
            "/v1/runs/" + verified.run_id + "/fork",
            method="POST",
            data=json.dumps({"policy": fork_policy, "fork_step": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        future = json.loads(data)
        if (
            future["mode"] != "DETERMINISTIC_SIMULATION"
            or not future["world_diff"]
            or any(
                row["rule_id"] == "declared_protected_materialization_v1"
                for row in future["incidents"]
            )
        ):
            raise ValueError(
                "deployed native OPA alternate future did not meet the declared fixture predicate"
            )
        receipt["checks"]["native_OPA_future"] = {
            "mode": future["mode"],
            "changed_paths": [row["path"] for row in future["world_diff"]],
            "incidents": len(future["incidents"]),
        }
        # Explicit access and byte-budget controls on the actual HTTP service.
        for label, request, expected in (
            ("unauthenticated", Request(f"http://127.0.0.1:{api_port}/v1/runs"), 401),
            (
                "oversized_JSON",
                Request(
                    f"http://127.0.0.1:{api_port}/v1/runs/{verified.run_id}/fork",
                    data=b"x" * 65537,
                    method="POST",
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                ),
                413,
            ),
        ):
            try:
                with urlopen(request, timeout=10):
                    raise ValueError("deployed negative control unexpectedly succeeded")
            except HTTPError as error:
                if error.code != expected:
                    raise ValueError("deployed negative control returned wrong status") from error
                receipt["checks"][label] = error.code
        # The signer key is not mounted in API; trusted public key is read-only.
        isolation = compose(
            projects[0],
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import os,pathlib; assert os.getuid()==10001; "
            "assert not pathlib.Path('/run/sentinel/signing.ed25519.key').exists(); "
            "p=pathlib.Path('/run/sentinel/trusted.pub');\n"
            "try: p.write_bytes(b'x')\n"
            "except OSError: pass\n"
            "else: raise AssertionError('trusted key is writable')\n",
            capture=True,
        )
        receipt["checks"]["API_nonroot_public_key_readonly"] = isolation == b""
        witness_isolation = compose(
            projects[0],
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import pathlib; p=pathlib.Path('/run/sentinel-witness'); "
            f"w=p/{witnessed.name!r}; assert w.read_bytes();\n"
            "for target in (w, p/'forged.json'):\n"
            " try: target.write_bytes(b'forged')\n"
            " except OSError: pass\n"
            " else: raise AssertionError('operator witness is writable')\n",
            capture=True,
        )
        receipt["checks"]["operator_witness_readonly"] = witness_isolation == b""
        # A database/CAS rollback cannot erase the separately retained witness.
        pinned = witnessed.read_bytes()
        witnessed.unlink()
        try:
            try:
                http(
                    f"/v1/runs/{verified.run_id}/replay",
                    method="POST",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
            except HTTPError as error:
                if error.code != 503:
                    raise
            else:
                raise ValueError("missing operator witness did not quarantine replay")
        finally:
            witnessed.write_bytes(pinned)
            witnessed.chmod(0o444)
        receipt["checks"]["missing_operator_witness_quarantines_replay"] = True
        before_crash_limits = json.loads(
            compose(
                projects[0],
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import json,pathlib; p=pathlib.Path('/sys/fs/cgroup'); "
                "print(json.dumps({name:(p/name).read_text().strip() for name in "
                "['memory.max','memory.peak','memory.events','pids.max','pids.current']}))",
                capture=True,
            )
        )
        if (
            before_crash_limits["memory.max"] != "1073741824"
            or before_crash_limits["pids.max"] != "128"
            or int(before_crash_limits["memory.peak"]) >= 1073741824
            or "oom_kill 0" not in before_crash_limits["memory.events"].splitlines()
        ):
            raise ValueError("API resource boundary failed under the50k query workload")
        receipt["checks"]["bounded_API_cgroup_before_crash"] = before_crash_limits
        # Crash an actually admitted, running job; startup must mark uncertainty explicitly.
        base = "/v1/runs/" + verified.run_id
        status, accepted = http(
            base + "/jobs",
            method="POST",
            data=b'{"kind":"policy_search"}',
            headers={"Content-Type": "application/json"},
        )
        if status != 202:
            raise ValueError("crash rehearsal job was not admitted")
        interrupted_job_id = json.loads(accepted)["job_id"]
        deadline = time.monotonic() + 20
        while True:
            job = json.loads(http(base + "/jobs/" + interrupted_job_id)[1])
            if job["state"] == "running":
                break
            if (
                job["state"] in {"completed", "failed", "interrupted"}
                or time.monotonic() > deadline
            ):
                raise ValueError("crash rehearsal did not observe a running job")
            time.sleep(0.1)
        compose(projects[0], "kill", "--signal", "SIGKILL", "api")
        compose(projects[0], "up", "--detach", "--no-build", "api")
        wait_healthy()
        recovered = json.loads(http(base + "/jobs/" + interrupted_job_id)[1])
        if recovered["state"] != "interrupted":
            raise ValueError("controller loss was silently resumed or reported successful")
        events = http(base + "/jobs/" + interrupted_job_id + "/events")[1]
        if b"interrupted" not in events:
            raise ValueError("interruption receipt missing from resumable event stream")
        receipt["checks"]["abrupt_running_job_recovery"] = {
            "job_id": interrupted_job_id,
            "state": recovered["state"],
            "event_stream_digest": blob_digest(events),
        }
        exercise("restarted")
        limits = json.loads(
            compose(
                projects[0],
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import json,pathlib; p=pathlib.Path('/sys/fs/cgroup'); "
                "print(json.dumps({name:(p/name).read_text().strip() for name in "
                "['memory.max','memory.peak','memory.events','pids.max','pids.current']}))",
                capture=True,
            )
        )
        if (
            limits["memory.max"] != "1073741824"
            or limits["pids.max"] != "128"
            or int(limits["memory.peak"]) >= 1073741824
            or "oom_kill 0" not in limits["memory.events"].splitlines()
        ):
            raise ValueError("API resource limits or OOM boundary failed")
        receipt["checks"]["bounded_API_cgroup"] = limits
        # Stop all evidence writers before taking the database/CAS consistency set.
        compose(projects[0], "stop", "ui", "api")
        backup = output / "backup"
        backup.mkdir(mode=0o700)
        dump = compose(
            projects[0],
            "exec",
            "-T",
            "db",
            "pg_dump",
            "--format=custom",
            "--username=postgres",
            "sentinel",
            capture=True,
        )
        dump_path = backup / "metadata.dump"
        dump_path.touch(mode=0o600)
        dump_path.write_bytes(dump)
        compose(projects[0], "cp", "api:/var/lib/sentinel/evidence", str(backup / "evidence"))
        if (backup / "evidence/sha256").exists():
            raise ValueError("production evidence backup contains plaintext CAS")
        if not list((backup / "evidence/ciphertext/sha256").glob("*/*")):
            raise ValueError("production encrypted CAS backup is empty")
        receipt["checks"]["stopped_writer_encrypted_backup"] = True
        receipt["backup_metadata_digest"] = blob_digest(dump)
        compose(projects[0], "down", "--volumes", "--remove-orphans")
        compose(
            projects[1],
            "up",
            "--detach",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "90",
        )
        compose(projects[1], "stop", "ui", "api")
        compose(
            projects[1],
            "exec",
            "-T",
            "db",
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--username=postgres",
            "--dbname=sentinel",
            data=dump,
        )
        compose(
            projects[1], "cp", str(backup / "evidence/.") + "/.", "api:/var/lib/sentinel/evidence"
        )
        # Docker cp may preserve host ownership; normalize only this new own volume.
        compose(
            projects[1],
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0:0",
            "init-evidence",
            "python",
            "-c",
            "import os,pathlib; p=pathlib.Path('/var/lib/sentinel/evidence');\n"
            "for q in [p,*p.rglob('*')]: os.chown(q,10001,10001)\n",
        )
        compose(projects[1], "start", "api", "ui")
        wait_healthy()
        exercise("restored")
        restored_job = json.loads(http(base + "/jobs/" + interrupted_job_id)[1])
        if restored_job["state"] != "interrupted":
            raise ValueError("backup restore changed the interrupted-job outcome")
        receipt["checks"]["interrupted_job_survives_backup_restore"] = True
        receipt["completed"] = True
    except Exception as error:
        receipt["failure_type"] = type(error).__name__
        raise
    finally:
        for project in projects:
            subprocess.run(
                [*compose_base, "--project-name", project, "logs", "--no-color"],
                stdout=log,
                stderr=log,
                timeout=30,
                check=False,
            )
            result = subprocess.run(
                [*compose_base, "--project-name", project, "down", "--volumes", "--remove-orphans"],
                stdout=log,
                stderr=log,
                timeout=60,
                check=False,
            )
            receipt.setdefault("cleanup", {})[project] = result.returncode == 0
        log.close()
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-proof", action="store_true")
    parser.add_argument("--scale-capsule", type=Path)
    args = parser.parse_args()
    validate(
        args.capsule.resolve(),
        args.output.resolve(),
        browser_proof=args.browser_proof,
        scale_capsule=args.scale_capsule,
    )
    print("LOCAL_DEPLOYMENT_AND_RECOVERY_VALIDATED " + str(args.output / "receipt.json"))
