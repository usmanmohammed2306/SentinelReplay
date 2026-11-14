"""Finite trusted environment pack with durable intents and covered effect replay.

No program text is executed. HTTP/process/model/handoff operations are declared
local simulations or stubs. Strict replay's guarantee is only this adapter's
regular-file world and recorded nondeterministic inputs, never the live agent.
"""

import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel_replay.boundary import ReplayMiss
from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore, blob_digest
from sentinel_replay.journal import Journal
from sentinel_replay.policy_language import Action, Decision, Policy, evaluate_batch, policy_digest
from sentinel_replay.progress_anchor import ProgressAnchors, verify_progress
from sentinel_replay.replay_profiles import validate_replay_profile
from sentinel_replay.telemetry import RecordingTelemetry, merge_telemetry
from sentinel_replay.workspace_snapshot import (
    WorkspaceManifest,
    capture_workspace,
    restore_workspace,
    verify_workspace,
)

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_EFFECTS = frozenset(
    {"write_file", "delete_file", "http_post", "artifact_export", "handoff", "env_set", "git_write"}
)
_SUPPORTED = _EFFECTS | {"read_file", "clock", "rng", "model_call", "process_exec"}
Emit = Callable[[str, dict[str, Any], dict[str, Any], dict[str, Any]], int]


def _runtime_digests() -> dict[str, str]:
    return {
        name: blob_digest(Path(__file__).with_name(name).read_bytes())
        for name in (
            "environment_pack.py",
            "policy_language.py",
            "canonical.py",
            "journal.py",
            "workspace_snapshot.py",
            "evidence_store.py",
            "telemetry.py",
            "progress_anchor.py",
            "replay_profiles.py",
        )
    }


class PackStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Action
    value: str | None = Field(default=None, max_length=8192)
    from_step: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def safe_resource(self) -> "PackStep":
        if self.action.operation in _EFFECTS | {"read_file"} and (
            self.action.resource is None
            or not _NAME.fullmatch(self.action.resource)
            or self.action.resource in {".", ".."}
        ):
            raise ValueError("pack file operations require a bounded basename")
        return self


class Pack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    files: dict[str, str]
    steps: tuple[PackStep, ...] = Field(min_length=1, max_length=50000)
    seed: int | None = 11

    @model_validator(mode="after")
    def bounded(self) -> "Pack":
        if (
            len(self.files) > 100
            or sum(len(value.encode()) for value in self.files.values()) > 1_000_000
        ):
            raise ValueError("pack seed exceeds file or byte budget")
        if any(not _NAME.fullmatch(name) or name in {".", ".."} for name in self.files):
            raise ValueError("pack seed requires basename-only regular files")
        if any(
            step.from_step is not None and step.from_step >= index
            for index, step in enumerate(self.steps)
        ):
            raise ValueError("pack dependencies must point to an earlier step")
        return self


def _write_json(path: Path, value: object) -> None:
    # Publish only fully flushed metadata, before any covered mutation can run.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".metadata-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path, follow_symlinks=False)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)


def _run(
    pack: Pack,
    world: Path,
    store: FileEvidenceStore,
    decisions: list[Decision],
    emit: Emit,
    provenance_key: bytes,
    input_response: Callable[[int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    values: dict[int, str | None] = {}
    result_steps: dict[str, int] = {}
    effects = 0
    unknown = []
    for index, step in enumerate(pack.steps):
        action = step.action
        operation = action.operation
        if operation not in _SUPPORTED:
            unknown.append(index)
            break
        value = values.get(step.from_step) if step.from_step is not None else step.value
        request = {
            "action": action.model_dump(exclude_none=True),
            "value": value,
            "policy_decision": decisions[index],
        }
        evidence: dict[str, Any] = {
            "operation": operation,
            "coverage": "environment_pack_v1",
            "sensitivity": action.sensitivity,
        }
        if action.resource:
            evidence["resource"] = action.resource
        if action.host:
            evidence["host"] = action.host
        response: dict[str, Any]
        if decisions[index] != "allowed":
            response = {"state": decisions[index], "value": None}
        elif step.from_step is not None and value is None:
            response = {"state": "dependency_unavailable", "value": None}
        elif operation in {"clock", "rng", "model_call", "process_exec"}:
            if input_response is not None:
                response = input_response(index, operation)
                if (
                    set(response) != {"state", "value"}
                    or response["state"] != "recorded_input"
                    or not isinstance(response["value"], str)
                ):
                    raise ReplayMiss("invalid recorded nondeterministic input")
            else:
                observed = (
                    str(time.time_ns() if pack.seed is None else 1_000_000 + index)
                    if operation == "clock"
                    else str(
                        secrets.randbelow(2**31)
                        if pack.seed is None
                        else random.Random(pack.seed + index).randrange(2**31)
                    )
                    if operation == "rng"
                    else value or "fixed-pack-stub-v1"
                )
                response = {"state": "recorded_input", "value": observed}
        elif operation == "read_file":
            path = world / str(action.resource)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    data = source.read(8193)
            finally:
                os.close(descriptor)
            if len(data) > 8192:
                raise ValueError("pack read exceeds byte budget")
            response = {"state": "read", "value": data.decode()}
        else:
            before = capture_workspace(world, store).manifest_digest
            emit(
                f"intent-{index}",
                request,
                {"state": "prepared", "before": before},
                {"operation": "effect_intent", "coverage": "environment_pack_v1"},
            )
            path = world / str(action.resource)
            if operation == "delete_file":
                path.unlink(missing_ok=True)
            else:
                descriptor = os.open(
                    path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
                )
                try:
                    with os.fdopen(descriptor, "wb", closefd=False) as destination:
                        destination.write((value or "").encode())
                        destination.flush()
                        os.fsync(destination.fileno())
                finally:
                    os.close(descriptor)
            directory = os.open(world, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            response = {
                "state": "materialized",
                "value": value,
                "after": capture_workspace(world, store).manifest_digest,
            }
            effects += 1
        observed_value = response.get("value")
        if (
            isinstance(observed_value, str)
            and (operation == "read_file" or step.from_step is not None)
            and response["state"] not in {"denied", "confirmation_required"}
        ):
            evidence["carrier"] = hmac.new(
                provenance_key, observed_value.encode(), hashlib.sha256
            ).hexdigest()
            evidence["carrier_role"] = "source" if operation == "read_file" else "sink"
        result_steps[str(index)] = emit(f"action-{index}", request, response, evidence)
        values[index] = observed_value if isinstance(observed_value, str) else None
    return {"effects": effects, "unsupported_steps": unknown, "result_steps": result_steps}


def record_pack(
    pack: Pack,
    destination: Path,
    policy: Policy,
    *,
    decisions: list[Decision] | None = None,
    decision_source: str = "test_fixture",
    extra_checkpoint_digests: dict[str, str] | None = None,
    signing_key: Path | None = None,
    anchor_root: Path | None = None,
    anchor_every: int = 1000,
) -> dict[str, Any]:
    if (signing_key is None) != (anchor_root is None) or not 100 <= anchor_every <= 50000:
        raise ValueError(
            "signer and protected anchor root must be supplied together; interval100..50000"
        )
    extras = dict(extra_checkpoint_digests or {})
    if set(extras) - {"sqlite", "git"} or any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None for value in extras.values()
    ):
        raise ValueError("unknown or malformed extra checkpoint identity")
    if decisions is None:
        decisions = evaluate_batch(policy, [step.action for step in pack.steps])
        decision_source = "real_opa_batch"
    if len(decisions) != len(pack.steps) or any(
        value not in ("allowed", "denied", "confirmation_required") for value in decisions
    ):
        raise ValueError("missing or invalid policy decisions")
    if (
        len(pack.steps)
        + sum(
            step.action.operation in _EFFECTS and decision == "allowed"
            for step, decision in zip(pack.steps, decisions, strict=True)
        )
        > 50000
    ):
        raise ValueError("pack including effect intents exceeds the50000-boundary budget")
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    seed = destination / "seed"
    seed.mkdir()
    for name, value in pack.files.items():
        (seed / name).write_text(value)
    store = FileEvidenceStore(destination / "blobs")
    provenance_key = secrets.token_bytes(32)
    key_ref = store.put(provenance_key)
    initial = capture_workspace(seed, store)
    world = destination / "world"
    restore_workspace(initial, world, store)
    if not verify_workspace(initial, world):
        raise ValueError("initial pack restore failed")
    definition: dict[str, Any] = {
        "schema_version": 2,
        "replay_contract": "finite-pack/1",
        "recording_id": secrets.token_hex(16),
        "provenance_key": {"digest": key_ref.digest, "size": key_ref.size},
        "pack": pack.model_dump(),
        "policy": policy.model_dump(),
        "policy_digest": policy_digest(policy),
        "decisions": decisions,
        "decision_source": decision_source,
        "action_digests": [event_digest(step.action.model_dump()) for step in pack.steps],
        "adapter_digest": blob_digest(Path(__file__).read_bytes()),
        "runtime_digests": _runtime_digests(),
        "python_major_minor": list(sys.version_info[:2]),
        "extra_checkpoint_digests": extras,
        "checkpoint": initial.model_dump(),
    }
    definition["definition_digest"] = event_digest(definition)
    _write_json(destination / "definition.json", definition)
    run_id = "pack-" + definition["definition_digest"][7:]
    anchors = (
        ProgressAnchors(signing_key, anchor_root / run_id, world)
        if signing_key is not None and anchor_root is not None
        else None
    )
    sequence = 0
    telemetry = RecordingTelemetry()
    started = time.perf_counter()
    with telemetry, Journal(destination / "journal.jsonl").writer() as writer:
        if anchors:
            anchors.checkpoint(destination / "journal.jsonl", run_id, 0)

        def emit(
            call_id: str,
            request: dict[str, Any],
            response: dict[str, Any],
            evidence: dict[str, Any],
        ) -> int:
            nonlocal sequence
            digest = event_digest(request)
            with telemetry.boundary(call_id, digest, evidence.get("depends_on")):
                writer.append(
                    {
                        "sequence": sequence,
                        "kind": "tool",
                        "call_id": call_id,
                        "request": request,
                        "request_digest": digest,
                        "response": response,
                        "evidence": evidence,
                    }
                )
            sequence += 1
            if anchors and sequence % anchor_every == 0:
                anchors.checkpoint(destination / "journal.jsonl", run_id, sequence)
            return sequence - 1

        outcome = _run(pack, world, store, decisions, emit, provenance_key)
        if anchors:
            anchors.checkpoint(destination / "journal.jsonl", run_id, sequence)
        sealed = writer.verification
        if sealed is None or sealed.records != sequence:
            raise ValueError("recording writer has no complete durable root")
    progress_proof = None
    if anchors:
        ledger = anchors.path.read_bytes()
        (destination / "progress-anchors.jsonl").write_bytes(ledger)
        (destination / "progress-signing.pub").write_bytes(next(iter(anchors.keys.values())))
        progress_proof = verify_progress(
            ledger,
            (destination / "journal.jsonl").read_bytes(),
            run_id,
            anchors.keys,
            expected_head=Journal(anchors.path).verify().root,
        )
    telemetry.finish(destination / "telemetry.otlp.json")
    telemetry_merge = merge_telemetry(
        destination / "journal.jsonl",
        (destination / "telemetry.otlp.json").read_bytes(),
        expected_root=sealed.root,
    )
    if telemetry_merge["journal_records"] != sequence:
        raise ValueError("persisted recording count differs from its durable writer")
    _write_json(destination / "telemetry-merge.json", telemetry_merge)
    final = capture_workspace(world, store)
    report = {
        "schema_version": 1,
        "name": pack.name,
        "mode": "DETERMINISTIC_SIMULATION" if pack.seed is not None else "EXPLORATORY_BRANCH",
        "status": "unknown" if outcome["unsupported_steps"] else "completed",
        "definition_digest": definition["definition_digest"],
        "journal_root": telemetry_merge["journal_root"],
        "records": sequence,
        "progress_anchors": progress_proof,
        "program_steps": len(pack.steps),
        "outcome": outcome,
        "final_manifest": final.model_dump(),
        "elapsed_seconds": f"{time.perf_counter() - started:.9f}",
        "limitation": (
            "Trusted finite synthetic pack; HTTP/process/model are local "
            "simulations/stubs. No live agent or real network replay."
        ),
    }
    report["report_digest"] = event_digest(report)
    _write_json(destination / "report.json", report)
    return report


def replay_pack(
    source: Path,
    destination: Path,
    *,
    through: int | None = None,
    extra_restore: Callable[[Path, dict[str, str]], dict[str, bool]] | None = None,
) -> dict[str, Any]:
    definition = load_json_unique((source / "definition.json").read_text())
    declared = definition.pop("definition_digest")
    if event_digest(definition) != declared:
        raise ReplayMiss("pack definition identity mismatch")
    compatibility = validate_replay_profile(
        definition,
        {
            "adapter_digest": blob_digest(Path(__file__).read_bytes()),
            "runtime_digests": _runtime_digests(),
            "python_major_minor": list(sys.version_info[:2]),
        },
    )
    if (
        not isinstance(definition.get("recording_id"), str)
        or re.fullmatch(r"[0-9a-f]{32}", definition["recording_id"]) is None
    ):
        raise ReplayMiss("pack recording instance identity is invalid")
    report = load_json_unique((source / "report.json").read_text())
    report_digest = report.pop("report_digest")
    if event_digest(report) != report_digest or report["definition_digest"] != declared:
        raise ReplayMiss("pack report binding mismatch")
    if report["status"] != "completed":
        raise ValueError("unsupported or incomplete pack execution cannot be replayed")
    events, verified = Journal(source / "journal.jsonl").read_verified()
    if verified.root != report["journal_root"] or verified.records != report["records"]:
        raise ReplayMiss("recorded pack journal differs from sealed report")
    pack = Pack.model_validate(definition["pack"])
    complete = through is None or through == len(pack.steps)
    count = len(pack.steps) if through is None else through
    if not 0 <= count <= len(pack.steps):
        raise ValueError("prefix boundary outside program")
    policy = Policy.model_validate(definition["policy"])
    if (
        policy_digest(policy) != definition["policy_digest"]
        or [event_digest(step.action.model_dump()) for step in pack.steps]
        != definition["action_digests"]
    ):
        raise ReplayMiss("pack policy or proposed actions differ")
    decisions = definition["decisions"]
    if len(decisions) != len(pack.steps) or any(
        value not in ("allowed", "denied", "confirmation_required") for value in decisions
    ):
        raise ReplayMiss("invalid recorded policy decisions")
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    extras = definition.get("extra_checkpoint_digests", {})
    if not isinstance(extras, dict) or set(extras) - {"sqlite", "git"}:
        raise ReplayMiss("unsupported checkpoint adapter inventory")
    restored_extras = extra_restore(destination, extras) if extra_restore else {}
    if set(restored_extras) != set(extras) or any(
        value is not True for value in restored_extras.values()
    ):
        raise ReplayMiss("declared extra checkpoint was not restored and verified")
    original_store = FileEvidenceStore(source / "blobs")
    provenance_key = original_store.get(BlobRef(**definition["provenance_key"]))
    if len(provenance_key) != 32:
        raise ReplayMiss("invalid recorded provenance key")
    store = FileEvidenceStore(destination / "blobs")
    initial = WorkspaceManifest.model_validate(definition["checkpoint"])
    for entry in initial.entries:
        store.put(original_store.get(BlobRef(entry.digest, entry.size)))
    world = destination / "world"
    restore_workspace(initial, world, store)
    if not verify_workspace(initial, world):
        raise ReplayMiss("pack checkpoint restoration differs")
    cursor = 0

    def emit(
        call_id: str, request: dict[str, Any], response: dict[str, Any], evidence: dict[str, Any]
    ) -> int:
        nonlocal cursor
        expected = {
            "sequence": cursor,
            "kind": "tool",
            "call_id": call_id,
            "request": request,
            "request_digest": event_digest(request),
            "response": response,
            "evidence": evidence,
        }
        if cursor >= len(events) or event_digest(events[cursor]) != event_digest(expected):
            raise ReplayMiss(f"pack recording mismatch at boundary {cursor}")
        cursor += 1
        return cursor - 1

    def recorded_input(index: int, operation: str) -> dict[str, Any]:
        if cursor >= len(events):
            raise ReplayMiss("missing recorded nondeterministic input")
        event = events[cursor]
        if not isinstance(event, dict) or event.get("call_id") != f"action-{index}":
            raise ReplayMiss("missing recorded nondeterministic input")
        value = event["response"]
        if not isinstance(value, dict):
            raise ReplayMiss("invalid recorded input response")
        return value

    selected_pack = pack.model_copy(update={"steps": pack.steps[:count]})
    outcome = (
        _run(selected_pack, world, store, decisions[:count], emit, provenance_key, recorded_input)
        if count
        else {"effects": 0, "unsupported_steps": [], "result_steps": {}}
    )
    expected_records = (
        len(events)
        if complete
        else (report["outcome"]["result_steps"][str(count - 1)] + 1 if count else 0)
    )
    if cursor != expected_records or (complete and outcome != report["outcome"]):
        raise ReplayMiss("pack replay left unused boundaries or changed outcomes")
    final = capture_workspace(world, store)
    expected_state = initial.manifest_digest
    for item in events[:cursor]:
        if (
            isinstance(item, dict)
            and isinstance(item.get("response"), dict)
            and item["response"].get("state") == "materialized"
        ):
            expected_state = item["response"]["after"]
    if final.manifest_digest != expected_state or (
        complete and final.model_dump(mode="json") != report["final_manifest"]
    ):
        raise ReplayMiss("pack final effect state differs")
    result = {
        "mode": "VERIFIED_REPLAY",
        "compatibility": compatibility,
        "coverage": "environment_pack_v1_regular_files_and_simulated_effects",
        "definition_digest": declared,
        "journal_root": verified.root,
        "matched": cursor,
        "through_program_steps": count,
        "complete_run": complete,
        "effects_reexecuted": outcome["effects"],
        "checkpoint_verified": True,
        "checkpoints": {"workspace": True, **restored_extras},
        "final_state_verified": True,
        "live_nondeterministic_calls": 0,
        "limitation": (
            "Only this finite pack's declared world; not native agent, "
            "real HTTP, process, Git or database replay."
        ),
    }
    _write_json(destination / "replay.json", result)
    return result
