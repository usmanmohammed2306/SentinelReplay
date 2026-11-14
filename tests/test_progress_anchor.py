from pathlib import Path
from typing import Any, cast

import pytest

from sentinel_replay.environment_pack import Pack, PackStep, record_pack, replay_pack
from sentinel_replay.journal import Journal
from sentinel_replay.local_anchor import create_keypair
from sentinel_replay.policy_language import Action, Policy
from sentinel_replay.progress_anchor import ProgressAnchors, verify_progress


def test_signed_prefixes_detect_tail_rewrite_rollback_and_wrong_signer(tmp_path: Path) -> None:
    world = tmp_path / "world"
    world.mkdir()
    private, public = create_keypair(tmp_path / "keys", world)
    anchors = ProgressAnchors(private, tmp_path / "protected", world)
    journal = tmp_path / "events.jsonl"
    journal.touch()
    anchors.checkpoint(journal, "run", 0)
    Journal(journal).append({"kind": "read"})
    anchors.checkpoint(journal, "run", 1)
    old_ledger, old_journal = anchors.path.read_bytes(), journal.read_bytes()
    Journal(journal).append({"kind": "write"})
    anchors.checkpoint(journal, "run", 2)
    ledger, data = anchors.path.read_bytes(), journal.read_bytes()
    head = Journal(anchors.path).verify().root
    assert verify_progress(ledger, data, "run", anchors.keys, expected_head=head)["complete"]
    with pytest.raises(ValueError, match="witness"):
        verify_progress(old_ledger, old_journal, "run", anchors.keys, expected_head=head)
    with pytest.raises(ValueError, match="prefixes"):
        verify_progress(ledger, old_journal, "run", anchors.keys)
    with pytest.raises(ValueError, match="tail"):
        verify_progress(old_ledger, data, "run", anchors.keys)
    with pytest.raises(ValueError, match="trust"):
        verify_progress(ledger, data, "run", {})
    assert public.read_bytes() == next(iter(anchors.keys.values()))


def test_signer_failure_at_durable_intent_prevents_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "declared-agent"
    outside.mkdir()
    private, _ = create_keypair(tmp_path / "keys", outside)
    original = ProgressAnchors.checkpoint

    def outage(self: ProgressAnchors, journal: Path, run_id: str, records: int) -> None:
        if records:
            raise OSError("signer unavailable")
        original(self, journal, run_id, records)

    monkeypatch.setattr(ProgressAnchors, "checkpoint", outage)
    pack = Pack(
        name="anchor-outage",
        files={},
        steps=tuple(
            [PackStep(action=Action(operation="clock")) for _ in range(99)]
            + [
                PackStep(
                    action=Action(operation="write_file", resource="effect.txt"), value="blocked"
                )
            ]
        ),
    )
    with pytest.raises(OSError, match="signer unavailable"):
        record_pack(
            pack,
            tmp_path / "run",
            Policy(),
            decisions=["allowed"] * 100,
            signing_key=private,
            anchor_root=tmp_path / "anchors",
            anchor_every=100,
        )
    assert not (tmp_path / "run/world/effect.txt").exists()
    assert not (tmp_path / "run/report.json").exists()


def test_recordings_have_private_distinct_carriers_and_missing_key_fails(tmp_path: Path) -> None:
    pack = Pack(
        name="carriers",
        files={"secret.txt": "synthetic-only"},
        steps=(
            PackStep(
                action=Action(operation="read_file", resource="secret.txt", sensitivity="secret")
            ),
        ),
    )
    reports = [
        record_pack(pack, tmp_path / str(i), Policy(), decisions=["allowed"]) for i in range(2)
    ]
    events = [Journal(tmp_path / str(i) / "journal.jsonl").read_verified()[0] for i in range(2)]
    assert reports[0]["definition_digest"] != reports[1]["definition_digest"]
    assert (
        cast(Any, events[0][0])["evidence"]["carrier"]
        != cast(Any, events[1][0])["evidence"]["carrier"]
    )
    replay_pack(tmp_path / "0", tmp_path / "replay")
    import json

    definition = json.loads((tmp_path / "0/definition.json").read_text())
    key = definition["provenance_key"]["digest"][7:]
    (tmp_path / "0/blobs/sha256" / key[:2] / key).unlink()
    with pytest.raises((OSError, ValueError)):
        replay_pack(tmp_path / "0", tmp_path / "missing-key")
