"""Local OpenTelemetry SDK spans and journal-authoritative OTLP/JSON enrichment.

No global provider, environment resource detection, collector, or network export.
Span timestamps/parentage enrich a verified journal; they never replace an event,
change its order, authorize an effect, or add contamination reachability.
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NonRecordingSpan, SpanContext, set_span_in_context

from sentinel_replay.canonical import load_json_unique
from sentinel_replay.journal import Journal

MAX_TELEMETRY_BYTES = 32 * 1024 * 1024
MAX_SPANS = 50001


class RecordingTelemetry:
    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider(resource=Resource({"service.name": "sentinel-replay"}))
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("sentinel.environment-pack", "1")
        self.contexts: dict[str, SpanContext] = {}

    def __enter__(self) -> "RecordingTelemetry":
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if error_type is not None:
            self.provider.shutdown()

    @contextmanager
    def boundary(self, call_id: str, digest: str, parent: str | None) -> Iterator[None]:
        context = None
        if parent in self.contexts:
            context = set_span_in_context(NonRecordingSpan(self.contexts[parent]))
        with self.tracer.start_as_current_span(
            "recorded-boundary",
            context=context,
            attributes={"sentinel.call_id": call_id, "sentinel.request_digest": digest},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            self.contexts[call_id] = span.get_span_context()
            yield

    def finish(self, destination: Path) -> None:
        self.provider.force_flush()
        spans = []
        for span in self.exporter.get_finished_spans():
            context = span.context
            if context is None or span.start_time is None or span.end_time is None:
                raise ValueError("SDK span is missing identity or timestamps")
            spans.append(
                {
                    "traceId": format(context.trace_id, "032x"),
                    "spanId": format(context.span_id, "016x"),
                    "parentSpanId": format(span.parent.span_id, "016x") if span.parent else "",
                    "name": "recorded-boundary",
                    "kind": 1,
                    "startTimeUnixNano": str(span.start_time),
                    "endTimeUnixNano": str(span.end_time),
                    "attributes": [
                        {"key": key, "value": {"stringValue": value}}
                        for key, value in (span.attributes or {}).items()
                    ],
                }
            )
        self.provider.shutdown()
        data = json.dumps(
            {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if len(data) > MAX_TELEMETRY_BYTES or len(spans) > MAX_SPANS:
            raise ValueError("telemetry exceeds declared budget")
        destination.write_bytes(data)


def merge_telemetry(journal: Path, data: bytes, *, expected_root: str) -> dict[str, Any]:
    try:
        return _merge_telemetry(journal, data, expected_root=expected_root)
    except (AttributeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("malformed OTLP/JSON trace structure") from error


def _merge_telemetry(journal: Path, data: bytes, *, expected_root: str) -> dict[str, Any]:
    if len(data) > MAX_TELEMETRY_BYTES:
        raise ValueError("OTLP/JSON exceeds byte budget")
    events, verified = Journal(journal).read_verified()
    if verified.root != expected_root:
        raise ValueError("telemetry target root mismatch")
    by_call = {}
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get("call_id"), str):
            raise ValueError("telemetry requires typed journal boundaries")
        if event["call_id"] in by_call:
            raise ValueError("ambiguous journal call identity")
        by_call[event["call_id"]] = (index, event.get("request_digest"))
    envelope = load_json_unique(data.decode())
    if not isinstance(envelope, dict) or not isinstance(envelope.get("resourceSpans"), list):
        raise ValueError("OTLP/JSON trace envelope required")
    matched: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    calls: set[str] = set()
    unmatched = 0
    for resource in envelope["resourceSpans"]:
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                if len(seen) >= MAX_SPANS:
                    raise ValueError("OTLP span budget exceeded")
                trace, identity = span.get("traceId"), span.get("spanId")
                if (
                    not isinstance(trace, str)
                    or not re.fullmatch(r"[0-9a-fA-F]{32}", trace)
                    or int(trace, 16) == 0
                    or not isinstance(identity, str)
                    or not re.fullmatch(r"[0-9a-fA-F]{16}", identity)
                    or int(identity, 16) == 0
                ):
                    raise ValueError("invalid OTLP trace/span identity")
                key = (trace.lower(), identity.lower())
                if key in seen:
                    raise ValueError("duplicate OTLP span identity")
                seen.add(key)
                attributes = {}
                for item in span.get("attributes", []):
                    name = item.get("key")
                    if name in {"sentinel.call_id", "sentinel.request_digest"}:
                        if name in attributes:
                            raise ValueError("duplicate journal binding attribute")
                        attributes[name] = item.get("value", {}).get("stringValue")
                call_id = attributes.get("sentinel.call_id")
                if not isinstance(call_id, str) or call_id not in by_call:
                    unmatched += 1
                    continue
                step, digest = by_call[call_id]
                if digest is None or digest != attributes.get("sentinel.request_digest"):
                    raise ValueError("telemetry request binding differs from journal")
                if call_id in calls:
                    raise ValueError("multiple spans claim the same journal boundary")
                calls.add(call_id)
                start, stop = span.get("startTimeUnixNano"), span.get("endTimeUnixNano")
                if (
                    not isinstance(start, str)
                    or not isinstance(stop, str)
                    or not re.fullmatch(r"[0-9]{1,20}", start)
                    or not re.fullmatch(r"[0-9]{1,20}", stop)
                    or not 0 <= int(start) <= int(stop) < 2**64
                ):
                    raise ValueError("invalid OTLP nanosecond timestamps")
                parent = span.get("parentSpanId", "").lower()
                if parent and not re.fullmatch(r"[0-9a-f]{16}", parent):
                    raise ValueError("invalid OTLP parent identity")
                matched.append(
                    {
                        "step": step,
                        "trace_id": key[0],
                        "span_id": key[1],
                        "parent_span_id": parent,
                        "duration_ns": str(int(stop) - int(start)),
                    }
                )
    indexed = {(row["trace_id"], row["span_id"]): row["step"] for row in matched}
    structural = []
    for row in matched:
        parent_step = indexed.get((row["trace_id"], row["parent_span_id"]))
        if parent_step is not None:
            if parent_step == row["step"]:
                raise ValueError("OTLP span may not parent itself")
            structural.append(
                {
                    "source": parent_step,
                    "target": row["step"],
                    "kind": "trace_parent",
                    "rationale": "OTel structural parent; excluded from contamination reachability",
                }
            )
    parents = {edge["target"]: edge["source"] for edge in structural}
    finished: set[int] = set()
    for step in parents:
        trail: set[int] = set()
        current = step
        while current in parents and current not in finished:
            if current in trail:
                raise ValueError("OTLP parentage contains a cycle")
            trail.add(current)
            current = parents[current]
        finished.update(trail)
    return {
        "schema_version": 1,
        "journal_root": verified.root,
        "journal_records": verified.records,
        "matched_spans": sorted(matched, key=lambda row: row["step"]),
        "unmatched_spans": unmatched,
        "structural_edges": structural,
        "limitation": (
            "Untrusted telemetry enrichment only. Journal order/payloads remain authoritative; "
            "parentage adds no causal or effect guarantee."
        ),
    }
