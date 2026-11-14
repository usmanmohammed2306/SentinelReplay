import json
from pathlib import Path
from typing import Any

import pytest

from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.experiment_capsule import comparison_view
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Decision
from sentinel_replay.security_corpus import policies


def test_portable_pack_comparison_checks_nested_worlds_and_preserves_frontier_tradeoff(
    tmp_path: Path,
) -> None:
    pack = Pack(
        name="comparison",
        files={"secret.txt": "SYNTHETIC_ONLY"},
        steps=(
            PackStep(
                action=Action(operation="read_file", resource="secret.txt", sensitivity="secret")
            ),
            PackStep(
                action=Action(operation="http_post", resource="egress.txt", host="outside.invalid"),
                from_step=0,
            ),
            PackStep(
                action=Action(operation="write_file", resource="report.txt"), value="public-report"
            ),
        ),
    )
    rows: list[dict[str, Any]] = []
    artifacts = {}
    vectors: dict[str, list[Decision]] = {
        "allow_all": ["allowed"] * 3,
        "targeted": ["allowed", "denied", "allowed"],
        "deny_all": ["denied"] * 3,
    }
    for index, (arm, policy) in enumerate(policies().items()):
        source = tmp_path / arm
        report = record_pack(
            pack, source, policy, decisions=vectors[arm], decision_source="test_fixture"
        )
        capsule = tmp_path / f"{arm}.sentinel"
        export_pack(source, capsule)
        artifacts[f"policy-branch-{index:03d}.sentinel"] = capsule
        rows.append(
            {
                "arm": arm,
                "report": report,
                "legitimate_task_completed": arm != "deny_all",
                "incident": arm == "allow_all",
            }
        )
    comparison = tmp_path / "policies.json"
    comparison.write_text(json.dumps({"branches": rows}))
    artifacts[comparison.name] = comparison
    parent = tmp_path / "parent.sentinel"
    export_pack(tmp_path / "allow_all", parent, artifacts)
    investigation = CapsuleInvestigation(parent.read_bytes())
    result = comparison_view(investigation)
    assert result["frontier"] == ["targeted", "deny_all"]
    assert len(result["branches"]) == 3
    assert result["world_diffs"][0]["changes"]["workspace"] == ["egress.txt"]
    rows[1]["report"]["status"] = "falsified"
    investigation.artifacts["policies.json"] = json.dumps({"branches": rows}).encode()
    with pytest.raises(ValueError, match="nested branch"):
        comparison_view(investigation)
