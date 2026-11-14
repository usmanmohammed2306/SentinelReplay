from pathlib import Path

import pytest

from sentinel_replay.environment_pack import Pack, PackStep, record_pack, replay_pack
from sentinel_replay.policy_language import Action, Policy, Rule


def test_real_file_effects_restore_reexecute_and_match_without_live_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = Pack(
        name="tiny",
        files={"public.txt": "public"},
        steps=(
            PackStep(action=Action(operation="rng")),
            PackStep(action=Action(operation="read_file", resource="public.txt")),
            PackStep(action=Action(operation="write_file", resource="report.txt"), from_step=1),
        ),
    )
    policy = Policy(rules=(Rule(effect="allow"),))
    report = record_pack(
        pack, tmp_path / "run", policy, decisions=["allowed"] * 3, decision_source="test_fixture"
    )
    assert report["status"] == "completed"
    assert (tmp_path / "run/world/report.txt").read_text() == "public"

    def no_live(*args: object) -> None:
        raise AssertionError("strict replay reached live nondeterminism")

    monkeypatch.setattr("sentinel_replay.environment_pack.random.Random", no_live)
    replay = replay_pack(tmp_path / "run", tmp_path / "replay")
    assert replay["mode"] == "VERIFIED_REPLAY"
    assert replay["live_nondeterministic_calls"] == 0
    assert replay["effects_reexecuted"] == 1
    assert replay["final_state_verified"] is True


def test_failed_durable_intent_prevents_the_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel_replay.journal import JournalWriter

    original = JournalWriter.append

    def fail_intent(self: JournalWriter, event: object) -> object:
        if isinstance(event, dict) and str(event.get("call_id", "")).startswith("intent-"):
            raise OSError("injected durable-intent outage")
        return original(self, event)

    monkeypatch.setattr(JournalWriter, "append", fail_intent)
    pack = Pack(
        name="intent",
        files={},
        steps=(
            PackStep(
                action=Action(operation="write_file", resource="effect.txt"), value="must-not-exist"
            ),
        ),
    )
    with pytest.raises(OSError, match="intent outage"):
        record_pack(
            pack, tmp_path / "run", Policy(), decisions=["allowed"], decision_source="test_fixture"
        )
    assert not (tmp_path / "run/world/effect.txt").exists()
    assert not (tmp_path / "run/report.json").exists()


def test_unknown_operation_is_not_replay_eligible(tmp_path: Path) -> None:
    pack = Pack(name="gap", files={}, steps=(PackStep(action=Action(operation="native_shell")),))
    report = record_pack(
        pack, tmp_path / "run", Policy(), decisions=["allowed"], decision_source="test_fixture"
    )
    assert report["status"] == "unknown"
    with pytest.raises(ValueError, match="unsupported"):
        replay_pack(tmp_path / "run", tmp_path / "replay")


def test_changed_checkpoint_or_missing_recording_fails_before_claiming_replay(
    tmp_path: Path,
) -> None:
    pack = Pack(
        name="tiny",
        files={"public.txt": "public"},
        steps=(PackStep(action=Action(operation="read_file", resource="public.txt")),),
    )
    record_pack(
        pack, tmp_path / "run", Policy(), decisions=["allowed"], decision_source="test_fixture"
    )
    path = tmp_path / "run/journal.jsonl"
    path.write_bytes(b"")
    with pytest.raises((ValueError, RuntimeError)):
        replay_pack(tmp_path / "run", tmp_path / "replay")


def test_unpublished_definition_never_allows_covered_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    original = os.link

    def fail_definition(source: object, target: object, **kwargs: object) -> None:
        if Path(str(target)).name == "definition.json":
            raise OSError("injected metadata publication failure")
        original(source, target, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("sentinel_replay.environment_pack.os.link", fail_definition)
    pack = Pack(
        name="metadata",
        files={},
        steps=(
            PackStep(
                action=Action(operation="write_file", resource="effect.txt"), value="must-not-exist"
            ),
        ),
    )
    with pytest.raises(OSError, match="metadata publication"):
        record_pack(pack, tmp_path / "run", Policy(), decisions=["allowed"])
    assert not (tmp_path / "run/world/effect.txt").exists()
    assert not (tmp_path / "run/definition.json").exists()
    assert not (tmp_path / "run/report.json").exists()
