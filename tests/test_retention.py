import json
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
from sentinel_replay.encrypted_store import EncryptedEvidenceStore
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.journal import Journal
from sentinel_replay.operations import Operations
from sentinel_replay.retention import collect_evidence


@pytest.mark.parametrize("encrypted", [False, True])
def test_offline_collection_keeps_shared_live_data_and_refuses_active_writer(
    tmp_path: Path, encrypted: bool
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    root = tmp_path / "evidence"
    root.mkdir()
    key = None
    if encrypted:
        key = tmp_path / "storage.key"
        key.touch(mode=0o600)
        key.write_bytes(b"s" * 32)
    store = EncryptedEvidenceStore(root, key) if key else FileEvidenceStore(root)
    shared = store.put(b"synthetic shared reachability fixture")
    orphan = store.put(b"synthetic orphan")
    repository = RunRepository(engine)
    for name in ("active", "retired"):
        repository.insert_or_get(
            StoredRun(
                name, "sha256:" + "0" * 64, 0, shared.digest, shared.size, "sha256:" + "1" * 64
            )
        )
    repository.retire("retired", "2026-11-13T00:00:00Z", "operator_deletion")
    controller = Operations(engine, store, root, key, None)
    try:
        controller.start()
        with pytest.raises(ValueError, match="stop the controller"):
            collect_evidence(engine, root, key, apply=True)
    finally:
        controller.close()
    preview = collect_evidence(engine, root, key)
    assert preview["candidate_objects"] == 1
    assert preview["objects_removed"] == 0
    assert store.get(orphan) == b"synthetic orphan"
    result = collect_evidence(engine, root, key, apply=True)
    assert result["objects_removed"] == 1
    assert store.get(shared) == b"synthetic shared reachability fixture"
    with pytest.raises(FileNotFoundError):
        store.get(orphan)
    assert repository.get("retired") is None
    assert repository.get("retired", include_retired=True) is not None
    repository.retire("active", "2026-11-13T00:00:00Z", "retention_expired")
    assert collect_evidence(engine, root, key, apply=True)["objects_removed"] == 1
    assert collect_evidence(engine, root, key)["candidate_objects"] == 0


def test_inventory_symlink_refusal_happens_before_any_collection(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "controller.lock").touch(mode=0o600)
    outside = tmp_path / "outside"
    outside.mkdir()
    canary = outside / ("a" * 64)
    canary.write_bytes(b"must survive")
    (root / "sha256").mkdir()
    (root / "sha256/aa").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        collect_evidence(engine, root, apply=True)
    assert canary.read_bytes() == b"must survive"


@pytest.mark.parametrize("encrypted", [False, True])
def test_active_future_and_completed_job_descendants_survive_collection(
    tmp_path: Path, encrypted: bool
) -> None:
    # Reachability fixtures verify content identity, not execution or signatures.
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}")
    metadata.create_all(engine)
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "controller.lock").touch(mode=0o600)
    key = None
    if encrypted:
        key = tmp_path / "storage.key"
        key.touch(mode=0o600)
        key.write_bytes(b"s" * 32)
    store = EncryptedEvidenceStore(root, key) if key else FileEvidenceStore(root)
    parent = store.put(b"parent")
    child = store.put(b"active legacy future payload")
    job_child = store.put(b"active job future payload")
    RunRepository(engine).insert_or_get(
        StoredRun(
            "active", "sha256:" + "0" * 64, 0, parent.digest, parent.size, "sha256:" + "1" * 64
        )
    )
    receipt = store.put(
        json.dumps(
            {
                "kind": "finite_future_receipt",
                "parent_run_id": "active",
                "parent_capsule_digest": parent.digest,
                "capsule_digest": child.digest,
                "capsule_size": child.size,
            }
        ).encode()
    )
    # Historical entry intentionally has no size; encrypted-envelope length
    # recovery must preserve this existing reference too.
    Journal(root / "access-audit.jsonl").append(
        {"kind": "future_created", "run_id": "active", "receipt": receipt.digest}
    )
    request = store.put(b"closed job request fixture")
    result = store.put(
        json.dumps(
            {
                "job_id": "a" * 32,
                "run_id": "active",
                "source_capsule_digest": parent.digest,
                "report": {"capsule": {"digest": job_child.digest, "size": job_child.size}},
            }
        ).encode()
    )
    with engine.begin() as connection:
        connection.execute(
            insert(operation_jobs).values(
                job_id="a" * 32,
                run_id="active",
                kind="fork",
                request_digest=request.digest,
                request_size=request.size,
                created_at="fixture",
            )
        )
        connection.execute(
            insert(operation_events).values(
                job_id="a" * 32,
                sequence=0,
                state="completed",
                body={"result": {"digest": result.digest, "size": result.size}},
                created_at="fixture",
            )
        )
    report = collect_evidence(engine, root, key, apply=True)
    assert report["candidate_objects"] == 0
    assert store.get(child) == b"active legacy future payload"
    assert store.get(job_child) == b"active job future payload"
