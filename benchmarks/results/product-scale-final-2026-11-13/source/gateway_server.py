"""Stdio MCP adapter for the explicitly covered Sentinel tool gateway."""

import argparse
import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from sentinel_replay.policy import (
    OpaDockerEvaluator,
    OpaEvaluator,
    PolicyDenied,
    PolicySpec,
    PolicyUnavailable,
)
from sentinel_replay.tool_gateway import GatewayError, ToolGateway


def create_server(gateway: ToolGateway) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer(
        "sentinel-gateway",
        instructions=(
            "Only copy_named is covered by Sentinel policy and evidence. "
            "No other agent tool is intercepted by this server."
        ),
    )

    @server.tool()
    def copy_named(source_alias: str, destination_name: str) -> dict[str, object]:
        """Copy a configured named source into the covered outbox after OPA approval."""
        try:
            return gateway.copy_named(source_alias, destination_name)
        except PolicyDenied:
            return {"state": "denied", "covered": True}
        except PolicyUnavailable:
            return {"state": "policy_unavailable", "covered": True}
        except GatewayError:
            return {"state": "invalid_or_unsafe_request", "covered": True}

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded Sentinel MCP tool gateway")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--source-tools", type=Path, required=True)
    parser.add_argument("--opa", choices=("binary", "docker"), default="binary")
    options = parser.parse_args()
    policy = PolicySpec.model_validate_json(options.policy.read_text(encoding="utf-8"))
    source_tools = json.loads(options.source_tools.read_text(encoding="utf-8"))
    if not isinstance(source_tools, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in source_tools.items()
    ):
        raise ValueError("source-tools must be a JSON string-to-string mapping")
    evaluator = OpaEvaluator() if options.opa == "binary" else OpaDockerEvaluator()
    gateway = ToolGateway(
        root=options.root,
        journal_path=options.journal,
        source_tools=source_tools,
        policy=policy,
        evaluator=evaluator,
    )
    create_server(gateway).run(transport="stdio")


if __name__ == "__main__":
    main()
