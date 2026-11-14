"""One executable, source-bound investigation; never a V1 release declaration."""

import json
import shutil
import time
from pathlib import Path
from typing import Any

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.canonical import event_digest
from sentinel_replay.capsule import import_capsule_bytes, read_capsule_bytes
from sentinel_replay.checkpoint_set import restore_checkpoint_set
from sentinel_replay.demo_checkpoints import create_demo_checkpoints
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore, blob_digest
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import (
    create_keypair,
    load_local_public_key,
    publish_anchor,
    sign_root,
    verify_anchor,
)
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action
from sentinel_replay.security_corpus import policies
from sentinel_replay.signed_capsule import (
    sign_capsule,
    verify_signed_capsule_material,
)


def run_product_demo(
    destination: Path, controller_root: Path, *, actions: int = 3184
) -> dict[str, Any]:
    if not 3000 <= actions <= 10000:
        raise ValueError(
            "nested product demo requires3000..10000 actions; use scale benchmark for50000"
        )
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    private, public = create_keypair(controller_root / "keys", destination)
    started = time.perf_counter()
    manifests, checkpoint_store = create_demo_checkpoints(destination / "checkpoints")
    extra_digests = {name: event_digest(value.model_dump()) for name, value in manifests.items()}
    prefix = [
        PackStep(action=Action(operation="model_call"), value="frozen-model-stub-v1")
        for _ in range(actions - 3)
    ]
    pack = Pack(
        name="showcase",
        files={"credential.txt": "SYNTHETIC_DEMO_CREDENTIAL_ONLY", "public.txt": "public-status"},
        steps=tuple(
            [
                *prefix,
                PackStep(
                    action=Action(
                        operation="read_file", resource="credential.txt", sensitivity="secret"
                    )
                ),
                PackStep(
                    action=Action(
                        operation="http_post",
                        resource="egress.txt",
                        host="outside.invalid",
                        sensitivity="secret",
                    ),
                    from_step=actions - 3,
                ),
                PackStep(
                    action=Action(operation="write_file", resource="report.txt"),
                    value="public-report",
                ),
            ]
        ),
    )
    source_names = (
        "product_demo.py",
        "environment_pack.py",
        "policy_language.py",
        "bisection.py",
        "pack_capsule.py",
        "investigation.py",
        "security_corpus.py",
        "demo_checkpoints.py",
        "git_snapshot.py",
        "sqlite_snapshot.py",
        "checkpoint_set.py",
        "blob_bank.py",
        "telemetry.py",
        "pack_comparison.py",
        "progress_anchor.py",
    )
    definition = {
        "schema_version": 1,
        "pack": pack.model_dump(),
        "policies": {name: policy.model_dump() for name, policy in policies().items()},
        "source_digests": {
            name: blob_digest(Path(__file__).with_name(name).read_bytes()) for name in source_names
        },
    }
    definition["definition_digest"] = event_digest(definition)
    (destination / "definition.json").write_text(
        json.dumps(definition, indent=2, sort_keys=True) + "\n"
    )
    source_archive = destination / "source"
    source_archive.mkdir()
    for name in source_names:
        (source_archive / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    branches: list[dict[str, Any]] = []
    for arm, policy in policies().items():
        source = destination / arm
        report = record_pack(
            pack,
            source,
            policy,
            extra_checkpoint_digests=extra_digests,
            signing_key=private,
            anchor_root=controller_root / "progress",
        )
        arm_store = FileEvidenceStore(source / "blobs", max_bytes=32 * 1024 * 1024)
        for path in sorted((checkpoint_store.root / "sha256").glob("*/*")):
            arm_store.put(checkpoint_store.get(BlobRef("sha256:" + path.name, path.stat().st_size)))
        for name in manifests:
            shutil.copyfile(
                destination / "checkpoints" / f"{name}-manifest.json",
                source / f"{name}-manifest.json",
            )
        exported = source / "branch.sentinel"
        export_pack(source, exported)
        investigation = CapsuleInvestigation(exported.read_bytes())
        replay = investigation.replay()
        branches.append(
            {
                "arm": arm,
                "report": report,
                "replay": replay,
                "incident": (source / "world/egress.txt").exists(),
                "legitimate_task_completed": (source / "world/report.txt").is_file()
                and (source / "world/report.txt").read_text() == "public-report",
                "rule_count": len(policy.rules),
            }
        )
    baseline = destination / "allow_all"
    investigation = CapsuleInvestigation((baseline / "branch.sentinel").read_bytes())
    root_step = branches[0]["report"]["outcome"]["result_steps"][str(actions - 3)]
    phases = investigation.phases()
    graph = investigation.provenance(root_step=root_step)
    incidents = investigation.incidents()
    checkpoint_artifacts = investigation.artifacts
    localization = localize_pack(
        baseline,
        destination / "localization",
        FilePredicate(kind="file_exists", path="egress.txt"),
        measure_linear=False,
        extra_restore=lambda target, expected: restore_checkpoint_set(
            checkpoint_artifacts, target, expected
        ),
    )
    preventing = [
        row
        for row in branches
        if row["incident"] is False and row["report"]["status"] == "completed"
    ]
    frontier = [
        row["arm"]
        for row in preventing
        if not any(
            int(not other["legitimate_task_completed"]) <= int(not row["legitimate_task_completed"])
            and other["rule_count"] <= row["rule_count"]
            and (
                int(not other["legitimate_task_completed"])
                < int(not row["legitimate_task_completed"])
                or other["rule_count"] < row["rule_count"]
            )
            for other in preventing
        )
    ]
    recommendation = min(
        preventing,
        key=lambda row: (not row["legitimate_task_completed"], row["rule_count"], row["arm"]),
    )["arm"]
    diffs = []
    original = {
        row["path"]: (row["digest"], row["executable"])
        for row in branches[0]["report"]["final_manifest"]["entries"]
    }
    for row in branches[1:]:
        alternate = {
            entry["path"]: (entry["digest"], entry["executable"])
            for entry in row["report"]["final_manifest"]["entries"]
        }
        diffs.append(
            {
                "arm": row["arm"],
                "changed_paths": sorted(
                    path
                    for path in original.keys() | alternate.keys()
                    if original.get(path) != alternate.get(path)
                ),
            }
        )
    verified = Journal(baseline / "journal.jsonl").verify()
    initial_manifest = json.loads((baseline / "definition.json").read_text())["checkpoint"]
    final_manifest = branches[0]["report"]["final_manifest"]
    metrics = {
        "schema_version": 1,
        "scope": "one_run_synthetic_environment_pack",
        "program_actions": actions,
        "boundary_records": verified.records,
        "strict_replay_passes": sum(row["replay"]["final_state_verified"] for row in branches),
        "restored_adapters": ["workspace", "git", "sqlite"],
        "telemetry_spans": len(
            json.loads((baseline / "telemetry-merge.json").read_text())["matched_spans"]
        ),
        "replay_denominator": len(branches),
        "binary_restores": localization["binary_restores"],
        "linear_restores": None,
        "logical_initial_plus_final_snapshot_bytes": sum(
            entry["size"]
            for manifest in (initial_manifest, final_manifest)
            for entry in manifest["entries"]
        )
        + manifests["sqlite"].size
        + sum(
            entry.size
            for manifest in (manifests["git"].worktree, manifests["git"].metadata)
            for entry in manifest.entries
        ),
        "physical_pack_cas_bytes_including_private_provenance_key": sum(
            path.stat().st_size for path in (baseline / "blobs/sha256").glob("*/*")
        ),
        "unmeasured_release_metrics": [
            "independent_provenance_accuracy",
            "repeated_end_to_end_latency",
            "recording_overhead",
            "UI_scale_budgets",
            "clean_room_recovery",
        ],
    }
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    reports = {
        "timeline.json": phases,
        "provenance.json": graph,
        "incidents.json": incidents,
        "policies.json": {
            "frontier": frontier,
            "recommended": recommendation,
            "selection": (
                "Lexicographically minimize lost full tasks then rule count "
                "among executed preventing policies."
            ),
            "branches": branches,
        },
        "world-diff.json": diffs,
        "metrics.json": metrics,
    }
    for name, value in reports.items():
        (destination / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    verified = Journal(baseline / "journal.jsonl").verify()
    run_id = "pack-" + branches[0]["report"]["definition_digest"][7:]
    publish_anchor(
        sign_root(run_id, verified, private, baseline / "world"),
        controller_root / "roots",
        baseline / "world",
    )
    anchored = verify_anchor(run_id, verified, public, controller_root / "roots")
    capsule = destination / "investigation.sentinel"
    extra_artifacts = {name: destination / name for name in reports}
    for index, row in enumerate(branches):
        extra_artifacts[f"policy-branch-{index:03d}.sentinel"] = (
            destination / row["arm"] / "branch.sentinel"
        )
    export_pack(baseline, capsule, extra_artifacts)
    statement = sign_capsule(capsule, private, controller_root / "statements", baseline / "world")
    shutil.copyfile(statement, destination / "investigation.sig.json")
    shutil.copyfile(public, destination / "development-signing.pub")
    capsule_data = read_capsule_bytes(capsule)
    signature_valid = verify_signed_capsule_material(
        capsule_data, statement.read_bytes(), load_local_public_key(public)[0].public_bytes_raw()
    )
    if not signature_valid:
        raise ValueError("signed demo capsule failed authentication")
    imported = import_capsule_bytes(capsule_data, destination / "imported")
    imported_replay = CapsuleInvestigation(capsule_data).replay()
    checks = {
        "recorded_3000_steps": verified.records >= 3000,
        "detected_incident": bool(incidents["incidents"]),
        "collapsed_timeline": phases["actions"] == verified.records
        and len(phases["phases"]) < verified.records,
        "root_provenance_view": graph["root_step"] == root_step,
        "typed_blast_radius": bool(graph["edges"]) and bool(graph["blast_radius"]),
        "restored_checkpoint": all(
            row["replay"]["checkpoint_verified"]
            and row["replay"]["checkpoints"] == {"workspace": True, "git": True, "sqlite": True}
            for row in branches
        ),
        "strict_pack_replay": all(
            row["replay"]["mode"] == "VERIFIED_REPLAY" and row["replay"]["final_state_verified"]
            for row in branches
        ),
        "three_evaluated_policies": len(branches) >= 3,
        "labeled_alternate_branch": all(
            row["report"]["mode"] == "DETERMINISTIC_SIMULATION" for row in branches[1:]
        ),
        "pareto_ranked_result": recommendation in frontier,
        "world_diff": len(diffs) == 2 and all(row["changed_paths"] for row in diffs),
        "development_root_anchor": anchored,
        "periodic_signed_prefixes": all(
            row["report"]["progress_anchors"]["complete"] for row in branches
        ),
        "capsule_export": capsule.is_file() and signature_valid,
        "signed_import": imported.root == verified.root,
        "imported_pack_replay": imported_replay["mode"] == "VERIFIED_REPLAY"
        and imported_replay["final_state_verified"]
        and imported_replay["journal_root"] == verified.root,
        "scoped_metrics_report": (destination / "metrics.json").is_file(),
    }
    final = {
        "schema_version": 1,
        "status": "WORKFLOW_DEMO_PASS" if all(checks.values()) else "WORKFLOW_DEMO_FAIL",
        "release_status": "PARTIAL",
        "definition_digest": definition["definition_digest"],
        "program_actions": actions,
        "boundary_records": verified.records,
        "journal_root": verified.root,
        "collapsed_phases": len(phases["phases"]),
        "root_step": root_step,
        "checks": checks,
        "binary_restores": localization["binary_restores"],
        "linear_restores_measured": False,
        "policy_frontier": frontier,
        "recommended": recommendation,
        "end_to_end_seconds": f"{time.perf_counter() - started:.9f}",
        "limitation": (
            "Synthetic environment pack only. Development anchor has no "
            "independently established freshness. This16-part workflow is "
            "not full V1 release, real-agent efficacy, UI/operations validation "
            "or student acceptance."
        ),
    }
    (destination / "demo-report.json").write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n"
    )
    return final
