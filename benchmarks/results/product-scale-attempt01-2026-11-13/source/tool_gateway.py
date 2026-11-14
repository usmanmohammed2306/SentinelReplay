"""Narrow, fail-closed effect gateway for explicitly routed agent tool calls.

Only named source files and a bounded outbox copy are covered. This does not
intercept an agent's native shell, network, or other tools.
"""

import os
import re
import stat
import uuid
from pathlib import Path

from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import Journal
from sentinel_replay.policy import (
    PolicyAction,
    PolicyDenied,
    PolicyEvaluator,
    PolicySpec,
    PolicyUnavailable,
    policy_source_digest,
)

MAX_COPY_BYTES = 64 * 1024
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")


class GatewayError(ValueError):
    """A malformed request or unsafe covered filesystem condition."""


class ToolGateway:
    """Serialize policy decisions and effects behind a durable journal writer."""

    def __init__(
        self,
        *,
        root: Path,
        journal_path: Path,
        source_tools: dict[str, str],
        policy: PolicySpec,
        evaluator: PolicyEvaluator,
    ) -> None:
        if not source_tools or any(
            _NAME.fullmatch(name) is None or PolicyAction(tool=tool).tool != tool
            for name, tool in source_tools.items()
        ):
            raise GatewayError("source aliases and tool classifications must be valid")
        if journal_path.is_relative_to(root):
            raise GatewayError("journal must be outside the agent-visible fixture root")
        self.root = root
        self.journal = Journal(journal_path)
        self.source_tools = dict(source_tools)
        self.policy = policy
        self.evaluator = evaluator

    def copy_named(self, source_alias: str, destination_name: str) -> dict[str, object]:
        """Check OPA before effect; record intent and decision durably first.

        An allowed decision with no terminal result means outcome unknown after a
        crash. Never infer that the copy succeeded from the decision alone.
        """
        if source_alias not in self.source_tools or _NAME.fullmatch(destination_name) is None:
            raise GatewayError("source alias or destination name is not allowed")
        if destination_name in {".", ".."}:
            raise GatewayError("invalid destination name")
        action = PolicyAction(tool=self.source_tools[source_alias])
        request_id = uuid.uuid4().hex
        request = {
            "request_id": request_id,
            "source_alias": source_alias,
            "destination_name": destination_name,
            "tool": action.tool,
            "policy_digest": policy_source_digest(self.policy),
        }
        with self.journal.writer() as writer:
            writer.append({"kind": "gateway_proposal", **request})
            try:
                allowed = self.evaluator.evaluate(self.policy, action)
                if type(allowed) is not bool:
                    raise PolicyUnavailable("policy evaluator did not return a boolean")
            except Exception:
                writer.append(
                    {"kind": "gateway_decision", "request_id": request_id, "state": "unavailable"}
                )
                raise
            writer.append(
                {
                    "kind": "gateway_decision",
                    "request_id": request_id,
                    "state": "allowed" if allowed else "denied",
                }
            )
            if not allowed:
                raise PolicyDenied("policy denied proposed action")
            try:
                data = self._read_source(source_alias)
                receipt = {"state": "completed", "bytes": len(data), "digest": blob_digest(data)}
                writer.append(
                    {
                        "kind": "gateway_effect_intent",
                        "request_id": request_id,
                        "bytes": receipt["bytes"],
                        "digest": receipt["digest"],
                    }
                )
                self._write_destination(destination_name, data)
            except Exception:
                writer.append(
                    {
                        "kind": "gateway_result",
                        "request_id": request_id,
                        "state": "failed_or_unknown",
                    }
                )
                raise
            writer.append({"kind": "gateway_result", "request_id": request_id, **receipt})
            return {"request_id": request_id, **receipt}

    def _read_source(self, source_alias: str) -> bytes:
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            source_dir_fd = os.open(
                "sources", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            try:
                source_fd = os.open(source_alias, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_dir_fd)
                try:
                    source_stat = os.fstat(source_fd)
                    if (
                        not stat.S_ISREG(source_stat.st_mode)
                        or source_stat.st_size > MAX_COPY_BYTES
                    ):
                        raise GatewayError("source is not a bounded regular file")
                    with os.fdopen(source_fd, "rb", closefd=False) as source:
                        data = source.read(MAX_COPY_BYTES + 1)
                    source_after = os.fstat(source_fd)
                    if (
                        len(data) != source_stat.st_size
                        or len(data) > MAX_COPY_BYTES
                        or (source_stat.st_dev, source_stat.st_ino, source_stat.st_mtime_ns)
                        != (source_after.st_dev, source_after.st_ino, source_after.st_mtime_ns)
                    ):
                        raise GatewayError("source changed during bounded read")
                finally:
                    os.close(source_fd)
            finally:
                os.close(source_dir_fd)
        finally:
            os.close(root_fd)
        return data

    def _write_destination(self, destination_name: str, data: bytes) -> None:
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            outbox_fd = os.open(
                "outbox", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            try:
                output_fd = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=outbox_fd,
                )
                with os.fdopen(output_fd, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.fsync(outbox_fd)
            finally:
                os.close(outbox_fd)
        finally:
            os.close(root_fd)
