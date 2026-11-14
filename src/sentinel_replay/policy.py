"""Finite policy grammar compiled to Rego and evaluated by OPA, never Python rules.

This first enforcement boundary covers exact tool names and outbound hosts. It is
not the complete V1 grammar or a substitute for an isolated agent tool gateway.
"""

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

_TOOL_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_HOST_PATTERN = r"^[a-z0-9][a-z0-9.-]{0,252}$"


class PolicyError(ValueError):
    """An invalid policy or policy-engine failure."""


class PolicyDenied(PolicyError):
    """OPA denied an action; its effect callback was not invoked."""


class PolicyUnavailable(PolicyError):
    """OPA did not produce an unambiguous decision; fail closed."""


class PolicySpec(BaseModel):
    """Versioned, finite exact-match policy with deny precedence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    allow_tools: tuple[str, ...] = ()
    deny_tools: tuple[str, ...] = ()
    allow_hosts: tuple[str, ...] = ()
    deny_hosts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_atoms(self) -> "PolicySpec":
        import re

        for name, values, pattern in (
            ("allow_tools", self.allow_tools, _TOOL_PATTERN),
            ("deny_tools", self.deny_tools, _TOOL_PATTERN),
            ("allow_hosts", self.allow_hosts, _HOST_PATTERN),
            ("deny_hosts", self.deny_hosts, _HOST_PATTERN),
        ):
            if len(values) > 128 or tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted, unique, and contain at most 128 entries")
            if any(re.fullmatch(pattern, value) is None for value in values):
                raise ValueError(f"{name} contains an invalid exact-match atom")
        return self


class PolicyAction(BaseModel):
    """A normalized action proposed to the policy boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    tool: str = Field(pattern=_TOOL_PATTERN)
    host: str | None = Field(default=None, pattern=_HOST_PATTERN)

    @model_validator(mode="after")
    def validate_host(self) -> "PolicyAction":
        if (self.tool == "http_post") != (self.host is not None):
            raise ValueError("http_post requires a host; other tools must not supply one")
        return self


def compile_rego(policy: PolicySpec) -> str:
    """Emit Rego v1 source from validated atoms, with no caller-supplied code."""
    allowed_tools = json.dumps(policy.allow_tools, separators=(",", ":"))
    denied_tools = json.dumps(policy.deny_tools, separators=(",", ":"))
    allowed_hosts = json.dumps(policy.allow_hosts, separators=(",", ":"))
    denied_hosts = json.dumps(policy.deny_hosts, separators=(",", ":"))
    return f"""package sentinel.policy

default allow := false

tool_denied if {{
    input.tool in {denied_tools}
}}

host_denied if {{
    input.host in {denied_hosts}
}}

host_permitted if {{
    input.tool != "http_post"
}}

host_permitted if {{
    input.tool == "http_post"
    input.host in {allowed_hosts}
    not host_denied
}}

allow if {{
    input.schema_version == 1
    input.tool in {allowed_tools}
    not tool_denied
    host_permitted
}}
"""


def policy_source_digest(policy: PolicySpec) -> str:
    return "sha256:" + hashlib.sha256(compile_rego(policy).encode("utf-8")).hexdigest()


class PolicyEvaluator(Protocol):
    def evaluate(self, policy: PolicySpec, action: PolicyAction) -> bool: ...


class OpaEvaluator:
    """Execute a configured OPA binary with bounded time and exact boolean output."""

    def __init__(self, executable: str = "opa", *, timeout_seconds: float = 3.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("OPA timeout must be within (0, 30] seconds")
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def evaluate(self, policy: PolicySpec, action: PolicyAction) -> bool:
        with tempfile.TemporaryDirectory(prefix="sentinel-opa-") as directory:
            root = Path(directory)
            (root / "policy.rego").write_text(compile_rego(policy), encoding="utf-8")
            (root / "input.json").write_text(
                action.model_dump_json(exclude_none=True), encoding="utf-8"
            )
            try:
                result = subprocess.run(
                    [
                        self.executable,
                        "eval",
                        "--format=raw",
                        "--data",
                        str(root / "policy.rego"),
                        "--input",
                        str(root / "input.json"),
                        "data.sentinel.policy.allow",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise PolicyUnavailable("OPA execution failed or timed out") from error
        if result.returncode != 0 or result.stdout not in {"true\n", "false\n"}:
            raise PolicyUnavailable("OPA returned no valid boolean decision")
        return result.stdout == "true\n"


OPA_DOCKER_IMAGE = (
    "openpolicyagent/opa:1.0.0@"
    "sha256:c0609fecc0924743f8648dc4a035d2f57ca163dc723ed1d13f3197ba5bd122b3"
)


class OpaDockerEvaluator:
    """Local demo evaluator using a pinned, networkless OPA container.

    Use a native OPA binary for a deployed gateway; one container per decision
    is intentionally simple and too slow for production traffic.
    """

    def evaluate(self, policy: PolicySpec, action: PolicyAction) -> bool:
        with tempfile.TemporaryDirectory(prefix="sentinel-opa-docker-") as directory:
            root = Path(directory)
            (root / "policy.rego").write_text(compile_rego(policy), encoding="utf-8")
            (root / "input.json").write_text(
                action.model_dump_json(exclude_none=True), encoding="utf-8"
            )
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--platform=linux/amd64",
                        f"--user={os.getuid()}:{os.getgid()}",
                        "--network=none",
                        "--read-only",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--mount",
                        f"type=bind,source={root},target=/work,readonly",
                        OPA_DOCKER_IMAGE,
                        "eval",
                        "--format=raw",
                        "--data=/work/policy.rego",
                        "--input=/work/input.json",
                        "data.sentinel.policy.allow",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise PolicyUnavailable("Docker-backed OPA failed or timed out") from error
        if result.returncode != 0 or result.stdout not in {"true\n", "false\n"}:
            raise PolicyUnavailable("Docker-backed OPA returned no valid boolean decision")
        return result.stdout == "true\n"


def enforce[T](
    evaluator: PolicyEvaluator, policy: PolicySpec, action: PolicyAction, effect: Callable[[], T]
) -> T:
    """Invoke an effect only after an explicit OPA allow; all failures stop it."""
    decision = evaluator.evaluate(policy, action)
    if type(decision) is not bool:
        raise PolicyUnavailable("policy evaluator did not return a boolean")
    if not decision:
        raise PolicyDenied("policy denied proposed action")
    return effect()
