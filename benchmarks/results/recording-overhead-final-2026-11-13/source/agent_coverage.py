"""Conservative coverage accounting for a Codex trace and the narrow MCP gateway.

These two evidence streams have no shared, authenticated call identity. Matching
counts therefore cannot establish that all agent actions crossed the gateway.
"""

from dataclasses import asdict, dataclass
from typing import Literal

from sentinel_replay.codex_trace import CodexObservation
from sentinel_replay.gateway_audit import GatewayAudit


@dataclass(frozen=True)
class AgentCoverageManifest:
    schema_version: int
    mode: Literal["AGENT_OBSERVATION_ONLY"]
    codex_trace_digest: str
    gateway_journal_root: str | None
    gateway_requests: int
    observed_native_commands: int
    observed_native_file_changes: int
    unclassified_item_events: int
    action_coverage: Literal["partial", "unsupported"]
    strict_replay_eligible: Literal[False]
    gaps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_agent_coverage(
    observation: CodexObservation, gateway: GatewayAudit | None = None
) -> AgentCoverageManifest:
    """Classify observed gaps without inferring complete interception from silence."""
    native_commands = max(observation.commands_started, observation.commands_completed)
    native_files = observation.file_changes_completed
    gaps = [
        "Codex JSONL is observational and cannot prove all action boundaries were seen",
        "native shell and file-change tools are not intercepted by the MCP gateway",
        "Codex events and gateway requests lack a shared authenticated call identity",
        "model/tool nondeterminism and effect receipts are not complete for strict replay",
    ]
    if native_commands or native_files:
        gaps.append("unsupported native action observed in this trace")
    if observation.other_item_events:
        gaps.append("other item events are not individually classified as safe or covered")
    if observation.turn_status != "completed":
        gaps.append("agent turn did not complete")
    return AgentCoverageManifest(
        schema_version=1,
        mode="AGENT_OBSERVATION_ONLY",
        codex_trace_digest=observation.trace_digest,
        gateway_journal_root=gateway.journal_root if gateway else None,
        gateway_requests=gateway.requests if gateway else 0,
        observed_native_commands=native_commands,
        observed_native_file_changes=native_files,
        unclassified_item_events=observation.other_item_events,
        action_coverage="partial" if gateway and gateway.requests else "unsupported",
        strict_replay_eligible=False,
        gaps=tuple(gaps),
    )
