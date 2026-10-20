import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from sentinel_replay.policy import (
    OpaEvaluator,
    PolicyAction,
    PolicyDenied,
    PolicySpec,
    PolicyUnavailable,
    compile_rego,
    enforce,
    policy_source_digest,
)


def _policy() -> PolicySpec:
    return PolicySpec(
        allow_tools=("http_post", "read_file"),
        deny_tools=("delete_file",),
        allow_hosts=("internal.demo.invalid",),
        deny_hosts=("demo.invalid",),
    )


def test_policy_source_is_deterministic_and_has_default_deny() -> None:
    source = compile_rego(_policy())
    assert source == compile_rego(_policy())
    assert "default allow := false" in source
    assert "not tool_denied" in source
    assert "not host_denied" in source
    assert policy_source_digest(_policy()).startswith("sha256:")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allow_tools": ("read_file", "read_file")},
        {"allow_tools": ("read_file", "http_post")},
        {"allow_tools": ('read_file"; allow := true',)},
        {"allow_hosts": ("example.com/../../",)},
    ],
)
def test_invalid_atoms_cannot_become_rego_source(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PolicySpec(**kwargs)


def test_action_shape_is_strict() -> None:
    with pytest.raises(ValidationError, match="requires a host"):
        PolicyAction(tool="http_post")
    with pytest.raises(ValidationError, match="must not supply"):
        PolicyAction(tool="read_file", host="example.com")
    with pytest.raises(ValidationError):
        PolicyAction.model_validate({"tool": "read_file", "untrusted": True})


def test_effect_never_runs_on_deny_or_engine_failure() -> None:
    action = PolicyAction(tool="http_post", host="demo.invalid")
    effects: list[str] = []

    class Denier:
        def evaluate(self, _policy: PolicySpec, _action: PolicyAction) -> bool:
            return False

    class Broken:
        def evaluate(self, _policy: PolicySpec, _action: PolicyAction) -> bool:
            raise PolicyUnavailable("OPA unavailable")

    class Malformed:
        def evaluate(self, _policy: PolicySpec, _action: PolicyAction) -> bool:
            return cast(bool, "false")

    def effect() -> str:
        effects.append("network")
        return "sent"

    with pytest.raises(PolicyDenied):
        enforce(Denier(), _policy(), action, effect)
    with pytest.raises(PolicyUnavailable):
        enforce(Broken(), _policy(), action, effect)
    with pytest.raises(PolicyUnavailable, match="boolean"):
        enforce(Malformed(), _policy(), action, effect)
    assert effects == []


def test_opa_evaluator_accepts_only_exact_boolean_output(monkeypatch: pytest.MonkeyPatch) -> None:
    action = PolicyAction(tool="read_file")
    evaluator = OpaEvaluator("opa", timeout_seconds=1)

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[0:3] == ["opa", "eval", "--format=raw"]
        assert Path(args[4]).read_text().startswith("package sentinel.policy")
        assert Path(args[6]).read_text() == action.model_dump_json(exclude_none=True)
        return subprocess.CompletedProcess(args, 0, "true\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert evaluator.evaluate(_policy(), action)

    def invalid_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "undefined\n", "")

    monkeypatch.setattr(subprocess, "run", invalid_run)
    with pytest.raises(PolicyUnavailable, match="valid boolean"):
        evaluator.evaluate(_policy(), action)
