"""Crash-gap reconciliation checks actual bytes before finalizing a result."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_replay.cli import app
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.gateway_reconcile import ReconciliationError, reconcile_gateway_effects
from sentinel_replay.journal import Journal, JournalWriter, Verification
from sentinel_replay.policy import PolicyAction, PolicySpec
from sentinel_replay.tool_gateway import ToolGateway

REQUEST = "1" * 32
POLICY = "sha256:" + "a" * 64
DATA = b"synthetic-public\n"


def setup_gap(tmp_path: Path, *, intent: bool = True) -> tuple[Path, Path]:
    root = tmp_path / "fixture"
    (root / "outbox").mkdir(parents=True)
    journal = tmp_path / "controller" / "gateway.jsonl"
    events: list[dict[str, object]] = [
        {
            "kind": "gateway_proposal",
            "request_id": REQUEST,
            "source_alias": "public.txt",
            "destination_name": "copy.txt",
            "tool": "copy_public",
            "policy_digest": POLICY,
        },
        {"kind": "gateway_decision", "request_id": REQUEST, "state": "allowed"},
    ]
    if intent:
        events.append(
            {
                "kind": "gateway_effect_intent",
                "request_id": REQUEST,
                "bytes": len(DATA),
                "digest": blob_digest(DATA),
            }
        )
    Journal(journal).append_many(events)
    return root, journal


def test_missing_effect_is_not_inferred_from_allowed_intent(tmp_path: Path) -> None:
    root, journal = setup_gap(tmp_path)
    before = Journal(journal).verify()
    report = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert report.requests[0].outcome == "missing_effect"
    assert Journal(journal).verify() == before


def test_matched_effect_finalizes_once_without_repeating_write(tmp_path: Path) -> None:
    root, journal = setup_gap(tmp_path)
    output = root / "outbox" / "copy.txt"
    output.write_bytes(DATA)
    first = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert first.requests[0].outcome == "matched_effect_finalized"
    assert first.journal_records == 4
    after = output.stat()
    second = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert second.requests[0].outcome == "completed_verified"
    assert second.journal_root == first.journal_root
    assert output.stat().st_ino == after.st_ino
    assert output.stat().st_mtime_ns == after.st_mtime_ns
    cli = CliRunner().invoke(app, ["gateway", "reconcile", str(journal), str(root)])
    assert cli.exit_code == 0, cli.output
    assert '"completed_verified"' in cli.output


def test_gateway_result_write_crash_is_recovered_from_actual_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "fixture"
    (root / "sources").mkdir(parents=True)
    (root / "outbox").mkdir()
    (root / "sources" / "public.txt").write_bytes(DATA)
    journal = tmp_path / "controller" / "gateway.jsonl"

    class AllowPublic:
        def evaluate(self, _policy: PolicySpec, _action: PolicyAction) -> bool:
            return True

    gateway = ToolGateway(
        root=root,
        journal_path=journal,
        source_tools={"public.txt": "copy_public"},
        policy=PolicySpec(allow_tools=("copy_public",)),
        evaluator=AllowPublic(),
    )
    original_append = JournalWriter.append

    def crash_on_result(self: JournalWriter, event: object) -> Verification:
        if isinstance(event, dict) and event.get("kind") == "gateway_result":
            raise OSError("simulated process loss before result record")
        return original_append(self, event)

    monkeypatch.setattr(JournalWriter, "append", crash_on_result)
    with pytest.raises(OSError, match="simulated process loss"):
        gateway.copy_named("public.txt", "copy.txt")
    monkeypatch.setattr(JournalWriter, "append", original_append)
    assert (root / "outbox" / "copy.txt").read_bytes() == DATA
    assert len(Journal(journal).events()) == 3
    recovered = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert recovered.requests[0].outcome == "matched_effect_finalized"
    assert reconcile_gateway_effects(journal, root).requests[0].outcome == "completed_verified"


def test_mismatched_or_missing_recorded_effect_fails_verification(tmp_path: Path) -> None:
    root, journal = setup_gap(tmp_path)
    output = root / "outbox" / "copy.txt"
    output.write_bytes(b"changed\n")
    report = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert report.requests[0].outcome == "effect_mismatch"
    assert report.journal_records == 3
    output.write_bytes(DATA)
    reconcile_gateway_effects(journal, root, finalize_matched=True)
    output.unlink()
    assert reconcile_gateway_effects(journal, root).requests[0].outcome == "effect_mismatch"


def test_legacy_allow_without_intent_remains_unknown(tmp_path: Path) -> None:
    root, journal = setup_gap(tmp_path, intent=False)
    (root / "outbox" / "copy.txt").write_bytes(DATA)
    report = reconcile_gateway_effects(journal, root, finalize_matched=True)
    assert report.requests[0].outcome == "unknown_no_intent"
    assert report.journal_records == 2


def test_symlink_effect_is_not_followed(tmp_path: Path) -> None:
    root, journal = setup_gap(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(DATA)
    (root / "outbox" / "copy.txt").symlink_to(outside)
    with pytest.raises((OSError, ReconciliationError)):
        reconcile_gateway_effects(journal, root, finalize_matched=True)
