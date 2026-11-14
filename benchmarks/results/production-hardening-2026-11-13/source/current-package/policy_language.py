"""Versioned finite policy atoms; batched real OPA decisions, never Python enforcement.

Globs match bounded normalized metadata, not shell syntax or arbitrary Rego.
Confirmation is a terminal non-allow decision until a separate approval exists.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.policy import OPA_DOCKER_IMAGE, PolicyUnavailable

Decision = Literal["allowed", "denied", "confirmation_required"]


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    resource: str | None = Field(default=None, max_length=256)
    host: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")
    sensitivity: Literal["public", "secret", "unspecified"] = "unspecified"
    executable: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")

    @model_validator(mode="after")
    def normalized(self) -> "Action":
        if self.resource is not None and (
            not self.resource
            or self.resource.startswith("/")
            or "\\" in self.resource
            or any(part in {"", ".", ".."} for part in self.resource.split("/"))
            or "\x00" in self.resource
        ):
            raise ValueError("resource must be a normalized relative path")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    effect: Literal["allow", "deny", "confirm"]
    operation: str = Field(default="*", pattern=r"^(\*|[a-z][a-z0-9_]{0,63})$")
    resource: str | None = Field(default=None, max_length=128)
    host: str | None = Field(default=None, max_length=128)
    sensitivity: Literal["public", "secret", "unspecified"] | None = None
    executable: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def bounded_patterns(self) -> "Rule":
        for field in (self.resource, self.host, self.executable):
            if field is not None and (not field or not re.fullmatch(r"[A-Za-z0-9_.*?/-]+", field)):
                raise ValueError(
                    "patterns support only bounded literal, star and question-mark atoms"
                )
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2] = 2
    rules: tuple[Rule, ...] = Field(default=(), max_length=128)


def compile_policy(policy: Policy) -> str:
    rules = json.dumps([rule.model_dump() for rule in policy.rules], separators=(",", ":"))
    return (
        """package sentinel.v2

match_field(actual, expected) if { expected == null }
match_field(actual, expected) if {
    expected != null
    actual != null
    glob.match(expected, ["/"], actual)
}

matches(rule, action) if {
    match_field(action.operation, rule.operation)
    match_field(action.resource, rule.resource)
    match_field(action.host, rule.host)
    match_field(action.sensitivity, rule.sensitivity)
    match_field(action.executable, rule.executable)
}

has_effect(action, effect) if {
    some rule in rules
    rule.effect == effect
    matches(rule, action)
}

decision(action) := "denied" if { has_effect(action, "deny") }
else := "confirmation_required" if { has_effect(action, "confirm") }
else := "allowed" if { has_effect(action, "allow") }
else := "denied"

decisions := [decision(action) | some action in input.actions]
"""
        + "\nrules := "
        + rules
        + "\n"
    )


def policy_digest(policy: Policy) -> str:
    return blob_digest(compile_policy(policy).encode())


def evaluate_batch(
    policy: Policy, actions: list[Action], *, executable: str | None = None
) -> list[Decision]:
    if not actions or len(actions) > 50_000:
        raise ValueError("policy batch must contain 1..50000 actions")
    with tempfile.TemporaryDirectory(prefix="sentinel-policy-v2-") as directory:
        root = Path(directory)
        (root / "policy.rego").write_text(compile_policy(policy))
        encoded = json.dumps({"actions": [action.model_dump() for action in actions]})
        if len(encoded.encode()) > 16 * 1024 * 1024:
            raise ValueError("policy input exceeds byte budget")
        if executable:
            command = [
                executable,
                "eval",
                "--format=raw",
                "--stdin-input",
                "--data",
                str(root / "policy.rego"),
                "data.sentinel.v2.decisions",
            ]
        else:
            command = [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--interactive",
                "--platform=linux/amd64",
                f"--user={os.getuid()}:{os.getgid()}",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory=256m",
                "--pids-limit=64",
                "--mount",
                f"type=bind,source={root},target=/work,readonly",
                OPA_DOCKER_IMAGE,
                "eval",
                "--format=raw",
                "--stdin-input",
                "--data=/work/policy.rego",
                "data.sentinel.v2.decisions",
            ]
        try:
            result = subprocess.run(
                command, input=encoded, capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PolicyUnavailable("policy execution failed; effects must stop") from error
    if result.returncode != 0:
        raise PolicyUnavailable("OPA rejected the compiled policy or input")
    try:
        decisions = json.loads(result.stdout)
    except ValueError as error:
        raise PolicyUnavailable("OPA returned malformed decisions") from error
    if (
        not isinstance(decisions, list)
        or len(decisions) != len(actions)
        or any(value not in ("allowed", "denied", "confirmation_required") for value in decisions)
    ):
        raise PolicyUnavailable("OPA returned an incomplete or unknown decision")
    return decisions
