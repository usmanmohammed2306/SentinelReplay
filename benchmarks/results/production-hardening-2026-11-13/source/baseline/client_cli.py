"""Local investigation commands and explicit bearer-authenticated API inspection."""

import base64
import json
import os
import secrets
from pathlib import Path
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import typer

from sentinel_replay.capsule import read_capsule_bytes, verify_capsule
from sentinel_replay.capsule_privacy import MAX_SEALED_BYTES, seal, unseal, write_private
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.experiment_capsule import comparison_view
from sentinel_replay.futures import simulate_future
from sentinel_replay.git_snapshot import GitCheckpoint, capture_git, restore_git
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.local_anchor import _regular_bytes
from sentinel_replay.policy_language import Policy
from sentinel_replay.sqlite_snapshot import SQLiteCheckpoint, capture_sqlite, restore_sqlite
from sentinel_replay.telemetry import MAX_TELEMETRY_BYTES, merge_telemetry
from sentinel_replay.trust_registry import TrustedKey, TrustRegistry


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def api_read(path: str, base_url: str, body: dict[str, Any] | None = None) -> Any:
    parts = urlsplit(base_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise typer.BadParameter("API URL must be an explicit HTTP(S) origin without credentials")
    if parts.scheme == "http" and parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("non-loopback API access requires HTTPS")
    token = os.environ.get("SENTINEL_API_TOKEN", "")
    if len(token) < 32:
        raise typer.BadParameter("set SENTINEL_API_TOKEN; never pass it as a command argument")
    try:
        with build_opener(NoRedirect()).open(
            Request(
                base_url.rstrip("/") + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            ),
            timeout=30,
        ) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("API metadata exceeds byte budget")
            return json.loads(data)
    except HTTPError as error:
        raise typer.BadParameter(f"API request rejected ({error.code})") from None
    except (URLError, ValueError):
        raise typer.BadParameter("API unavailable or invalid metadata") from None


def register_client_commands(app: typer.Typer) -> None:
    privacy = typer.Typer(help="Private portable AES-GCM capsules; separate from signatures.")
    app.add_typer(privacy, name="privacy")
    snapshots = typer.Typer(help="Declared cooperative Git and SQLite snapshot adapters.")
    app.add_typer(snapshots, name="snapshot")
    trust = typer.Typer(help="Create a new operator trust-registry version; never overwrite one.")
    app.add_typer(trust, name="trust")
    retention = typer.Typer(
        help="Stopped-controller collection; dry-run unless --apply is supplied."
    )
    app.add_typer(retention, name="retention")

    @retention.command("collect")
    def retention_collect(
        evidence_root: Path, key: Path | None = None, apply: bool = False
    ) -> None:
        from sqlalchemy import create_engine

        from sentinel_replay.retention import collect_evidence

        database_url = os.environ.get("SENTINEL_DATABASE_URL")
        if not database_url:
            raise typer.BadParameter("set SENTINEL_DATABASE_URL in the operator environment")
        engine = create_engine(database_url)
        try:
            result = collect_evidence(engine, evidence_root, key, apply=apply)
        finally:
            engine.dispose()
        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @app.command("retire")
    def retire(
        run_id: str, reason: str = "operator_deletion", api_url: str = "http://127.0.0.1:8000"
    ) -> None:
        if reason not in {"operator_deletion", "retention_expired"}:
            raise typer.BadParameter("reason must be operator_deletion or retention_expired")
        typer.echo(
            json.dumps(
                api_read(
                    "/v1/runs/" + quote(run_id, safe="") + "/retire", api_url, {"reason": reason}
                ),
                indent=2,
            )
        )

    @trust.command("init")
    def trust_init(public_key: Path, destination: Path) -> None:
        from sentinel_replay.evidence_store import blob_digest

        raw = _regular_bytes(public_key, 32)
        key = TrustedKey(key_id=blob_digest(raw), public_key_b64=base64.b64encode(raw).decode())
        value = TrustRegistry(epoch=1, keys=(key,))
        write_private(destination, (value.model_dump_json(indent=2) + "\n").encode())
        typer.echo("OPERATOR_TRUST_REGISTRY_CREATED epoch=1")

    @trust.command("rotate")
    def trust_rotate(current: Path, new_public_key: Path, destination: Path) -> None:
        from sentinel_replay.evidence_store import blob_digest

        registry = TrustRegistry.model_validate_json(_regular_bytes(current, 32768))
        raw = _regular_bytes(new_public_key, 32)
        key = TrustedKey(key_id=blob_digest(raw), public_key_b64=base64.b64encode(raw).decode())
        if any(item.key_id == key.key_id for item in registry.keys):
            raise typer.BadParameter("rotation requires a new public key")
        prior = tuple(
            item.model_copy(update={"state": "retired"}) if item.state == "active" else item
            for item in registry.keys
        )
        value = TrustRegistry(epoch=registry.epoch + 1, keys=(*prior, key))
        write_private(destination, (value.model_dump_json(indent=2) + "\n").encode())
        typer.echo(f"OPERATOR_TRUST_ROTATION_PREPARED epoch={value.epoch}")

    @trust.command("revoke")
    def trust_revoke(current: Path, key_id: str, destination: Path) -> None:
        registry = TrustRegistry.model_validate_json(_regular_bytes(current, 32768))
        if not any(item.key_id == key_id for item in registry.keys):
            raise typer.BadParameter("key is absent from registry")
        keys = tuple(
            item.model_copy(update={"state": "revoked"}) if item.key_id == key_id else item
            for item in registry.keys
        )
        value = TrustRegistry(epoch=registry.epoch + 1, keys=keys)
        write_private(destination, (value.model_dump_json(indent=2) + "\n").encode())
        typer.echo(f"OPERATOR_REVOCATION_PREPARED epoch={value.epoch}")

    @privacy.command("keygen")
    def keygen(destination: Path) -> None:
        write_private(destination, secrets.token_bytes(32))
        typer.echo("PRIVATE_AES_KEY_CREATED")

    @privacy.command("seal")
    def encrypt(capsule: Path, key: Path, destination: Path) -> None:
        write_private(destination, seal(read_capsule_bytes(capsule), key))
        typer.echo("CAPSULE_ENCRYPTED_AES256_GCM signature_verification=separate")

    @privacy.command("open")
    def decrypt(encrypted: Path, key: Path, destination: Path) -> None:
        data = _regular_bytes(encrypted, MAX_SEALED_BYTES)
        write_private(destination, unseal(data, key))
        typer.echo("CAPSULE_DECRYPTED_INTEGRITY_VERIFIED authenticity=not_checked")

    @snapshots.command("capture")
    def capture(adapter: str, source: Path, store_root: Path, manifest: Path) -> None:
        store = FileEvidenceStore(store_root, max_bytes=32 * 1024 * 1024)
        result: GitCheckpoint | SQLiteCheckpoint
        if adapter == "git":
            result = capture_git(source, store)
        elif adapter == "sqlite":
            result = capture_sqlite(source, store)
        else:
            raise typer.BadParameter("adapter must be git or sqlite")
        write_private(manifest, (result.model_dump_json(indent=2) + "\n").encode())
        typer.echo(f"CHECKPOINT_CAPTURED adapter={result.adapter} coverage={result.coverage}")

    @snapshots.command("restore")
    def restore(adapter: str, manifest: Path, store_root: Path, destination: Path) -> None:
        store = FileEvidenceStore(store_root, max_bytes=32 * 1024 * 1024)
        if adapter == "git":
            restored = restore_git(
                GitCheckpoint.model_validate_json(_regular_bytes(manifest, 1024 * 1024)),
                destination,
                store,
            )
        elif adapter == "sqlite":
            restored = restore_sqlite(
                SQLiteCheckpoint.model_validate_json(_regular_bytes(manifest, 65536)),
                destination,
                store,
            )
        else:
            raise typer.BadParameter("adapter must be git or sqlite")
        typer.echo(f"CHECKPOINT_RESTORED adapter={adapter} verified={restored}")

    @app.command("verify")
    def verify(capsule: Path) -> None:
        result = verify_capsule(capsule)
        typer.echo(
            f"CAPSULE_INTEGRITY_VERIFIED run={result.run_id} records={result.records} "
            "authenticity=not_checked"
        )

    @app.command("runs")
    def runs(api_url: str = "http://127.0.0.1:8000", after: str | None = None) -> None:
        suffix = "?limit=100" + ("&after=" + quote(after, safe="") if after else "")
        typer.echo(json.dumps(api_read("/v1/runs" + suffix, api_url), indent=2))

    @app.command("inspect")
    def inspect(run: str, api_url: str = "http://127.0.0.1:8000") -> None:
        path = Path(run)
        if path.is_file():
            value = CapsuleInvestigation(read_capsule_bytes(path)).summary()
        else:
            value = api_read("/v1/runs/" + quote(run, safe="") + "/investigation", api_url)
        typer.echo(json.dumps(value, indent=2))

    @app.command("incident")
    def incident(capsule: Path, step: Annotated[int, typer.Option(min=0)] = 0) -> None:
        source = CapsuleInvestigation(read_capsule_bytes(capsule))
        typer.echo(
            json.dumps(
                {"findings": source.incidents(), "provenance": source.provenance(root_step=step)},
                indent=2,
            )
        )

    @app.command("futures")
    def futures(capsule: Path) -> None:
        typer.echo(
            json.dumps(comparison_view(CapsuleInvestigation(read_capsule_bytes(capsule))), indent=2)
        )

    @app.command("fork")
    def fork(
        capsule: Path,
        policy: Path,
        destination: Path,
        from_step: Annotated[int, typer.Option(min=0)] = 0,
    ) -> None:
        source = CapsuleInvestigation(read_capsule_bytes(capsule))
        result = simulate_future(
            source,
            Policy.model_validate_json(_regular_bytes(policy, 65536)),
            destination,
            fork_step=from_step,
        )
        typer.echo(
            f"{result['mode']} status={result['status']} "
            f"changed_paths={len(result['world_diff'])} "
            f"report={destination / 'future-report.json'}"
        )

    @app.command("telemetry-merge")
    def telemetry_merge(journal: Path, otlp: Path, expected_root: str, destination: Path) -> None:
        result = merge_telemetry(
            journal, _regular_bytes(otlp, MAX_TELEMETRY_BYTES), expected_root=expected_root
        )
        write_private(destination, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
        typer.echo(
            f"TELEMETRY_ENRICHED matched={len(result['matched_spans'])} "
            f"unmatched={result['unmatched_spans']} journal_authoritative=True"
        )
