"""Authenticated run-ingest API preview backed by SQL metadata and local CAS.

This is not the complete V1 API. TLS, scoped authorization, external anchoring,
retention, incident queries, and live streaming remain release requirements.
"""

import asyncio
import base64
import binascii
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, StreamingResponse

from sentinel_replay.access import AccessGrant, AccessPolicy, Scope
from sentinel_replay.capsule import MAX_ARCHIVE_BYTES, verify_capsule_bytes
from sentinel_replay.database import RunConflict, RunRepository, StoredRun
from sentinel_replay.encrypted_store import EncryptedEvidenceStore
from sentinel_replay.evidence_store import BlobCorruption, BlobRef, FileEvidenceStore
from sentinel_replay.experiment_capsule import comparison_view
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import load_local_public_key
from sentinel_replay.policy_language import Policy
from sentinel_replay.query_index import QueryIndex
from sentinel_replay.signed_capsule import (
    MAX_CAPSULE_ATTESTATION_BYTES,
    SignedCapsuleError,
    verify_signed_capsule_material,
)


class ForkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Policy
    fork_step: int = Field(default=0, ge=0, le=50000)


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    evidence_root: Path
    trusted_public_key: Path
    api_token: str
    access_grants: tuple[AccessGrant, ...] = ()
    encryption_key: Path | None = None
    max_inflight: int = 2
    opa_executable: Path | None = None

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("database URL is required")
        if len(self.api_token) < 32:
            raise ValueError("API token must be at least 32 characters")
        if not 1 <= self.max_inflight <= 8:
            raise ValueError("API in-flight budget must be within1..8")

    @classmethod
    def from_env(cls) -> "ApiSettings":
        required = (
            "SENTINEL_DATABASE_URL",
            "SENTINEL_EVIDENCE_ROOT",
            "SENTINEL_TRUSTED_PUBLIC_KEY",
            "SENTINEL_API_TOKEN",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError("missing API settings: " + ", ".join(missing))
        return cls(
            database_url=os.environ["SENTINEL_DATABASE_URL"],
            evidence_root=Path(os.environ["SENTINEL_EVIDENCE_ROOT"]),
            trusted_public_key=Path(os.environ["SENTINEL_TRUSTED_PUBLIC_KEY"]),
            api_token=os.environ["SENTINEL_API_TOKEN"],
            access_grants=tuple(
                AccessGrant.model_validate(value)
                for value in json.loads(os.environ.get("SENTINEL_ACCESS_GRANTS", "[]"))
            ),
            encryption_key=Path(os.environ["SENTINEL_ENCRYPTION_KEY"])
            if os.environ.get("SENTINEL_ENCRYPTION_KEY")
            else None,
            max_inflight=int(os.environ.get("SENTINEL_MAX_INFLIGHT", "2")),
            opa_executable=Path(os.environ["SENTINEL_OPA_EXECUTABLE"])
            if os.environ.get("SENTINEL_OPA_EXECUTABLE")
            else None,
        )


def create_app(settings: ApiSettings, *, engine: Engine | None = None) -> FastAPI:
    """Create an API only after the caller supplies an explicit trusted key and token."""
    public, key_id = load_local_public_key(settings.trusted_public_key)
    public_raw = public.public_bytes_raw()
    database = engine or create_engine(settings.database_url, pool_pre_ping=True)
    repository = RunRepository(database)
    store = (
        EncryptedEvidenceStore(
            settings.evidence_root, settings.encryption_key, max_bytes=MAX_ARCHIVE_BYTES
        )
        if settings.encryption_key
        else FileEvidenceStore(settings.evidence_root, max_bytes=MAX_ARCHIVE_BYTES)
    )
    access = AccessPolicy(settings.api_token, settings.access_grants)
    audit = Journal(settings.evidence_root / "access-audit.jsonl")
    indexes = QueryIndex(database, store)
    capacity = asyncio.Semaphore(settings.max_inflight)
    app = FastAPI(
        title="Sentinel Replay Investigation API",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> AccessGrant:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authentication required")
        supplied = authorization.removeprefix("Bearer ")
        if len(supplied) > 4096:
            raise HTTPException(status_code=401, detail="authentication required")
        grant = access.authenticate(supplied)
        if grant is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return grant

    def require(scope: Scope) -> Any:
        def check(
            request: Request, grant: Annotated[AccessGrant, Depends(authorize)]
        ) -> AccessGrant:
            run_id = request.path_params.get("run_id")
            allowed = access.permits(grant, scope, run_id)
            audit.append(
                {
                    "kind": "access",
                    "subject": grant.subject,
                    "scope": scope,
                    "run_id": run_id,
                    "allowed": allowed,
                }
            )
            if not allowed:
                raise HTTPException(status_code=403, detail="capability or run access denied")
            return grant

        return check

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response: Response
        if request.url.path.startswith("/v1/"):
            if capacity.locked():
                response = JSONResponse(
                    {"detail": "evidence work budget exhausted"},
                    status_code=429,
                    headers={"Retry-After": "1"},
                )
            else:
                async with capacity:
                    response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @lru_cache(maxsize=1)
    def cached_investigation(data: bytes) -> CapsuleInvestigation:
        return CapsuleInvestigation(data)

    def investigation(run_id: str, branch: int | None = None) -> CapsuleInvestigation:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            result = cached_investigation(
                store.get(BlobRef(record.capsule_digest, record.capsule_size))
            )
            if (
                result.verified.run_id != run_id
                or result.verified.root != record.journal_root
                or result.verified.records != record.records
            ):
                raise ValueError("stored run binding differs")
            if branch is None:
                return result
            view = comparison_view(result)
            if not 0 <= branch < len(view["branches"]):
                raise HTTPException(status_code=404, detail="branch not found")
            return CapsuleInvestigation(result.artifacts[f"branch-{branch:03d}.sentinel"])
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="stored evidence unavailable") from error

    def index_for(run_id: str, branch: int | None = None) -> dict[str, Any]:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            view_id = "root" if branch is None else f"branch-{branch:03d}"
            existing = indexes.find(record, view_id)
            return (
                existing
                if existing is not None
                else indexes.build(record, investigation(run_id, branch), view_id)
            )
        except (SQLAlchemyError, OSError, ValueError) as error:
            raise HTTPException(
                status_code=503, detail="derived investigation unavailable"
            ) from error

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        try:
            healthy = repository.health()
        except SQLAlchemyError:
            healthy = False
        if not healthy:
            raise HTTPException(status_code=503, detail="metadata database unavailable")
        return {"status": "ok"}

    @app.get("/v1/runs", dependencies=[Depends(require("metadata"))])
    def list_runs(
        grant: Annotated[AccessGrant, Depends(authorize)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: str | None = None,
    ) -> dict[str, object]:
        allowed = None if "admin" in grant.scopes or "*" in grant.runs else grant.runs
        records = repository.list(limit=limit, after=after, allowed_runs=allowed)
        return {
            "runs": [
                asdict(record)
                for record in records
                if access.permits(grant, "metadata", record.run_id)
            ],
            "next_cursor": records[-1].run_id if len(records) == limit else None,
        }

    @app.post("/v1/runs/{run_id}/fork", dependencies=[Depends(require("replay"))])
    def fork_run(
        run_id: str,
        body: ForkRequest,
        branch: Annotated[int | None, Query(ge=0, le=63)] = None,
    ) -> dict[str, Any]:
        from sentinel_replay.futures import simulate_future
        from sentinel_replay.policy import PolicyUnavailable

        source = investigation(run_id, branch)
        parent = repository.get(run_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            with tempfile.TemporaryDirectory(prefix="sentinel-future-") as directory:
                target = Path(directory) / "future"
                report = simulate_future(
                    source,
                    body.policy,
                    target,
                    fork_step=body.fork_step,
                    opa_executable=settings.opa_executable,
                )
                ref = store.put((target / "future.sentinel").read_bytes())
                envelope = {
                    "schema_version": 1,
                    "kind": "finite_future_receipt",
                    "parent_run_id": run_id,
                    "parent_capsule_digest": parent.capsule_digest,
                    "original_journal_root": source.verified.root,
                    "capsule_digest": ref.digest,
                    "capsule_size": ref.size,
                    "report": report,
                }
                raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
                receipt = store.put(raw)
        except PolicyUnavailable as error:
            raise HTTPException(status_code=503, detail="policy evaluator unavailable") from error
        except (ValueError, OSError, RuntimeError) as error:
            raise HTTPException(
                status_code=409, detail="unsupported fork or evidence mismatch"
            ) from error
        audit.append({"kind": "future_created", "run_id": run_id, "receipt": receipt.digest})
        return {"future_id": receipt.digest, "receipt_size": receipt.size, **report}

    def future_receipt(run_id: str, future_id: str, size: int) -> dict[str, Any]:
        from sentinel_replay.canonical import load_json_unique

        parent = repository.get(run_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            value = load_json_unique(store.get(BlobRef(future_id, size)).decode())
            if (
                value["kind"] != "finite_future_receipt"
                or value["schema_version"] != 1
                or value["parent_run_id"] != run_id
                or value["parent_capsule_digest"] != parent.capsule_digest
            ):
                raise ValueError("future parent binding differs")
            return dict(value)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(status_code=404, detail="future receipt unavailable") from error

    @app.get("/v1/runs/{run_id}/futures/{future_id}", dependencies=[Depends(require("evidence"))])
    def get_future(
        run_id: str, future_id: str, size: Annotated[int, Query(ge=1, le=1024 * 1024)]
    ) -> dict[str, Any]:
        return dict(future_receipt(run_id, future_id, size)["report"])

    @app.get(
        "/v1/runs/{run_id}/futures/{future_id}/capsule", dependencies=[Depends(require("export"))]
    )
    def export_future(
        run_id: str, future_id: str, size: Annotated[int, Query(ge=1, le=1024 * 1024)]
    ) -> Response:
        value = future_receipt(run_id, future_id, size)
        data = store.get(BlobRef(value["capsule_digest"], value["capsule_size"]))
        verify_capsule_bytes(data)
        return Response(
            data,
            media_type="application/octet-stream",
            headers={"X-Sentinel-Authenticity": "unsigned-simulated-future"},
        )

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(require("metadata"))])
    def get_run(run_id: str) -> dict[str, object]:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return asdict(record)

    @app.get("/v1/runs/{run_id}/capsule", dependencies=[Depends(require("export"))])
    def get_capsule(run_id: str) -> Response:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            data = store.get(BlobRef(record.capsule_digest, record.capsule_size))
            verified = verify_capsule_bytes(data)
            if (
                verified.run_id != record.run_id
                or verified.root != record.journal_root
                or verified.records != record.records
            ):
                raise BlobCorruption("stored capsule differs from indexed run")
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="stored evidence unavailable") from error
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/v1/runs/import", dependencies=[Depends(require("import"))])
    async def import_run(
        request: Request,
        response: Response,
        attestation: Annotated[str, Header(alias="X-Sentinel-Attestation")],
    ) -> dict[str, object]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
        if content_type != "application/octet-stream":
            raise HTTPException(status_code=415, detail="application/octet-stream required")
        if len(attestation) > ((MAX_CAPSULE_ATTESTATION_BYTES + 2) // 3) * 4:
            raise HTTPException(status_code=413, detail="attestation exceeds byte limit")
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                length = int(declared_length)
                if length < 0:
                    raise HTTPException(status_code=400, detail="invalid content length")
                if length > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="capsule exceeds byte limit")
            except ValueError as error:
                raise HTTPException(status_code=400, detail="invalid content length") from error
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_ARCHIVE_BYTES:
                raise HTTPException(status_code=413, detail="capsule exceeds byte limit")
        try:
            raw_statement = base64.b64decode(attestation, validate=True)
        except binascii.Error as error:
            raise HTTPException(status_code=422, detail="invalid attestation encoding") from error
        data = bytes(body)

        def validate() -> tuple[str, str, int]:
            if not verify_signed_capsule_material(data, raw_statement, public_raw):
                raise SignedCapsuleError("invalid signature")
            verified = verify_capsule_bytes(data)
            return verified.run_id, verified.root, verified.records

        try:
            verified_run_id, verified_root, verified_records = await run_in_threadpool(validate)
        except (SignedCapsuleError, ValueError):
            raise HTTPException(status_code=422, detail="invalid signed capsule") from None

        def persist() -> tuple[StoredRun, bool]:
            blob = store.put(data)
            record = StoredRun(
                run_id=verified_run_id,
                journal_root=verified_root,
                records=verified_records,
                capsule_digest=blob.digest,
                capsule_size=blob.size,
                signer_key_id=key_id,
            )
            return repository.insert_or_get(record)

        try:
            record, created = await run_in_threadpool(persist)
        except RunConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (OSError, SQLAlchemyError, ValueError) as error:
            raise HTTPException(status_code=503, detail="evidence store unavailable") from error
        response.status_code = 201 if created else 200
        return asdict(record)

    @app.get("/v1/runs/{run_id}/investigation", dependencies=[Depends(require("metadata"))])
    def get_investigation(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        return dict(index_for(run_id, branch)["summary"])

    @app.get("/v1/runs/{run_id}/comparison", dependencies=[Depends(require("evidence"))])
    def get_comparison(run_id: str) -> dict[str, Any]:
        try:
            return comparison_view(investigation(run_id))
        except (ValueError, KeyError) as error:
            raise HTTPException(
                status_code=409, detail="unsupported or inconsistent comparison"
            ) from error

    @app.get("/v1/runs/{run_id}/timeline", dependencies=[Depends(require("evidence"))])
    def get_timeline(
        run_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        root: str | None = None,
        branch: Annotated[int | None, Query(ge=0, le=63)] = None,
    ) -> dict[str, Any]:
        index = index_for(run_id, branch)
        if offset > index["records"] or (root is not None and root != index["journal_root"]):
            raise HTTPException(status_code=409, detail="timeline cursor or root mismatch")
        try:
            return indexes.timeline(index, offset=offset, limit=limit, expected_root=root)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="derived event page unavailable") from error

    @app.get("/v1/runs/{run_id}/phases", dependencies=[Depends(require("evidence"))])
    def get_phases(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        phases = index_for(run_id, branch)["phases"]
        if phases is None:
            raise HTTPException(status_code=409, detail="unsupported boundary metadata")
        return dict(phases)

    @app.get("/v1/runs/{run_id}/incidents", dependencies=[Depends(require("evidence"))])
    def get_incidents(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        return dict(index_for(run_id, branch)["incidents"])

    @app.get("/v1/runs/{run_id}/provenance", dependencies=[Depends(require("evidence"))])
    def get_provenance(
        run_id: str,
        root_step: Annotated[int, Query(ge=0)] = 0,
        depth: Annotated[int, Query(ge=1, le=5)] = 2,
        branch: Annotated[int | None, Query(ge=0, le=63)] = None,
    ) -> dict[str, Any]:
        try:
            return indexes.provenance(index_for(run_id, branch), root_step=root_step, depth=depth)
        except ValueError as error:
            raise HTTPException(
                status_code=409, detail="unsupported graph or neighborhood budget"
            ) from error

    @app.get("/v1/runs/{run_id}/events", dependencies=[Depends(require("evidence"))])
    def get_events(
        run_id: str,
        after: Annotated[int, Query(ge=-1)] = -1,
        limit: Annotated[int, Query(ge=1, le=500)] = 500,
        last_event_id: Annotated[int | None, Header()] = None,
        branch: Annotated[int | None, Query(ge=0, le=63)] = None,
    ) -> StreamingResponse:
        index = index_for(run_id, branch)
        cursor = last_event_id if last_event_id is not None else after
        if not -1 <= cursor < max(1, index["records"]):
            raise HTTPException(status_code=409, detail="stream cursor outside stored run")
        try:
            events = indexes.timeline(index, offset=min(cursor + 1, index["records"]), limit=limit)[
                "events"
            ]
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="derived event page unavailable") from error
        messages = tuple(
            f"id: {event['step']}\nevent: boundary\ndata: {json.dumps(event)}\n\n"
            for event in events
        )
        return StreamingResponse(
            iter(messages),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    @app.post("/v1/runs/{run_id}/replay", dependencies=[Depends(require("replay"))])
    def replay_run(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        try:
            return investigation(run_id, branch).replay()
        except (ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=409, detail="replay unsupported or evidence mismatch"
            ) from error

    @app.get("/v1/runs/{run_id}/verification", dependencies=[Depends(require("metadata"))])
    def verify_run(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        result = investigation(run_id, branch)
        return {
            "run_id": run_id,
            "branch_index": branch,
            "journal_root": result.verified.root,
            "records": result.verified.records,
            "integrity": "verified_capsule_bytes",
            "signer": "verified_at_ingest_against_configured_key",
            "freshness": "not_established",
        }

    @app.get("/v1/runs/{run_id}/telemetry", dependencies=[Depends(require("evidence"))])
    def get_telemetry(
        run_id: str, branch: Annotated[int | None, Query(ge=0, le=63)] = None
    ) -> dict[str, Any]:
        import tempfile

        from sentinel_replay.pack_capsule import capsule_telemetry
        from sentinel_replay.telemetry import merge_telemetry

        source = investigation(run_id, branch)
        try:
            with tempfile.TemporaryDirectory(prefix="sentinel-telemetry-") as directory:
                path = Path(directory) / "journal.jsonl"
                path.write_bytes(source.journal)
                report = merge_telemetry(
                    path, capsule_telemetry(source.artifacts), expected_root=source.verified.root
                )
        except (ValueError, OSError) as error:
            raise HTTPException(
                status_code=409, detail="unsupported or mismatched telemetry"
            ) from error
        return {
            "journal_root": report["journal_root"],
            "matched_spans": len(report["matched_spans"]),
            "unmatched_spans": report["unmatched_spans"],
            "structural_edges": len(report["structural_edges"]),
            "limitation": report["limitation"],
        }

    from sentinel_replay.request_budget import RequestBodyBudget

    app.add_middleware(RequestBodyBudget)
    return app


def app_factory() -> FastAPI:
    """Uvicorn factory: require PostgreSQL and explicit non-default secrets."""
    settings = ApiSettings.from_env()
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("self-hosted API requires a PostgreSQL psycopg URL")
    return create_app(settings)
