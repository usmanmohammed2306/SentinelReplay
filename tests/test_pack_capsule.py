import sqlite3
from pathlib import Path

import pytest

from sentinel_replay.canonical import event_digest
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Policy
from sentinel_replay.sqlite_snapshot import capture_sqlite


def test_portable_pack_reexecutes_covered_effect_from_imported_checkpoint(tmp_path: Path) -> None:
    pack = Pack(
        name="portable",
        files={"public.txt": "public"},
        steps=(
            PackStep(action=Action(operation="read_file", resource="public.txt")),
            PackStep(action=Action(operation="write_file", resource="report.txt"), from_step=0),
        ),
    )
    source = tmp_path / "source"
    record_pack(
        pack, source, Policy(), decisions=["allowed", "allowed"], decision_source="test_fixture"
    )
    capsule = tmp_path / "pack.sentinel"
    export_pack(source, capsule)
    investigation = CapsuleInvestigation(capsule.read_bytes())
    assert investigation.summary()["record_type"] == "environment_pack"
    report = investigation.replay()
    assert report["mode"] == "VERIFIED_REPLAY"
    assert report["effects_reexecuted"] == 1
    assert report["final_state_verified"]
    assert report["live_calls"] == 0


def test_many_checkpoint_files_do_not_exhaust_capsule_member_budget(tmp_path: Path) -> None:
    pack = Pack(
        name="many-files",
        files={f"file-{i}.txt": f"content-{i}" for i in range(100)},
        steps=(PackStep(action=Action(operation="read_file", resource="file-99.txt")),),
    )
    source = tmp_path / "source"
    record_pack(pack, source, Policy(), decisions=["allowed"], decision_source="test_fixture")
    capsule = tmp_path / "many.sentinel"
    export_pack(source, capsule)
    investigation = CapsuleInvestigation(capsule.read_bytes())
    assert len(investigation.artifacts) < 10
    assert investigation.replay()["final_state_verified"]


def test_identical_program_repeats_have_distinct_run_identity_and_same_covered_semantics(
    tmp_path: Path,
) -> None:
    pack = Pack(
        name="repeat",
        files={},
        steps=(PackStep(action=Action(operation="model_call"), value="stub"),),
    )
    runs = []
    for index in range(2):
        source = tmp_path / str(index)
        record_pack(pack, source, Policy(), decisions=["allowed"], decision_source="test_fixture")
        capsule = tmp_path / f"{index}.sentinel"
        export_pack(source, capsule)
        investigation = CapsuleInvestigation(capsule.read_bytes())
        runs.append(investigation)
        assert investigation.replay()["mode"] == "VERIFIED_REPLAY"
    assert runs[0].verified.run_id != runs[1].verified.run_id
    assert runs[0].verified.root == runs[1].verified.root


def test_declared_database_checkpoint_is_restored_before_verified_pack_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE data (value TEXT)")
        connection.execute("INSERT INTO data VALUES('initial')")
    extra_store = FileEvidenceStore(tmp_path / "checkpoint-cas")
    checkpoint = capture_sqlite(database, extra_store)
    pack = Pack(name="database", files={}, steps=(PackStep(action=Action(operation="model_call")),))
    source = tmp_path / "source"
    record_pack(
        pack,
        source,
        Policy(),
        decisions=["allowed"],
        decision_source="test_fixture",
        extra_checkpoint_digests={"sqlite": event_digest(checkpoint.model_dump())},
    )
    store = FileEvidenceStore(source / "blobs")
    store.put(extra_store.get(BlobRef(checkpoint.digest, checkpoint.size)))
    manifest = tmp_path / "sqlite-manifest.json"
    manifest.write_text(checkpoint.model_dump_json())
    capsule = tmp_path / "database.sentinel"
    export_pack(source, capsule, {"sqlite-manifest.json": manifest})
    result = CapsuleInvestigation(capsule.read_bytes()).replay()
    assert result["checkpoints"] == {"workspace": True, "sqlite": True}
    assert result["mode"] == "VERIFIED_REPLAY"
    from sentinel_replay.environment_pack import replay_pack

    with pytest.raises(RuntimeError, match="not restored"):
        replay_pack(source, tmp_path / "incomplete-replay")
