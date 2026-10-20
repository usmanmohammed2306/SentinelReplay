"""Reproducible local journal throughput probe; not the V1 release benchmark."""

import argparse
import json
import os
import platform
import resource
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter_ns

from sentinel_replay.journal import Journal
from sentinel_replay.provenance import build_provenance
from sentinel_replay.timeline import compress_timeline


def run(events: int, mode: str = "batch") -> dict[str, object]:
    if not 1 <= events <= 50_000:
        raise ValueError("events must be between 1 and 50,000")
    if mode not in {"batch", "stream"}:
        raise ValueError("mode must be batch or stream")
    with tempfile.TemporaryDirectory(prefix="sentinel-journal-benchmark-") as directory:
        journal = Journal(Path(directory) / "run.jsonl")

        def fixture() -> Iterator[dict[str, object]]:
            for index in range(events):
                yield {
                    "sequence": index,
                    "kind": "tool",
                    "call_id": f"read-{index}",
                    "evidence": {"operation": "read_file", "sensitivity": "public"},
                    "response": {"status": "ok"},
                }

        start = perf_counter_ns()
        if mode == "batch":
            written = journal.append_many(fixture())
        else:
            with journal.writer() as writer:
                for event in fixture():
                    written = writer.append(event)
        written_at = perf_counter_ns()
        checked = journal.verify()
        verified_at = perf_counter_ns()
        if checked != written or checked.records != events:
            raise RuntimeError("benchmark evidence did not verify")
        timeline = compress_timeline(journal.path)
        compressed_at = perf_counter_ns()
        if timeline.actions != events or len(timeline.phases) != 1 or timeline.findings:
            raise RuntimeError("benchmark timeline did not compress the benign run")
        provenance = build_provenance(journal.path, 0)
        graph_at = perf_counter_ns()
        if (
            provenance.nodes != events
            or len(provenance.edges) != events - 1
            or provenance.blast_radius
        ):
            raise RuntimeError("benchmark provenance did not preserve chronology-only semantics")
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {
            "schema_version": 2,
            "benchmark": "journal_append_verify_timeline_and_declared_provenance",
            "claim": "local_probe_only_not_release_gate",
            "mode": mode,
            "events": events,
            "journal_bytes": journal.path.stat().st_size,
            "root": checked.root,
            "append_seconds": round((written_at - start) / 1_000_000_000, 6),
            "verify_seconds": round((verified_at - written_at) / 1_000_000_000, 6),
            "timeline_seconds": round((compressed_at - verified_at) / 1_000_000_000, 6),
            "timeline_phases": len(timeline.phases),
            "provenance_seconds": round((graph_at - compressed_at) / 1_000_000_000, 6),
            "provenance_edges": len(provenance.edges),
            "max_rss_bytes": max_rss if sys.platform == "darwin" else max_rss * 1024,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "logical_cpus": os.cpu_count(),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, required=True)
    parser.add_argument("--mode", choices=("batch", "stream"), default="batch")
    args = parser.parse_args()
    print(json.dumps(run(args.events, args.mode), sort_keys=True))


if __name__ == "__main__":
    main()
