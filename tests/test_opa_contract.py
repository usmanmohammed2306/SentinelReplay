"""Actual OPA conformance; never silently substitutes Python policy evaluation."""

import os
import subprocess
from pathlib import Path

import pytest

from sentinel_replay.policy import PolicyAction, PolicySpec, compile_rego

OPA_IMAGE = (
    "openpolicyagent/opa:1.0.0@"
    "sha256:c0609fecc0924743f8648dc4a035d2f57ca163dc723ed1d13f3197ba5bd122b3"
)


@pytest.mark.opa_integration
def test_compiled_policy_decisions_on_real_opa(tmp_path: Path) -> None:
    if os.environ.get("SENTINEL_TEST_OPA_DOCKER") != "1":
        pytest.skip("requires explicit Docker-backed OPA contract run")
    policy = PolicySpec(
        allow_tools=("http_post", "read_file"),
        deny_tools=("delete_file",),
        allow_hosts=("internal.demo.invalid",),
        deny_hosts=("demo.invalid",),
    )
    (tmp_path / "policy.rego").write_text(compile_rego(policy), encoding="utf-8")
    examples = (
        (PolicyAction(tool="read_file"), True),
        (PolicyAction(tool="http_post", host="internal.demo.invalid"), True),
        (PolicyAction(tool="http_post", host="demo.invalid"), False),
        (PolicyAction(tool="delete_file"), False),
        (PolicyAction(tool="unknown_tool"), False),
    )
    for index, (action, expected) in enumerate(examples):
        input_name = f"input-{index}.json"
        (tmp_path / input_name).write_text(
            action.model_dump_json(exclude_none=True), encoding="utf-8"
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform=linux/amd64",
                "--network=none",
                "--read-only",
                "--mount",
                f"type=bind,source={tmp_path},target=/work,readonly",
                OPA_IMAGE,
                "eval",
                "--format=raw",
                "--data=/work/policy.rego",
                f"--input=/work/{input_name}",
                "data.sentinel.policy.allow",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, (action, result.stderr)
        assert result.stdout == f"{str(expected).lower()}\n"
