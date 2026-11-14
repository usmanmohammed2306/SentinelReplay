import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert

from sentinel_replay.database import (
    RunRepository,
    StoredRun,
    metadata,
    operation_events,
    operation_jobs,
)
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.operations import JobBusy, OperationRequest, Operations

CAPSULE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/results/isolated-branches-final-2026-11-13"
    / "protected_export--allow_both/controller/branch.sentinel"
)


def test_real_process_job_persists_result_and_rejects_second_controller(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    root = tmp_path / "evidence"
    store = FileEvidenceStore(root, max_bytes=65 * 1024 * 1024)
    source = CapsuleInvestigation(CAPSULE.read_bytes())
    ref = store.put(source.data)
    run = StoredRun(
        source.verified.run_id,
        source.verified.root,
        source.verified.records,
        ref.digest,
        ref.size,
        "sha256:" + "0" * 64,
    )
    RunRepository(engine).insert_or_get(run)
    controller = Operations(engine, store, root, None, None)
    other = Operations(engine, store, root, None, None)
    try:
        job = controller.submit(run, OperationRequest(kind="replay"))
        with pytest.raises(JobBusy, match="another local controller"):
            other.start()
        deadline = time.monotonic() + 10
        while True:
            status = controller.get(run.run_id, job)
            assert status is not None
            if status["state"] in {"completed", "failed", "interrupted"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert status["state"] == "completed", status
        result = controller.result(run.run_id, job)
        assert result["report"]["mode"] == "BOUNDARY_REPLAY_MATCHED"
        assert result["report"]["live_calls"] == 0
        assert controller.get("different-parent", job) is None
        events = controller.events(job)
        assert [row["sequence"] for row in events] == list(range(len(events)))
        assert events[0]["state"] == "accepted"
        assert events[-1]["state"] == "completed"
    finally:
        controller.close()
        other.close()
    # A new controller can read the retained result; closing did not rewrite it.
    restarted = Operations(engine, store, root, None, None)
    try:
        restarted.start()
        assert restarted.result(run.run_id, job) == result
    finally:
        restarted.close()


def test_restart_marks_unfinished_record_interrupted_without_inventing_result(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    store = FileEvidenceStore(tmp_path / "cas")
    run = StoredRun(
        "fixture", "sha256:" + "0" * 64, 0, "sha256:" + "1" * 64, 0, "sha256:" + "2" * 64
    )
    RunRepository(engine).insert_or_get(run)
    with engine.begin() as connection:
        connection.execute(
            insert(operation_jobs).values(
                job_id="f" * 32,
                run_id="fixture",
                kind="replay",
                request_digest="sha256:" + "3" * 64,
                request_size=1,
                created_at="fixture",
            )
        )
        connection.execute(
            insert(operation_events).values(
                job_id="f" * 32,
                sequence=0,
                state="running",
                body={"owner": "old-controller"},
                created_at="fixture",
            )
        )
    controller = Operations(engine, store, store.root, None, None)
    try:
        controller.start()
        status = controller.get("fixture", "f" * 32)
        assert status is not None and status["state"] == "interrupted"
        with pytest.raises(ValueError, match="no completed result"):
            controller.result("fixture", "f" * 32)
    finally:
        controller.close()
