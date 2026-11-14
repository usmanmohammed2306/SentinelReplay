"""Validate a retained capsule through a fresh local PostgreSQL/HTTP stack.

Only this invocation's uniquely named container and API process are removed.
Keys, credentials and service logs remain in the ignored local controller tree.
No image is pulled, no existing database is reused, and no cloud is contacted.
"""

import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from psycopg import connect, sql

from sentinel_replay.capsule import verify_capsule
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.signed_capsule import sign_capsule

POSTGRES_IMAGE = (
    "postgres:17.12-alpine@sha256:34261f594522cf41dfcb76aefd42b9d201098b0e6b23c9c68733f169e4218b6f"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((Path.cwd() / ".local-controller").resolve()):
        parser.error("output must be a new directory under .local-controller")
    verified = verify_capsule(args.capsule)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    agent = output / "declared-agent"
    agent.mkdir()
    private, public = create_keypair(output / "keys", agent)
    statement = sign_capsule(args.capsule, private, output / "anchors", agent)
    token, db_password, app_password = (secrets.token_urlsafe(32) for _ in range(3))
    env_file = output / "postgres.env"
    env_file.touch(mode=0o600)
    env_file.write_text(f"POSTGRES_PASSWORD={db_password}\nPOSTGRES_DB=sentinel\n")
    name = "sentinel-api-proof-" + uuid4().hex
    service: subprocess.Popen[bytes] | None = None
    receipt: dict[str, object] = {
        "schema_version": 1,
        "scope": "disposable_local_postgresql_http_signed_capsule",
        "postgres_image": POSTGRES_IMAGE,
        "run_id": verified.run_id,
        "journal_root": verified.root,
        "records": verified.records,
        "completed": False,
    }
    log = (output / "validation.log").open("xb")

    def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
        subprocess.run(command, env=env, stdout=log, stderr=log, timeout=60, check=True)

    try:
        run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--pull",
                "never",
                "--name",
                name,
                "--publish",
                "127.0.0.1::5432",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,nosuid,noexec,size=256m",
                "--env-file",
                str(env_file),
                POSTGRES_IMAGE,
            ]
        )
        published = subprocess.check_output(
            ["docker", "port", name, "5432/tcp"], text=True, timeout=10
        ).strip()
        if not published.startswith("127.0.0.1:"):
            raise RuntimeError("database port is not restricted to loopback")
        pg_port = int(published.rsplit(":", 1)[1])
        admin_url = f"postgresql://postgres:{db_password}@127.0.0.1:{pg_port}/sentinel"
        deadline = time.monotonic() + 30
        while True:
            try:
                with connect(admin_url, connect_timeout=1, autocommit=True) as database:
                    version = database.execute("SHOW server_version").fetchone()
                    if version is None or not version[0].startswith("17."):
                        raise RuntimeError("validation requires PostgreSQL 17")
                    receipt["postgres_version"] = version[0]
                    database.execute(
                        sql.SQL("CREATE ROLE sentinel_api LOGIN PASSWORD {}").format(
                            sql.Literal(app_password)
                        )
                    )
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("disposable PostgreSQL startup did not complete") from None
                time.sleep(0.25)
        migration_url = admin_url.replace("postgresql://", "postgresql+psycopg://", 1)
        env = {**os.environ, "SENTINEL_DATABASE_URL": migration_url}
        run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
        with connect(admin_url, autocommit=True) as database:
            database.execute("GRANT USAGE ON SCHEMA public TO sentinel_api")
            database.execute("GRANT SELECT, INSERT ON runs TO sentinel_api")
        test_env = {
            **env,
            "SENTINEL_TEST_DATABASE_URL": migration_url,
            "SENTINEL_TEST_DATABASE_DISPOSABLE": "1",
        }
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "postgres_integration",
                "--junitxml=" + str(output / "postgres-tests.xml"),
            ],
            env=test_env,
        )
        receipt["postgres_integration_passed"] = True
        app_url = f"postgresql+psycopg://sentinel_api:{app_password}@127.0.0.1:{pg_port}/sentinel"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            api_port = probe.getsockname()[1]
        env = {
            **os.environ,
            "SENTINEL_DATABASE_URL": app_url,
            "SENTINEL_EVIDENCE_ROOT": str(output / "evidence"),
            "SENTINEL_TRUSTED_PUBLIC_KEY": str(public),
            "SENTINEL_API_TOKEN": token,
            "SENTINEL_ALLOW_PLAINTEXT_PREVIEW": "1",
        }
        service = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sentinel_replay.api:app_factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        base_url = f"http://127.0.0.1:{api_port}"
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(base_url + "/healthz", timeout=1) as response:
                    if json.load(response) != {"status": "ok"}:
                        raise RuntimeError("unexpected health response")
                break
            except (OSError, URLError):
                if service.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("disposable API startup did not complete") from None
                time.sleep(0.1)
        run(
            [
                sys.executable,
                "scripts/smoke_local_api.py",
                "--capsule",
                str(args.capsule),
                "--attestation",
                str(statement),
                "--base-url",
                base_url,
            ],
            env=env,
        )
        receipt["real_http_signed_capsule_round_trip"] = True
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/octet-stream",
            "X-Sentinel-Attestation": base64.b64encode(statement.read_bytes()).decode(),
        }
        with urlopen(
            Request(
                base_url + "/v1/runs/import",
                data=args.capsule.read_bytes(),
                method="POST",
                headers=headers,
            ),
            timeout=10,
        ) as response:
            receipt["duplicate_import_status"] = response.status
            if response.status != 200:
                raise RuntimeError("duplicate capsule import was not idempotent")
        for label, request, expected in (
            ("unauthenticated_list", Request(base_url + "/v1/runs"), 401),
            (
                "changed_archive",
                Request(
                    base_url + "/v1/runs/import",
                    data=args.capsule.read_bytes() + b"modified",
                    method="POST",
                    headers=headers,
                ),
                422,
            ),
        ):
            try:
                with urlopen(request, timeout=10):
                    raise RuntimeError("negative control unexpectedly succeeded")
            except HTTPError as error:
                receipt[label + "_status"] = error.code
                if error.code != expected:
                    raise RuntimeError("negative control returned unexpected status") from None
        with connect(app_url.replace("postgresql+psycopg://", "postgresql://", 1)) as database:
            row = database.execute(
                "SELECT current_user, has_table_privilege(current_user, 'runs', 'SELECT'), "
                "has_table_privilege(current_user, 'runs', 'INSERT'), "
                "has_table_privilege(current_user, 'runs', 'UPDATE'), "
                "has_table_privilege(current_user, 'runs', 'DELETE')"
            ).fetchone()
            if row != ("sentinel_api", True, True, False, False):
                raise RuntimeError("API role permissions differ from the declared contract")
            receipt["api_role"] = dict(
                zip(("current_user", "select", "insert", "update", "delete"), row, strict=True)
            )
        receipt["completed"] = True
    except Exception as error:
        receipt["failure_type"] = type(error).__name__
        raise
    finally:
        if service is not None and service.poll() is None:
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
        cleanup = subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            stdout=log,
            stderr=log,
            timeout=15,
            check=False,
        )
        receipt["container_removed"] = cleanup.returncode == 0
        log.close()
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("LOCAL_BRANCH_API_VALIDATED " + str(output / "receipt.json"))


if __name__ == "__main__":
    main()
