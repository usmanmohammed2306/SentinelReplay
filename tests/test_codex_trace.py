import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.codex_trace import CodexTraceError, summarize_codex_trace


def _write_trace(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def test_codex_trace_observation_is_bounded_and_metadata_only(tmp_path: Path) -> None:
    path = tmp_path / "codex.jsonl"
    _write_trace(
        path,
        [
            {"type": "thread.started", "thread_id": "synthetic"},
            {
                "type": "item.started",
                "item": {"type": "command_execution", "command": "echo PRIVATE_SYNTHETIC_VALUE"},
            },
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "output": "PRIVATE_SYNTHETIC_VALUE"},
            },
            {"type": "item.completed", "item": {"type": "file_change", "path": "toy.py"}},
            {"type": "turn.completed", "usage": {"output_tokens": 10}},
        ],
    )
    summary = summarize_codex_trace(path)
    assert summary.mode == "AGENT_OBSERVATION_ONLY"
    assert summary.replay_coverage == "unsupported"
    assert (summary.events, summary.commands_started, summary.commands_completed) == (5, 1, 1)
    assert summary.file_changes_completed == 1
    assert summary.turn_status == "completed"
    assert "PRIVATE_SYNTHETIC_VALUE" not in str(summary.to_dict())
    output = tmp_path / "summary.json"
    result = CliRunner().invoke(app, ["codex", "inspect", str(path), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "AGENT_OBSERVATION_ONLY" in result.output
    assert "PRIVATE_SYNTHETIC_VALUE" not in output.read_text()


def test_codex_trace_rejects_duplicate_keys_and_torn_tail(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"type":"turn.completed","type":"turn.failed"}\n')
    with pytest.raises(CodexTraceError, match="duplicate key"):
        summarize_codex_trace(path)
    path.write_text('{"type":"turn.completed"}')
    with pytest.raises(CodexTraceError, match="torn tail"):
        summarize_codex_trace(path)


def test_codex_trace_refuses_symlink(tmp_path: Path) -> None:
    actual = tmp_path / "real.jsonl"
    _write_trace(actual, [{"type": "turn.completed"}])
    alias = tmp_path / "alias.jsonl"
    alias.symlink_to(actual)
    with pytest.raises(OSError):
        summarize_codex_trace(alias)
