import json
from pathlib import Path

import pytest

from sentinel_replay.boundary import ReplayMiss
from sentinel_replay.canonical import event_digest
from sentinel_replay.environment_pack import replay_pack
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.pack_capsule import materialize_pack

ROOT = Path(__file__).resolve().parents[1]


def test_historical_capsule_uses_installed_interpreter_and_recorded_nondeterminism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_live(*args: object) -> None:
        raise AssertionError("historical replay attempted live nondeterminism")

    capsule = CapsuleInvestigation(
        (ROOT / "tests/fixtures/replay/finite-pack-2026-11-13.sentinel").read_bytes()
    )
    expected = json.loads((ROOT / "tests/fixtures/replay/finite-pack-2026-11-13.json").read_text())
    monkeypatch.setattr("sentinel_replay.environment_pack.random.Random", forbid_live)
    monkeypatch.setattr("sentinel_replay.environment_pack.time.time_ns", forbid_live)
    result = capsule.replay()
    assert result["mode"] == "VERIFIED_REPLAY"
    assert result["journal_root"] == expected["journal_root"]
    assert result["compatibility"]["mode"] == "validated_finite_pack_v1_profile"
    assert result["live_nondeterministic_calls"] == 0


def test_full_published_capsule_replays_all_declared_adapters() -> None:
    capsule = CapsuleInvestigation(
        (
            ROOT / "benchmarks/results/product-demo-final-2026-11-13/investigation.sentinel"
        ).read_bytes()
    )
    result = capsule.replay()
    assert result["matched"] == 3186
    assert result["checkpoints"] == {"workspace": True, "git": True, "sqlite": True}
    assert result["final_state_verified"]


def test_self_consistent_unknown_runtime_cannot_bypass_profile_admission(tmp_path: Path) -> None:
    capsule = CapsuleInvestigation(
        (ROOT / "tests/fixtures/replay/finite-pack-2026-11-13.sentinel").read_bytes()
    )
    source = materialize_pack(capsule.artifacts, capsule.journal, tmp_path)
    path = source / "definition.json"
    definition = json.loads(path.read_text())
    definition.pop("definition_digest")
    definition["runtime_digests"]["policy_language.py"] = "sha256:" + "1" * 64
    definition["definition_digest"] = event_digest(definition)
    path.write_text(json.dumps(definition))
    with pytest.raises(ReplayMiss, match="validated replay profile"):
        replay_pack(source, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()
