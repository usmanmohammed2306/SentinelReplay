"""Authenticated run-ingest API preview backed by SQL metadata and local CAS.

This is not the complete V1 API. TLS, scoped authorization, external anchoring,
retention, incident queries, and live streaming remain release requirements.
"""

import base64
import binascii
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from sentinel_replay.capsule import MAX_ARCHIVE_BYTES, verify_capsule_bytes
from sentinel_replay.database import RunConflict, RunRepository, StoredRun
from sentinel_replay.evidence_store import BlobCorruption, BlobRef, FileEvidenceStore
from sentinel_replay.local_anchor import load_local_public_key
from sentinel_replay.signed_capsule import (
    MAX_CAPSULE_ATTESTATION_BYTES,
    SignedCapsuleError,
    verify_signed_capsule_material,
)


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    evidence_root: Path
    trusted_public_key: Path
    api_token: str

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("database URL is required")
        if len(self.api_token) < 32:
            raise ValueError("API token must be at least 32 characters")

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
        )


def create_app(settings: ApiSettings, *, engine: Engine | None = None) -> FastAPI:
    """Create an API only after the caller supplies an explicit trusted key and token."""
    public, key_id = load_local_public_key(settings.trusted_public_key)
    public_raw = public.public_bytes_raw()
    database = engine or create_engine(settings.database_url, pool_pre_ping=True)
    repository = RunRepository(database)
    store = FileEvidenceStore(settings.evidence_root, max_bytes=MAX_ARCHIVE_BYTES)
    app = FastAPI(
        title="Sentinel Replay API Preview",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authentication required")
        supplied = authorization.removeprefix("Bearer ")
        if not secrets.compare_digest(supplied, settings.api_token):
            raise HTTPException(status_code=401, detail="authentication required")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        try:
            healthy = repository.health()
        except SQLAlchemyError:
            healthy = False
        if not healthy:
            raise HTTPException(status_code=503, detail="metadata database unavailable")
        return {"status": "ok"}

    @app.get("/v1/runs", dependencies=[Depends(authorize)])
    def list_runs(
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: str | None = None,
    ) -> dict[str, object]:
        records = repository.list(limit=limit, after=after)
        return {"runs": [asdict(record) for record in records]}

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(authorize)])
    def get_run(run_id: str) -> dict[str, object]:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return asdict(record)

    @app.get("/v1/runs/{run_id}/capsule", dependencies=[Depends(authorize)])
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

    @app.post("/v1/runs/import", dependencies=[Depends(authorize)])
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

    return app


def app_factory() -> FastAPI:
    """Uvicorn factory: require PostgreSQL and explicit non-default secrets."""
    settings = ApiSettings.from_env()
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("self-hosted API requires a PostgreSQL psycopg URL")
    return create_app(settings)
