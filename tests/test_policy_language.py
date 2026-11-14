import os

import pytest
from pydantic import ValidationError

from sentinel_replay.policy_language import Action, Policy, Rule, evaluate_batch


def test_unknown_atoms_and_implicit_defaults_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate({"rules": [], "silent_allow": True})
    with pytest.raises(ValidationError):
        Action(operation="read_file", resource="../escape")


@pytest.mark.opa_integration
@pytest.mark.skipif(os.environ.get("SENTINEL_TEST_OPA_DOCKER") != "1", reason="real OPA required")
def test_full_grammar_real_opa_deny_confirm_and_pattern_precedence() -> None:
    policy = Policy(
        rules=(
            Rule(effect="allow", operation="*"),
            Rule(effect="deny", operation="read_file", resource="credential*"),
            Rule(effect="deny", operation="http_post", host="blocked.invalid"),
            Rule(effect="deny", operation="artifact_export", sensitivity="secret"),
            Rule(effect="deny", operation="process_exec", executable="curl"),
            Rule(effect="deny", operation="git_write", resource="refs*"),
            Rule(effect="confirm", operation="write_file", resource="harness*"),
        )
    )
    actions = [
        Action(operation="read_file", resource="credential.txt"),
        Action(operation="read_file", resource="public.txt"),
        Action(operation="http_post", host="blocked.invalid"),
        Action(operation="http_post", host="allowed.invalid"),
        Action(operation="artifact_export", sensitivity="secret"),
        Action(operation="process_exec", executable="curl"),
        Action(operation="git_write", resource="refs-main"),
        Action(operation="write_file", resource="harness.py"),
        Action(operation="write_file", resource="report.txt"),
    ]
    assert evaluate_batch(policy, actions) == [
        "denied",
        "allowed",
        "denied",
        "allowed",
        "denied",
        "denied",
        "denied",
        "confirmation_required",
        "allowed",
    ]
    assert evaluate_batch(Policy(), actions) == ["denied"] * len(actions)
