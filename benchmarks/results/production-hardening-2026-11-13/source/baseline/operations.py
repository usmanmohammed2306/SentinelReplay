"""Single-controller bounded process jobs with immutable SQL status events.

Only four closed operations are dispatched. JSON cannot supply Python, shell,
import names or live endpoints. Worker results are encrypted CAS references when
the API evidence store is encrypted. Controller loss is interrupted, never success.
"""

import fcntl
import json
import multiprocessing
import os
import queue
import signal
import tempfile
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.canonical import load_json_unique
from sentinel_replay.capsule import MAX_ARCHIVE_BYTES
from sentinel_replay.checkpoint_set import restore_checkpoint_set
from sentinel_replay.database import RunRepository, StoredRun, operation_events, operation_jobs
from sentinel_replay.encrypted_store import EncryptedEvidenceStore
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import materialize_pack
from sentinel_replay.policy_language import Policy
from sentinel_replay.policy_search import search_policies
from sentinel_replay.query_index import IndexStore

TERMINAL = {"completed", "failed", "interrupted"}


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["replay", "fork", "bisect", "policy_search"]
    policy: Policy | None = None
    fork_step: int = Field(default=0, ge=0, le=50000)
    predicate: FilePredicate | None = None
    measure_linear: bool = False
    max_candidates: int = Field(default=128, ge=1, le=1000)
    time_budget_seconds: int = Field(default=600, ge=1, le=600)

    @model_validator(mode="after")
    def required(self) -> "OperationRequest":
        if self.kind == "fork" and self.policy is None:
            raise ValueError("fork requires a finite policy")
        if self.kind == "bisect" and self.predicate is None:
            raise ValueError("bisection requires a typed file predicate")
        return self


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _store(root: Path, key: Path | None) -> IndexStore:
    return (
        EncryptedEvidenceStore(root, key, max_bytes=MAX_ARCHIVE_BYTES)
        if key
        else FileEvidenceStore(root, max_bytes=MAX_ARCHIVE_BYTES)
    )


def _worker(
    channel: Connection,
    root: Path,
    key: Path | None,
    request_ref: BlobRef,
    opa: Path | None,
    job_id: str,
    scratch: Path,
) -> None:
    # One private process group enables the parent to terminate this job's OPA
    # child too, without signaling any other controller or container.
    os.setsid()
    signal.alarm(605)
    try:
        store = _store(root, key)
        envelope = load_json_unique(store.get(request_ref).decode())
        operation = OperationRequest.model_validate(envelope["request"])
        run = StoredRun(**envelope["run"])
        source = CapsuleInvestigation(store.get(BlobRef(run.capsule_digest, run.capsule_size)))
        if source.verified.run_id != run.run_id or source.verified.root != run.journal_root:
            raise ValueError("job source binding differs")
        if envelope["branch_artifact"] is not None:
            source = CapsuleInvestigation(source.artifacts[envelope["branch_artifact"]])
        channel.send({"stage": "source_verified", "records": source.verified.records})
        with tempfile.TemporaryDirectory(prefix="worker-", dir=scratch) as directory:
            target = Path(directory)
            if operation.kind == "replay":
                result = source.replay()
            elif operation.kind == "fork":
                from sentinel_replay.futures import simulate_future

                if operation.policy is None:
                    raise ValueError("missing finite policy")
                future = target / "future"
                result = simulate_future(
                    source,
                    operation.policy,
                    future,
                    fork_step=operation.fork_step,
                    opa_executable=opa,
                )
                ref = store.put((future / "future.sentinel").read_bytes())
                result["capsule"] = {
                    "digest": ref.digest,
                    "size": ref.size,
                    "authenticity": "unsigned_simulated_future",
                }
            elif operation.kind == "bisect":
                if operation.predicate is None:
                    raise ValueError("missing predicate")
                pack = materialize_pack(source.artifacts, source.journal, target)
                result = localize_pack(
                    pack,
                    target / "localization",
                    operation.predicate,
                    measure_linear=operation.measure_linear,
                    extra_restore=lambda destination, expected: restore_checkpoint_set(
                        source.artifacts, destination, expected
                    ),
                )
            else:
                # This search is explicitly the frozen twelve-case corpus, not
                # an inferred incident predicate for arbitrary imported evidence.
                result = search_policies(
                    root / "synthetic-policy-jobs" / job_id,
                    max_candidates=operation.max_candidates,
                    time_budget_seconds=operation.time_budget_seconds,
                    opa_executable=opa,
                )
                result["scope"] = "frozen_twelve_case_synthetic_corpus"
            channel.send({"stage": "operation_executed"})
            payload = {
                "schema_version": 1,
                "job_id": job_id,
                "run_id": run.run_id,
                "source_capsule_digest": run.capsule_digest,
                "report": result,
            }
            data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            ref = store.put(data)
            channel.send({"result": {"digest": ref.digest, "size": ref.size}})
    except BaseException as error:
        with suppress(OSError, EOFError):
            channel.send({"error_type": type(error).__name__})
    finally:
        signal.alarm(0)
        channel.close()


class JobBusy(RuntimeError):
    pass


class Operations:
    def __init__(
        self, engine: Engine, store: IndexStore, root: Path, key: Path | None, opa: Path | None
    ) -> None:
        self.engine, self.store, self.root, self.key, self.opa = engine, store, root, key, opa
        self.owner = uuid4().hex
        self.pending: queue.Queue[str] = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.guard = threading.Lock()
        self.descriptor: int | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        with self.guard:
            if self.thread is not None:
                return
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                self.root / "controller.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(descriptor)
                raise JobBusy("another local controller owns this evidence root") from None
            self.descriptor = descriptor
            try:
                self._interrupt_unfinished()
            except BaseException:
                os.close(descriptor)
                self.descriptor = None
                raise
            self.stop.clear()
            self.thread = threading.Thread(
                target=self._supervise, name="sentinel-operations", daemon=True
            )
            self.thread.start()

    def _interrupt_unfinished(self) -> None:
        latest = (
            select(operation_events.c.job_id, func.max(operation_events.c.sequence).label("last"))
            .group_by(operation_events.c.job_id)
            .subquery()
        )
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(operation_events)
                    .join(
                        latest,
                        (operation_events.c.job_id == latest.c.job_id)
                        & (operation_events.c.sequence == latest.c.last),
                    )
                    .where(operation_events.c.state.in_(["accepted", "running"]))
                )
                .mappings()
                .all()
            )
        for row in rows:
            self.append(
                row["job_id"],
                row["sequence"],
                "interrupted",
                {"reason": "controller_restarted_or_stopped", "owner": self.owner},
            )

    def append(self, job_id: str, previous: int, state: str, body: dict[str, Any]) -> int:
        with self.engine.begin() as connection:
            connection.execute(
                insert(operation_events).values(
                    job_id=job_id, sequence=previous + 1, state=state, body=body, created_at=_now()
                )
            )
        return previous + 1

    def submit(
        self, run: StoredRun, request: OperationRequest, branch_artifact: str | None = None
    ) -> str:
        self.start()
        with self.guard:
            if self.pending.full() or self.stop.is_set():
                raise JobBusy("operation queue budget exhausted")
            job_id = uuid4().hex
            envelope = {
                "request": request.model_dump(),
                "run": run.__dict__,
                "branch_artifact": branch_artifact,
            }
            ref = self.store.put(
                json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
            )
            with self.engine.begin() as connection:
                connection.execute(
                    insert(operation_jobs).values(
                        job_id=job_id,
                        run_id=run.run_id,
                        kind=request.kind,
                        request_digest=ref.digest,
                        request_size=ref.size,
                        created_at=_now(),
                    )
                )
                connection.execute(
                    insert(operation_events).values(
                        job_id=job_id,
                        sequence=0,
                        state="accepted",
                        body={"owner": self.owner, "coverage": "closed_local_operation"},
                        created_at=_now(),
                    )
                )
            self.pending.put_nowait(job_id)
            return job_id

    def get(self, run_id: str, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            job = (
                connection.execute(
                    select(operation_jobs).where(
                        operation_jobs.c.run_id == run_id, operation_jobs.c.job_id == job_id
                    )
                )
                .mappings()
                .first()
            )
            if job is None:
                return None
            latest = (
                connection.execute(
                    select(operation_events)
                    .where(operation_events.c.job_id == job_id)
                    .order_by(operation_events.c.sequence.desc())
                    .limit(1)
                )
                .mappings()
                .one()
            )
        return {
            "job_id": job_id,
            "run_id": run_id,
            "kind": job["kind"],
            "created_at": job["created_at"],
            "sequence": latest["sequence"],
            "state": latest["state"],
            "detail": latest["body"],
        }

    def events(self, job_id: str, after: int = -1) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(operation_events)
                    .where(operation_events.c.job_id == job_id, operation_events.c.sequence > after)
                    .order_by(operation_events.c.sequence)
                    .limit(100)
                ).mappings()
            ]

    def list(self, run_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("invalid operation list budget")
        with self.engine.connect() as connection:
            identifiers: list[str] = list(
                connection.execute(
                    select(operation_jobs.c.job_id)
                    .where(operation_jobs.c.run_id == run_id)
                    .order_by(operation_jobs.c.created_at.desc(), operation_jobs.c.job_id)
                    .limit(limit)
                ).scalars()
            )
        return [
            job for identifier in identifiers if (job := self.get(run_id, identifier)) is not None
        ]

    def result(self, run_id: str, job_id: str) -> dict[str, Any]:
        job = self.get(run_id, job_id)
        if job is None or job["state"] != "completed":
            raise ValueError("operation has no completed result")
        ref = job["detail"]["result"]
        value = load_json_unique(self.store.get(BlobRef(ref["digest"], ref["size"])).decode())
        run = RunRepository(self.engine).get(run_id)
        if (
            not isinstance(value, dict)
            or value.get("job_id") != job_id
            or value.get("run_id") != run_id
            or run is None
            or value.get("source_capsule_digest") != run.capsule_digest
        ):
            raise ValueError("operation result source binding differs")
        return value

    @staticmethod
    def _terminate(process: BaseProcess) -> None:
        if process.is_alive():
            try:
                pid = process.pid
                if pid is not None and os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)

    def _execute(self, job_id: str) -> None:
        with self.engine.connect() as connection:
            job = (
                connection.execute(select(operation_jobs).where(operation_jobs.c.job_id == job_id))
                .mappings()
                .one()
            )
        sequence = self.append(job_id, 0, "running", {"owner": self.owner, "stage": "starting"})
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        scratch = tempfile.TemporaryDirectory(prefix="sentinel-job-")
        process = context.Process(
            target=_worker,
            args=(
                send,
                self.root,
                self.key,
                BlobRef(job["request_digest"], job["request_size"]),
                self.opa,
                job_id,
                Path(scratch.name),
            ),
        )
        try:
            process.start()
        except BaseException:
            receive.close()
            send.close()
            scratch.cleanup()
            process.close()
            raise
        send.close()
        deadline = time.monotonic() + 603
        terminal = False
        try:
            while not self.stop.is_set() and time.monotonic() < deadline:
                if receive.poll(0.1):
                    try:
                        value = receive.recv()
                    except EOFError:
                        break
                    if "result" in value:
                        self.append(
                            job_id,
                            sequence,
                            "completed",
                            {"owner": self.owner, "result": value["result"]},
                        )
                        terminal = True
                        break
                    if "error_type" in value:
                        self.append(job_id, sequence, "failed", {"owner": self.owner, **value})
                        terminal = True
                        break
                    sequence = self.append(
                        job_id, sequence, "running", {"owner": self.owner, **value}
                    )
                elif not process.is_alive():
                    break
            if not terminal:
                self.append(
                    job_id,
                    sequence,
                    "interrupted",
                    {"owner": self.owner, "reason": "worker_exit_controller_stop_or_deadline"},
                )
        finally:
            self._terminate(process)
            process.join(timeout=2)
            receive.close()
            process.close()
            scratch.cleanup()

    def _supervise(self) -> None:
        while not self.stop.is_set():
            try:
                job_id = self.pending.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._execute(job_id)
            except (OSError, ValueError, SQLAlchemyError):
                # On a healthy metadata path record failure immediately. If SQL
                # itself is unavailable, startup recovery will mark it interrupted.
                try:
                    with self.engine.connect() as connection:
                        row = (
                            connection.execute(
                                select(operation_events)
                                .where(operation_events.c.job_id == job_id)
                                .order_by(operation_events.c.sequence.desc())
                                .limit(1)
                            )
                            .mappings()
                            .one()
                        )
                    if row["state"] not in TERMINAL:
                        self.append(
                            job_id,
                            row["sequence"],
                            "interrupted",
                            {"reason": "controller_exception", "owner": self.owner},
                        )
                except SQLAlchemyError:
                    pass
            finally:
                self.pending.task_done()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("operation supervisor did not stop")
            self._interrupt_unfinished()
            self.thread = None
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
