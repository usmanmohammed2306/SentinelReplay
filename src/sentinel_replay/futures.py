"""Covered finite-program intervention after a verified recorded prefix.

This re-executes the trusted finite pack from its checkpoint, applying the original
decisions before the fork and a real OPA policy afterward. It never resumes a
native process or calls a live model/network; changed futures are simulations.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from sentinel_replay.blob_bank import restore_blob_bank
from sentinel_replay.canonical import load_json_unique
from sentinel_replay.checkpoint_set import restore_checkpoint_set
from sentinel_replay.divergence import compare_recordings
from sentinel_replay.environment_pack import Pack, record_pack, replay_pack
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Policy, evaluate_batch, policy_digest


def simulate_future(
    investigation: CapsuleInvestigation,
    policy: Policy,
    destination: Path,
    *,
    fork_step: int = 0,
    opa_executable: Path | None = None,
) -> dict[str, Any]:
    artifacts = investigation.artifacts
    if "pack-definition.json" not in artifacts:
        raise ValueError("alternate finite futures require an environment-pack capsule")
    definition = load_json_unique(artifacts["pack-definition.json"].decode())
    pack = Pack.model_validate(definition["pack"])
    if not 0 <= fork_step <= len(pack.steps):
        raise ValueError("fork step is outside the finite program")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="sentinel-future-prefix-") as directory:
        source = Path(directory) / "source"
        source.mkdir()
        (source / "definition.json").write_bytes(artifacts["pack-definition.json"])
        (source / "report.json").write_bytes(artifacts["report.json"])
        (source / "journal.jsonl").write_bytes(investigation.journal)
        store = FileEvidenceStore(source / "blobs", max_bytes=32 * 1024 * 1024)
        restore_blob_bank(artifacts, store)
        prefix = replay_pack(
            source,
            Path(directory) / "prefix",
            through=fork_step,
            extra_restore=lambda target, expected: restore_checkpoint_set(
                artifacts, target, expected
            ),
        )
        # Full baseline replay is needed before interpreting final state differences.
        baseline = replay_pack(
            source,
            Path(directory) / "baseline",
            extra_restore=lambda target, expected: restore_checkpoint_set(
                artifacts, target, expected
            ),
        )
        decisions = evaluate_batch(
            policy,
            [step.action for step in pack.steps],
            executable=str(opa_executable) if opa_executable is not None else None,
        )
        decisions[:fork_step] = definition["decisions"][:fork_step]
        future_source = destination / "branch"
        report = record_pack(
            pack,
            future_source,
            policy,
            decisions=decisions,
            decision_source=f"recorded_prefix_before_{fork_step};real_opa_after_fork",
            extra_checkpoint_digests=definition.get("extra_checkpoint_digests", {}),
        )
        future_store = FileEvidenceStore(future_source / "blobs", max_bytes=32 * 1024 * 1024)
        restore_blob_bank(artifacts, future_store)
        for name in ("sqlite-manifest.json", "git-manifest.json"):
            if name in artifacts:
                (future_source / name).write_bytes(artifacts[name])
    capsule = destination / "future.sentinel"
    export_pack(future_source, capsule)
    future = CapsuleInvestigation(capsule.read_bytes())
    receipt = future.replay()
    original = load_json_unique(artifacts["report.json"].decode())
    left = {item["path"]: item for item in original["final_manifest"]["entries"]}
    right = {item["path"]: item for item in report["final_manifest"]["entries"]}
    changes = [
        {"path": name, "before": left.get(name), "after": right.get(name)}
        for name in sorted(left.keys() | right.keys())
        if left.get(name) != right.get(name)
    ]
    divergent = next(
        (
            i
            for i, (a, b) in enumerate(zip(definition["decisions"], decisions, strict=True))
            if a != b
        ),
        None,
    )
    result = {
        "schema_version": 1,
        "mode": report["mode"],
        "original_journal_root": investigation.verified.root,
        "future_journal_root": future.verified.root,
        "policy_digest": policy_digest(policy),
        "fork_program_step": fork_step,
        "verified_prefix": prefix,
        "baseline_replay": baseline,
        "future_replay": receipt,
        "first_policy_decision_divergence": divergent,
        "world_diff": changes,
        "divergence": compare_recordings(investigation, future),
        "incidents": future.incidents()["incidents"],
        "status": report["status"],
        "limitation": (
            "Finite-program re-execution with frozen pre-fork decisions. "
            "Simulated future, not native agent continuation or a causal proof."
        ),
    }
    (destination / "future-report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result
