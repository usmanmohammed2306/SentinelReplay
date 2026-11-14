"""Semantic audit of the bounded gateway's already hash-verified journal."""

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sentinel_replay.journal import Journal
from sentinel_replay.tool_gateway import MAX_COPY_BYTES

MAX_AUDIT_EVENTS = 150_000
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
_TOOL = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class GatewayAuditError(ValueError):
    """A chained gateway event sequence violates the declared transaction grammar."""


@dataclass(frozen=True)
class GatewayAudit:
    journal_root: str
    journal_records: int
    requests: int
    completed: int
    denied: int
    unavailable: int
    failed_or_unknown: int
    interrupted_unknown: int
    coverage: Literal["copy_named_mcp_tool_only"] = "copy_named_mcp_tool_only"
    replay_coverage: Literal["unsupported"] = "unsupported"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _string(value: object, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise GatewayAuditError(f"invalid {label}")
    return value


def audit_gateway_journal(path: Path, *, expected_policy_digest: str | None = None) -> GatewayAudit:
    """Verify chain and transaction grammar; never infer effects from allow alone."""
    if expected_policy_digest is not None:
        _string(expected_policy_digest, _DIGEST, "expected policy digest")
    seen: set[str] = set()
    counts = {
        "completed": 0,
        "denied": 0,
        "unavailable": 0,
        "failed_or_unknown": 0,
        "interrupted_unknown": 0,
    }
    active_id: str | None = None
    phase: str | None = None
    active_intent: tuple[int, str] | None = None
    observed_policy_digest: str | None = None

    def finish_active() -> None:
        nonlocal active_id, phase, active_intent
        if active_id is None or phase is None:
            return
        if phase in {"proposal", "allowed", "intent"}:
            counts["interrupted_unknown"] += 1
        else:
            counts[phase] += 1
        active_id = None
        phase = None
        active_intent = None

    def visit(index: int, event: object) -> None:
        nonlocal active_id, phase, active_intent, observed_policy_digest
        if index >= MAX_AUDIT_EVENTS:
            raise GatewayAuditError("gateway audit exceeds event limit")
        if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
            raise GatewayAuditError(f"event {index}: invalid gateway event")
        kind = event["kind"]
        request_id = _string(event.get("request_id"), _REQUEST_ID, "request ID")
        if kind == "gateway_proposal":
            if set(event) != {
                "kind",
                "request_id",
                "source_alias",
                "destination_name",
                "tool",
                "policy_digest",
            }:
                raise GatewayAuditError("invalid proposal shape")
            _string(event["source_alias"], _NAME, "source alias")
            _string(event["destination_name"], _NAME, "destination name")
            _string(event["tool"], _TOOL, "tool")
            digest = _string(event["policy_digest"], _DIGEST, "policy digest")
            if expected_policy_digest is not None and digest != expected_policy_digest:
                raise GatewayAuditError("proposal policy digest mismatch")
            if observed_policy_digest is not None and digest != observed_policy_digest:
                raise GatewayAuditError("gateway journal mixes policy digests")
            observed_policy_digest = digest
            if request_id in seen:
                raise GatewayAuditError("duplicate gateway request ID")
            finish_active()
            seen.add(request_id)
            active_id, phase = request_id, "proposal"
        elif kind == "gateway_decision":
            if set(event) != {"kind", "request_id", "state"}:
                raise GatewayAuditError("invalid decision shape")
            if active_id != request_id or phase != "proposal":
                raise GatewayAuditError("decision without matching proposal")
            state = event["state"]
            if not isinstance(state, str) or state not in {"allowed", "denied", "unavailable"}:
                raise GatewayAuditError("invalid decision state")
            phase = state
        elif kind == "gateway_effect_intent":
            if set(event) != {"kind", "request_id", "bytes", "digest"}:
                raise GatewayAuditError("invalid effect intent shape")
            if active_id != request_id or phase != "allowed":
                raise GatewayAuditError("effect intent without matching allowed decision")
            if type(event["bytes"]) is not int or not 0 <= event["bytes"] <= MAX_COPY_BYTES:
                raise GatewayAuditError("invalid effect intent byte count")
            _string(event["digest"], _DIGEST, "effect intent digest")
            active_intent = (event["bytes"], event["digest"])
            phase = "intent"
        elif kind == "gateway_result":
            if active_id != request_id or phase not in {"allowed", "intent"}:
                raise GatewayAuditError("result without matching allowed decision")
            state = event.get("state")
            if state == "completed":
                if set(event) != {"kind", "request_id", "state", "bytes", "digest"}:
                    raise GatewayAuditError("invalid completed result shape")
                if type(event["bytes"]) is not int or not 0 <= event["bytes"] <= MAX_COPY_BYTES:
                    raise GatewayAuditError("invalid completed byte count")
                _string(event["digest"], _DIGEST, "result digest")
                if active_intent is not None and (event["bytes"], event["digest"]) != active_intent:
                    raise GatewayAuditError("result does not match effect intent")
            elif state == "failed_or_unknown":
                if set(event) != {"kind", "request_id", "state"}:
                    raise GatewayAuditError("invalid uncertain result shape")
            else:
                raise GatewayAuditError("invalid result state")
            phase = state
        else:
            raise GatewayAuditError("unexpected event kind in gateway journal")

    verification = Journal(path).scan_verified(visit)
    finish_active()
    return GatewayAudit(
        journal_root=verification.root,
        journal_records=verification.records,
        requests=len(seen),
        completed=counts["completed"],
        denied=counts["denied"],
        unavailable=counts["unavailable"],
        failed_or_unknown=counts["failed_or_unknown"],
        interrupted_unknown=counts["interrupted_unknown"],
    )
