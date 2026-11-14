"""Inspect materialized gateway effects after a crash without replaying them.

An allowed decision is not an effect receipt. A digest-bound intent lets us
recognize a completed file copy even if the process died before writing the
result record. This only covers the named-file outbox adapter.
"""

import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.gateway_audit import audit_gateway_journal
from sentinel_replay.journal import Journal, Verification
from sentinel_replay.tool_gateway import MAX_COPY_BYTES

Outcome = Literal[
    "denied",
    "policy_unavailable",
    "unknown_no_intent",
    "missing_effect",
    "matched_effect_unrecorded",
    "matched_effect_finalized",
    "completed_verified",
    "effect_mismatch",
    "failed_or_unknown",
]


class ReconciliationError(ValueError):
    """The declared outbox cannot be inspected safely."""


@dataclass(frozen=True)
class ReconciledRequest:
    request_id: str
    outcome: Outcome


@dataclass(frozen=True)
class GatewayReconciliation:
    schema_version: int
    coverage: Literal["copy_named_mcp_tool_only"]
    journal_root: str
    journal_records: int
    requests: tuple[ReconciledRequest, ...]
    limitation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _outbox_digest(root: Path, name: str) -> tuple[int, str] | None:
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        outbox_fd = os.open("outbox", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            try:
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=outbox_fd)
            except FileNotFoundError:
                return None
            try:
                before = os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_COPY_BYTES:
                    raise ReconciliationError("outbox effect is not a bounded regular file")
                with os.fdopen(file_fd, "rb", closefd=False) as source:
                    data = source.read(MAX_COPY_BYTES + 1)
                after = os.fstat(file_fd)
                if (
                    len(data) != before.st_size
                    or len(data) > MAX_COPY_BYTES
                    or (before.st_dev, before.st_ino, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_mtime_ns)
                ):
                    raise ReconciliationError("outbox effect changed during read")
                return len(data), blob_digest(data)
            finally:
                os.close(file_fd)
        finally:
            os.close(outbox_fd)
    finally:
        os.close(root_fd)


def reconcile_gateway_effects(
    journal_path: Path, root: Path, *, finalize_matched: bool = False
) -> GatewayReconciliation:
    """Verify actual bytes and optionally finalize only matched crash-gap effects.

    Repeated finalization is idempotent: a matching result is appended once and
    the materialized file is never written by this function.
    """
    if not journal_path.exists():
        raise FileNotFoundError("gateway journal does not exist")
    with Journal(journal_path).writer() as writer:
        audit_gateway_journal(journal_path)
        events, verification = writer.read_verified()
        requests: dict[str, dict[str, object]] = {}
        order: list[str] = []
        for raw in events:
            if not isinstance(raw, dict):
                raise ReconciliationError("invalid gateway event")
            event = raw
            request_id = event["request_id"]
            if not isinstance(request_id, str):
                raise ReconciliationError("invalid gateway request ID")
            kind = event["kind"]
            if kind == "gateway_proposal":
                requests[request_id] = {"destination": event["destination_name"]}
                order.append(request_id)
            elif kind == "gateway_decision":
                requests[request_id]["decision"] = event["state"]
            elif kind == "gateway_effect_intent":
                requests[request_id]["intent"] = (event["bytes"], event["digest"])
            elif kind == "gateway_result":
                requests[request_id]["result"] = event
        outcomes: list[ReconciledRequest] = []
        for request_id in order:
            entry = requests[request_id]
            decision = entry.get("decision")
            if decision == "denied":
                outcome: Outcome = "denied"
            elif decision == "unavailable":
                outcome = "policy_unavailable"
            elif decision != "allowed" or not isinstance(entry["destination"], str):
                outcome = "unknown_no_intent"
            else:
                actual = _outbox_digest(root, entry["destination"])
                expected = entry.get("intent")
                result = entry.get("result")
                if isinstance(result, dict) and result.get("state") == "completed":
                    receipt = (result["bytes"], result["digest"])
                    outcome = "completed_verified" if actual == receipt else "effect_mismatch"
                elif isinstance(result, dict):
                    outcome = "failed_or_unknown"
                elif expected is None:
                    outcome = "unknown_no_intent"
                elif actual is None:
                    outcome = "missing_effect"
                elif actual != expected:
                    outcome = "effect_mismatch"
                elif finalize_matched:
                    bytes_count, digest = actual
                    writer.append(
                        {
                            "kind": "gateway_result",
                            "request_id": request_id,
                            "state": "completed",
                            "bytes": bytes_count,
                            "digest": digest,
                        }
                    )
                    outcome = "matched_effect_finalized"
                else:
                    outcome = "matched_effect_unrecorded"
            outcomes.append(ReconciledRequest(request_id=request_id, outcome=outcome))
        final: Verification = writer.verification or verification
        return GatewayReconciliation(
            schema_version=1,
            coverage="copy_named_mcp_tool_only",
            journal_root=final.root,
            journal_records=final.records,
            requests=tuple(outcomes),
            limitation=(
                "Point-in-time named-file inspection only; no authenticated journal author, "
                "concurrent mutation exclusion, remote-effect recovery, or general replay proof"
            ),
        )
