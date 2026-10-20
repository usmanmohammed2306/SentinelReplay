"""MCP tool-call conformance through the real SDK transport abstraction."""

import asyncio
import os
from pathlib import Path

import pytest
from mcp import Client

from sentinel_replay.gateway_server import create_server
from sentinel_replay.journal import Journal
from sentinel_replay.policy import OpaDockerEvaluator, PolicyAction, PolicySpec
from sentinel_replay.tool_gateway import ToolGateway


class DeterministicEvaluator:
    def evaluate(self, _policy: PolicySpec, action: PolicyAction) -> bool:
        return action.tool == "copy_public"


async def _exercise_mcp(tmp_path: Path, *, real_opa: bool) -> None:
    root = tmp_path / "fixtures"
    (root / "sources").mkdir(parents=True)
    (root / "outbox").mkdir()
    (root / "sources" / "public.txt").write_text("safe demo\n")
    (root / "sources" / "credential.txt").write_text("synthetic-secret\n")
    journal_path = tmp_path / "private" / "journal.jsonl"
    server = create_server(
        ToolGateway(
            root=root,
            journal_path=journal_path,
            source_tools={"public.txt": "copy_public", "credential.txt": "copy_secret"},
            policy=PolicySpec(allow_tools=("copy_public",), deny_tools=("copy_secret",)),
            evaluator=OpaDockerEvaluator() if real_opa else DeterministicEvaluator(),
        )
    )
    async with Client(server) as client:
        listing = await client.list_tools()
        assert [tool.name for tool in listing.tools] == ["copy_named"]
        denied = await client.call_tool(
            "copy_named", {"source_alias": "credential.txt", "destination_name": "leak.txt"}
        )
        assert not denied.is_error
        assert denied.structured_content == {"state": "denied", "covered": True}
        assert not (root / "outbox" / "leak.txt").exists()
        allowed = await client.call_tool(
            "copy_named", {"source_alias": "public.txt", "destination_name": "copy.txt"}
        )
        assert not allowed.is_error
        assert (root / "outbox" / "copy.txt").read_text() == "safe demo\n"
    events = Journal(journal_path).events()
    assert [
        event["state"]
        for event in events
        if isinstance(event, dict) and event.get("kind") == "gateway_decision"
    ] == [
        "denied",
        "allowed",
    ]
    assert "synthetic-secret" not in journal_path.read_text()


def test_mcp_adapter_in_memory(tmp_path: Path) -> None:
    asyncio.run(_exercise_mcp(tmp_path, real_opa=False))


@pytest.mark.opa_integration
def test_mcp_adapter_with_real_opa(tmp_path: Path) -> None:
    if os.environ.get("SENTINEL_TEST_OPA_DOCKER") != "1":
        pytest.skip("requires explicit Docker-backed OPA contract run")
    asyncio.run(_exercise_mcp(tmp_path, real_opa=True))
