"""Bounded observation of Codex CLI JSONL; never a replay recording.

The CLI event stream can reveal actions but does not intercept all inputs,
outputs, state mutations, or effects. Its only valid mode here is observation.
"""

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

MAX_CODEX_TRACE_BYTES = 32 * 1024 * 1024
MAX_CODEX_TRACE_EVENTS = 100_000
MAX_CODEX_TRACE_LINE_BYTES = 1024 * 1024
_TYPE = re.compile(r"[a-z][a-z0-9_.]{0,63}\Z")


class CodexTraceError(ValueError):
    """The Codex event stream is malformed or exceeds an observation bound."""


@dataclass(frozen=True)
class CodexObservation:
    mode: Literal["AGENT_OBSERVATION_ONLY"]
    trace_digest: str
    events: int
    commands_started: int
    commands_completed: int
    file_changes_completed: int
    other_item_events: int
    other_events: int
    turn_status: Literal["completed", "failed", "incomplete"]
    replay_coverage: Literal["unsupported"]
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CodexTraceError("duplicate key in Codex event")
        result[key] = value
    return result


def summarize_codex_trace(path: Path) -> CodexObservation:
    """Summarize only safe metadata from an exact, bounded JSONL file."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CodexTraceError("Codex trace must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read(MAX_CODEX_TRACE_BYTES + 1)
    finally:
        os.close(descriptor)
    if not data or len(data) > MAX_CODEX_TRACE_BYTES or not data.endswith(b"\n"):
        raise CodexTraceError("Codex trace is empty, oversized, or has a torn tail")
    counts = {
        "commands_started": 0,
        "commands_completed": 0,
        "file_changes_completed": 0,
        "other_item_events": 0,
        "other_events": 0,
    }
    status: Literal["completed", "failed", "incomplete"] = "incomplete"
    lines = data.splitlines()
    if len(lines) > MAX_CODEX_TRACE_EVENTS:
        raise CodexTraceError("Codex trace exceeds event limit")
    for index, raw_line in enumerate(lines, 1):
        if not raw_line or len(raw_line) > MAX_CODEX_TRACE_LINE_BYTES:
            raise CodexTraceError(f"Codex event {index} is empty or oversized")
        try:
            event = json.loads(raw_line.decode("utf-8"), object_pairs_hook=_unique_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CodexTraceError(f"Codex event {index} is not valid JSON") from error
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise CodexTraceError(f"Codex event {index} lacks a type")
        kind = event["type"]
        if _TYPE.fullmatch(kind) is None:
            raise CodexTraceError(f"Codex event {index} has an invalid type")
        if kind in {"turn.completed", "turn.failed"}:
            status = "completed" if kind == "turn.completed" else "failed"
        if kind in {"item.started", "item.completed"}:
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise CodexTraceError(f"Codex item event {index} lacks an item type")
            item_type = item["type"]
            if _TYPE.fullmatch(item_type) is None:
                raise CodexTraceError(f"Codex item event {index} has an invalid item type")
            if item_type == "command_execution":
                field = "commands_started" if kind == "item.started" else "commands_completed"
                counts[field] += 1
            elif item_type == "file_change" and kind == "item.completed":
                counts["file_changes_completed"] += 1
            else:
                counts["other_item_events"] += 1
        else:
            counts["other_events"] += 1
    return CodexObservation(
        mode="AGENT_OBSERVATION_ONLY",
        trace_digest="sha256:" + hashlib.sha256(data).hexdigest(),
        events=len(lines),
        **counts,
        turn_status=status,
        replay_coverage="unsupported",
        limitation=(
            "Codex JSONL events alone are observations, not intercepted model/tool "
            "boundaries or effect receipts. They do not prove state restoration or "
            "fail-closed replay."
        ),
    )
