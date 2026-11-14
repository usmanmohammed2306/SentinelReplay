"""Correlate isolated actions, derive declared provenance and package their proof.

No native-Python dataflow is inferred. Only gateway source intents and verified
materialized receipts can produce a source-to-effect carrier edge.
"""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from sentinel_replay.boundary import BoundarySession
from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.capsule import export_capsule, import_capsule, verify_imported
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.gateway_audit import audit_gateway_journal
from sentinel_replay.journal import Journal
from sentinel_replay.policy import PolicySpec, policy_source_digest
from sentinel_replay.provenance import build_provenance
from sentinel_replay.workspace_snapshot import (
    WorkspaceManifest,
    restore_workspace,
    verify_workspace,
)


def package_branch(controller: Path) -> dict[str, Any]:
    """Verify cross-stream bindings before deriving a portable investigation."""
    report = load_json_unique((controller / "report.json").read_text())
    protocol, protocol_verified = Journal(controller / "protocol.jsonl").read_verified()
    if report["protocol_root"] != protocol_verified.root:
        raise ValueError("branch report does not match protocol root")
    policy = PolicySpec.model_validate_json((controller / "policy.json").read_text())
    gateway_path = controller / "gateway.jsonl"
    audit = audit_gateway_journal(gateway_path, expected_policy_digest=policy_source_digest(policy))
    if audit.journal_root != report["gateway_audit"]["journal_root"]:
        raise ValueError("branch report does not match gateway root")
    gateway_events = Journal(gateway_path).events()
    requests: dict[str, list[dict[str, Any]]] = {}
    for event in gateway_events:
        if not isinstance(event, dict):
            raise ValueError("invalid gateway event")
        requests.setdefault(event["request_id"], []).append(event)
    completed = {
        row["request_id"]
        for row in report["reconciliation"]["requests"]
        if row["outcome"] == "completed_verified"
    }
    actions: dict[int, dict[str, Any]] = {}
    seen: set[str] = set()
    boundaries: list[dict[str, Any]] = []
    secret_roots: list[int] = []
    # Synthetic digest-keyed markers link verified copy receipts without payloads.
    # This is a demonstration fingerprint, not production confidential provenance.
    key = b"sentinel-branch-synthetic-provenance-v1"

    def append(call_id: str, request: object, response: object, metadata: dict[str, Any]) -> None:
        boundaries.append(
            {
                "kind": "tool",
                "call_id": call_id,
                "sequence": len(boundaries),
                "request": request,
                "request_digest": event_digest(request),
                "response": response,
                "evidence": metadata,
            }
        )

    for event in protocol:
        if not isinstance(event, dict):
            raise ValueError("invalid protocol event")
        step = event.get("step")
        if type(step) is not int:
            raise ValueError("invalid protocol step")
        if event["kind"] == "model_exchange":
            if step != len(actions):
                raise ValueError("model step sequence mismatch")
            action = event["action"]
            actions[step] = action
            if action["tool"] in {"python", "read_file", "write_file"}:
                append(
                    f"native-{step}",
                    {"action_digest": event_digest(action)},
                    {"coverage": "not_semantically_intercepted"},
                    {
                        "operation": "native_" + action["tool"],
                        "coverage": "workspace_container_only",
                    },
                )
        elif event["kind"] == "gateway_exchange":
            action = actions.get(step)
            if (
                action is None
                or action.get("tool") != "copy_named"
                or event["action_digest"] != event_digest(action)
            ):
                raise ValueError("gateway/model action correlation mismatch")
            request_id = event["result"]["request_id"]
            if request_id in seen or request_id not in requests:
                raise ValueError("orphan or repeated gateway exchange")
            seen.add(request_id)
            events = requests[request_id]
            proposal = events[0]
            if any(
                proposal[field] != action[field] for field in ("source_alias", "destination_name")
            ):
                raise ValueError("gateway source/destination differs from model action")
            terminal = events[-1]
            if terminal["state"] != event["result"]["state"]:
                raise ValueError("gateway terminal state differs from protocol")
            for field in ("digest", "bytes"):
                if field in terminal and event["result"].get(field) != terminal[field]:
                    raise ValueError("gateway receipt differs from protocol")
            intent = next((row for row in events if row["kind"] == "gateway_effect_intent"), None)
            if intent is None:
                append(
                    request_id,
                    action,
                    {"state": terminal["state"]},
                    {"operation": "copy_proposal", "coverage": "policy_gateway"},
                )
                continue
            carrier = hmac.new(key, intent["digest"].encode(), hashlib.sha256).hexdigest()
            read_id = request_id + "-source"
            if proposal["tool"] == "copy_secret":
                secret_roots.append(len(boundaries))
            append(
                read_id,
                {"source_alias": proposal["source_alias"]},
                {"bytes": intent["bytes"], "digest": intent["digest"]},
                {
                    "operation": "read_file",
                    "sensitivity": "secret" if proposal["tool"] == "copy_secret" else "public",
                    "carrier": carrier,
                    "carrier_role": "source",
                },
            )
            if request_id in completed:
                append(
                    request_id + "-effect",
                    {"destination_name": proposal["destination_name"]},
                    {"state": "completed", "digest": terminal["digest"]},
                    {
                        "operation": "copy_effect",
                        "carrier": carrier,
                        "carrier_role": "sink",
                        "depends_on": read_id,
                    },
                )
        else:
            raise ValueError("unsupported protocol event")
    if seen != set(requests):
        raise ValueError("uncorrelated gateway requests remain")
    normalized = controller / "boundaries.jsonl"
    Journal(normalized).append_many(boundaries)
    replay = BoundarySession.replay(normalized)
    for event in boundaries:
        replay.call(event["kind"], event["call_id"], event["request"], evidence=event["evidence"])
    replay.assert_complete()
    graph = build_provenance(normalized, secret_roots[0] if secret_roots else 0)
    (controller / "provenance.json").write_text(
        json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    artifacts = {
        name: controller / name
        for name in (
            "report.json",
            "policy.json",
            "protocol.jsonl",
            "gateway.jsonl",
            "workspace-manifest.json",
            "fixture-manifest.json",
            "provenance.json",
        )
    }
    for blob in sorted((controller / "blobs" / "sha256").glob("*/*")):
        artifacts["blob-" + blob.name] = blob
    capsule = controller / "branch.sentinel"
    run_id = "branch-" + Journal(normalized).verify().root.removeprefix("sha256:")
    exported = export_capsule(run_id, normalized, capsule, artifacts)
    imported = controller / "imported"
    import_capsule(capsule, imported)
    verified = verify_imported(imported)
    if exported.root != verified.root:
        raise ValueError("capsule root changed during round trip")
    imported_session = BoundarySession.replay(imported / "journal.jsonl")
    for event in boundaries:
        imported_session.call(
            event["kind"], event["call_id"], event["request"], evidence=event["evidence"]
        )
    imported_session.assert_complete()
    imported_store = FileEvidenceStore(controller / "imported-blobs")
    for blob in sorted((imported / "artifacts").glob("blob-*")):
        ref = imported_store.put(blob.read_bytes())
        if ref.digest != "sha256:" + blob.name.removeprefix("blob-"):
            raise ValueError("imported blob identity mismatch")
    restored_states: dict[str, bool] = {}
    for name in ("workspace", "fixture"):
        manifest = WorkspaceManifest.model_validate_json(
            (imported / "artifacts" / f"{name}-manifest.json").read_text()
        )
        restored = controller / f"imported-restored-{name}"
        restore_workspace(manifest, restored, imported_store)
        restored_states[name] = verify_workspace(manifest, restored)
    result = {
        "correlated_gateway_requests": len(seen),
        "native_actions_not_semantically_intercepted": report["native_actions"],
        "boundary_records": len(boundaries),
        "normalized_root": exported.root,
        "boundary_replay": "BOUNDARY_REPLAY_MATCHED",
        "capsule_import_boundary_replay": "BOUNDARY_REPLAY_MATCHED",
        "capsule_import_checkpoint_restore": restored_states,
        "provenance": graph.to_dict(),
        "limitation": (
            "Derived declared graph; no native dataflow or independent provenance F1. "
            "Capsule integrity and boundary matching do not establish authenticated "
            "author/freshness or restored-effect VERIFIED_REPLAY."
        ),
    }
    (controller / "investigation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result
