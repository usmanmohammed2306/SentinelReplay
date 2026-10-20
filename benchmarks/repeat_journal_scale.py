"""Run isolated journal-scale trials and retain raw results plus robust summaries.

This is a local synthetic component benchmark, not the V1 release benchmark.
"""

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

METRICS = (
    "append_seconds",
    "verify_seconds",
    "timeline_seconds",
    "provenance_seconds",
    "max_rss_bytes",
)


def _summary(rows: list[dict[str, Any]], events: int) -> dict[str, object]:
    result: dict[str, object] = {"trials": len(rows)}
    for key in METRICS:
        samples = [row[key] for row in rows]
        if any(type(value) not in {int, float} or value <= 0 for value in samples):
            raise ValueError(f"invalid benchmark samples for {key}")
        result[key] = {
            "median": statistics.median(samples),
            "min": min(samples),
            "max": max(samples),
        }
    for key in ("append_seconds", "verify_seconds"):
        seconds = result[key]
        if not isinstance(seconds, dict):
            raise AssertionError("summary shape changed")
        result[key.replace("seconds", "records_per_second_at_median")] = round(
            events / seconds["median"], 1
        )
    return result


def run_repeated(*, events: int, trials: int, script: Path) -> dict[str, object]:
    if not 1 <= events <= 50_000 or not 3 <= trials <= 20:
        raise ValueError("events must be 1..50,000 and trials must be 3..20")
    source = script.parent.parent / "src" / "sentinel_replay" / "journal.py"
    source_digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    benchmark_digest = "sha256:" + hashlib.sha256(script.read_bytes()).hexdigest()
    raw: list[dict[str, object]] = []
    by_mode: dict[str, list[dict[str, Any]]] = {"batch": [], "stream": []}
    expected_root: str | None = None
    expected_bytes: int | None = None
    expected_environment: object = None
    for round_index in range(trials):
        # Balanced alternating order reduces one obvious cache/thermal-order bias.
        order = ("batch", "stream") if round_index % 2 == 0 else ("stream", "batch")
        for mode in order:
            completed = subprocess.run(
                [sys.executable, str(script), "--events", str(events), "--mode", mode],
                capture_output=True,
                text=True,
                timeout=90,
                check=True,
            )
            row = json.loads(completed.stdout)
            if not isinstance(row, dict) or row.get("events") != events or row.get("mode") != mode:
                raise ValueError("benchmark child produced a mismatched result")
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
                raise ValueError("benchmark child changed evidence or environment across trials")
            by_mode[mode].append(row)
            raw.append({"round": round_index + 1, "mode": mode, "result": row})
    return {
        "schema_version": 1,
        "claim": "local_synthetic_component_benchmark_not_release_or_real_agent",
        "events_per_trial": events,
        "trials_per_mode": trials,
        "isolation": "fresh_process_per_trial",
        "order": "balanced_alternating_batch_stream",
        "journal_source_digest": source_digest,
        "benchmark_source_digest": benchmark_digest,
        "journal_root_all_trials": expected_root,
        "journal_bytes_all_trials": expected_bytes,
        "environment": expected_environment,
        "raw_trials": raw,
        "summary": {mode: _summary(rows, events) for mode, rows in by_mode.items()},
        "limitations": [
            "synthetic public metadata only; no model or external tool latency",
            "one macOS host, one sequential process at a time; "
            "no concurrent throughput or p95 claim",
            "memory is peak process RSS for append, verify, timeline, and provenance together",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=50_000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    script = Path(__file__).resolve().parent / "journal_scale.py"
    report = run_repeated(events=options.events, trials=options.trials, script=script)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
