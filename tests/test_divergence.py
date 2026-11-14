from pathlib import Path
from typing import Any

from sentinel_replay.canonical import event_digest
from sentinel_replay.capsule import export_capsule
from sentinel_replay.divergence import compare_recordings
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.journal import Journal


def _capsule(
    root: Path, name: str, request: int = 1, output: str = "same", call_id: str = "action-1"
) -> CapsuleInvestigation:
    events: list[dict[str, Any]] = []
    for index in range(2):
        value = {"fixture_input": request if index else 0}
        events.append(
            {
                "kind": "tool",
                "call_id": call_id if index else "action-0",
                "request": value,
                "request_digest": event_digest(value),
                "response": {
                    "state": "materialized" if index else "recorded_input",
                    "value": output if index else "stub",
                },
                "evidence": {"operation": "write_file" if index else "model_call"},
            }
        )
    journal, capsule = root / (name + ".jsonl"), root / (name + ".sentinel")
    Journal(journal).append_many(events)
    export_capsule(name, journal, capsule)
    return CapsuleInvestigation(capsule.read_bytes())


def test_typed_input_output_effect_and_structural_changes_do_not_fall_back_to_digest_matching(
    tmp_path: Path,
) -> None:
    original = _capsule(tmp_path, "original")
    same = compare_recordings(original, _capsule(tmp_path, "same"))
    assert same["structural_divergence"] is None
    assert same["first_input_divergence"] is None
    assert not same["declared_effect_receipts_differ"]
    changed = compare_recordings(
        original, _capsule(tmp_path, "changed", request=2, output="changed")
    )
    assert changed["first_input_divergence"]["step"] == 1
    assert changed["first_output_divergence"]["step"] == 1
    assert changed["declared_effect_receipts_differ"]
    structural = compare_recordings(original, _capsule(tmp_path, "structural", call_id="different"))
    assert structural["compared_identity_prefix"] == 1
    assert structural["structural_divergence"]["step"] == 1
    assert structural["first_input_divergence"] is None
