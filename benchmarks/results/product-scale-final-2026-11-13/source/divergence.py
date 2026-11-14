"""Structural, input/output and declared-effect differences over verified evidence."""

import re
from itertools import zip_longest
from typing import Any

from sentinel_replay.canonical import event_digest
from sentinel_replay.investigation import CapsuleInvestigation


def _identity(event: dict[str, Any] | None) -> dict[str, str] | None:
    if event is None:
        return None

    def safe(value: object) -> str:
        return (
            value
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)
            else "redacted"
        )

    return {"call_id": safe(event.get("call_id")), "kind": safe(event.get("kind"))}


def compare_recordings(left: CapsuleInvestigation, right: CapsuleInvestigation) -> dict[str, Any]:
    structural = input_change = output_change = None
    prefix = 0
    for step, (a, b) in enumerate(zip_longest(left.events, right.events)):
        if (
            a is None
            or b is None
            or (a.get("kind"), a.get("call_id")) != (b.get("kind"), b.get("call_id"))
        ):
            structural = {"step": step, "original": _identity(a), "alternate": _identity(b)}
            break
        prefix += 1
        for event in (a, b):
            if "request" not in event or event_digest(event["request"]) != event.get(
                "request_digest"
            ):
                raise ValueError("declared request digest differs from recorded payload")
        if input_change is None and a["request_digest"] != b["request_digest"]:
            input_change = {
                "step": step,
                "original_digest": a["request_digest"],
                "alternate_digest": b["request_digest"],
            }
        if output_change is None and event_digest(a.get("response")) != event_digest(
            b.get("response")
        ):
            output_change = {
                "step": step,
                "original_digest": event_digest(a.get("response")),
                "alternate_digest": event_digest(b.get("response")),
            }

    def receipts(source: CapsuleInvestigation) -> list[str]:
        return [
            event_digest(event.get("response"))
            for event in source.events
            if (
                isinstance(event.get("evidence"), dict)
                and event["evidence"].get("operation") == "effect_intent"
            )
            or (
                isinstance(event.get("response"), dict)
                and event["response"].get("state") == "materialized"
            )
        ]

    original, alternate = receipts(left), receipts(right)
    return {
        "schema_version": 1,
        "original_journal_root": left.verified.root,
        "alternate_journal_root": right.verified.root,
        "alignment": "ordered_equal_identity_prefix",
        "compared_identity_prefix": prefix,
        "structural_divergence": structural,
        "first_input_divergence": input_change,
        "first_output_divergence": output_change,
        "declared_effect_receipts_differ": original != alternate,
        "original_effect_receipts": len(original),
        "alternate_effect_receipts": len(alternate),
        "limitation": (
            "Verified recordings compared; effects remain adapter-specific. "
            "Changes after the first "
            "structural mismatch are unaligned, not silently matched by request digest. "
            "No universal causal claim."
        ),
    }
