"""Reconstruct the former joined batch write and compare peak process RSS.

The legacy implementation exists only in this benchmark. It matches the old
append_many algorithm except for its function location; the production writer
remains the current Journal.append_many implementation.
"""

import argparse
import fcntl
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import journal_scale

from sentinel_replay import journal as journal_module


def _legacy_join_append_many(
    self: journal_module.Journal, events: Iterable[object]
) -> journal_module.Verification:
    """Benchmark-only reconstruction of the pre-2026-10-10 joined write."""
    self.path.parent.mkdir(parents=True, exist_ok=True)
    destination, created = journal_module._open_writer(self.path)
    with destination:
        fcntl.flock(destination.fileno(), fcntl.LOCK_EX)
        destination.seek(0)
        current = journal_module._read_verified_stream(destination, collect=False)[1]
        if created:
            journal_module._fsync_parent(self.path)
        previous = current.root
        encoded_rows: list[bytes] = []
        total_bytes = 0
        for offset, event in enumerate(events, 1):
            if offset > journal_module.MAX_BATCH_EVENTS:
                raise ValueError("journal batch exceeds event limit")
            index = current.records + offset
            encoded, digest = journal_module._encode_record(index, previous, event)
            total_bytes += len(encoded)
            if total_bytes > journal_module.MAX_BATCH_BYTES:
                raise ValueError("journal batch exceeds byte limit")
            encoded_rows.append(encoded)
            previous = digest
        if not encoded_rows:
            return current
        destination.seek(0, os.SEEK_END)
        destination.write(b"".join(encoded_rows))
        destination.flush()
        os.fsync(destination.fileno())
    return journal_module.Verification(current.records + len(encoded_rows), previous)


def _child(strategy: str, events: int) -> dict[str, object]:
    if strategy == "legacy_join":
        journal_module.Journal.append_many = _legacy_join_append_many
    elif strategy != "current_chunked":
        raise ValueError("unknown strategy")
    return journal_scale.run(events, "batch")


def _median(values: list[int | float]) -> int | float:
    return statistics.median(values)


def compare(events: int, trials: int) -> dict[str, object]:
    if not 1 <= events <= 50_000 or not 3 <= trials <= 20:
        raise ValueError("events must be 1..50,000 and trials must be 3..20")
    script = Path(__file__).resolve()
    root = script.parent.parent
    raw: list[dict[str, object]] = []
    by_strategy: dict[str, list[dict[str, Any]]] = {
        "legacy_join": [],
        "current_chunked": [],
    }
    expected_root: str | None = None
    expected_bytes: int | None = None
    expected_environment: object = None
    for round_index in range(trials):
        order = (
            ("legacy_join", "current_chunked")
            if round_index % 2 == 0
            else ("current_chunked", "legacy_join")
        )
        for strategy in order:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--child",
                    strategy,
                    "--events",
                    str(events),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=True,
            )
            row = json.loads(completed.stdout)
            if (
                not isinstance(row, dict)
                or row.get("events") != events
                or row.get("mode") != "batch"
            ):
                raise ValueError("benchmark child returned a mismatched result")
            if expected_root is None:
                expected_root = row["root"]
                expected_bytes = row["journal_bytes"]
                expected_environment = row["environment"]
            if (
                row.get("root") != expected_root
                or row.get("journal_bytes") != expected_bytes
                or row.get("environment") != expected_environment
                or row.get("timeline_phases") != 1
                or row.get("provenance_edges") != events - 1
            ):
                raise ValueError("evidence or environment changed across strategies")
            raw.append({"round": round_index + 1, "strategy": strategy, "result": row})
            by_strategy[strategy].append(row)

    summary: dict[str, dict[str, int | float]] = {}
    for strategy, rows in by_strategy.items():
        summary[strategy] = {
            "median_append_seconds": _median([row["append_seconds"] for row in rows]),
            "median_peak_process_rss_bytes": _median([row["max_rss_bytes"] for row in rows]),
            "min_peak_process_rss_bytes": min(row["max_rss_bytes"] for row in rows),
            "max_peak_process_rss_bytes": max(row["max_rss_bytes"] for row in rows),
        }
    legacy = summary["legacy_join"]["median_peak_process_rss_bytes"]
    current = summary["current_chunked"]["median_peak_process_rss_bytes"]
    reduction = round(100 * (legacy - current) / legacy, 2)
    return {
        "schema_version": 1,
        "claim": "local_synthetic_reconstructed_strategy_comparison_not_release_or_real_agent",
        "events_per_trial": events,
        "trials_per_strategy": trials,
        "isolation": "fresh_process_per_trial",
        "order": "balanced_alternating_legacy_current",
        "journal_source_digest": "sha256:"
        + hashlib.sha256((root / "src/sentinel_replay/journal.py").read_bytes()).hexdigest(),
        "benchmark_source_digest": "sha256:"
        + hashlib.sha256((root / "benchmarks/journal_scale.py").read_bytes()).hexdigest(),
        "comparison_source_digest": "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest(),
        "journal_root_all_trials": expected_root,
        "journal_bytes_all_trials": expected_bytes,
        "environment": expected_environment,
        "summary": summary,
        "median_peak_process_rss_reduction_percent": reduction,
        "raw_trials": raw,
        "limitations": [
            "legacy code is reconstructed in this benchmark, not a historical checkout",
            "synthetic public metadata; no real agent, network effect, or concurrency",
            "RSS is the peak for the entire append/verify/timeline/provenance process",
            "five trials per strategy on one macOS host do not establish a production SLO",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=50_000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=("legacy_join", "current_chunked"))
    options = parser.parse_args()
    if options.child:
        print(json.dumps(_child(options.child, options.events), sort_keys=True))
        return
    if options.output is None:
        parser.error("--output is required for a comparison run")
    report = compare(options.events, options.trials)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "median_peak_process_rss_reduction_percent": report[
                    "median_peak_process_rss_reduction_percent"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
