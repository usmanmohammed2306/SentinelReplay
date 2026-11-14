"""Source-bound synthetic recorder/index scale, with cold and warm costs separated.

Uses real cached OPA, real fsync journal writes, a file-backed SQLite derived index
and CAS. Warm query latencies exclude HTTP/browser/network time; they are not
production throughput. Every attempted size and failure is retained.
"""

import argparse
import json
import math
import platform
import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import create_engine

from sentinel_replay.canonical import event_digest
from sentinel_replay.database import RunRepository, StoredRun, metadata
from sentinel_replay.environment_pack import Pack, PackStep, record_pack
from sentinel_replay.evidence_store import FileEvidenceStore, blob_digest
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.journal import Journal
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Action, Policy, Rule
from sentinel_replay.query_index import QueryIndex


def timed(operation: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    value = operation()
    return value, time.perf_counter() - start


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_seconds": values,
        "n": len(values),
        "p50_seconds": ordered[math.ceil(0.5 * len(ordered)) - 1],
        "p95_seconds": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def measure(destination: Path, *, trials: int = 25) -> dict[str, Any]:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    source_root = Path(__file__).resolve().parents[1] / "src/sentinel_replay"
    sources = {
        path.name: blob_digest(path.read_bytes()) for path in sorted(source_root.glob("*.py"))
    }
    definition = {
        "schema_version": 1,
        "sizes": [3000, 10000, 50000],
        "trials": trials,
        "source_digests": sources,
        "runner_digest": blob_digest(Path(__file__).read_bytes()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "synthetic_finite_pack_SQLite_index_inprocess_queries",
    }
    definition["definition_digest"] = event_digest(definition)
    (destination / "definition.json").write_text(json.dumps(definition, indent=2) + "\n")
    archive = destination / "source"
    archive.mkdir()
    for name in sources:
        (archive / name).write_bytes((source_root / name).read_bytes())
    (archive / "product_scale_runner.py").write_bytes(Path(__file__).read_bytes())
    result: dict[str, Any] = {
        "definition_digest": definition["definition_digest"],
        "attempts": [],
        "limitation": __doc__,
    }
    for size in definition["sizes"]:
        attempt: dict[str, Any] = {"target_boundaries": size, "completed": False}
        result["attempts"].append(attempt)
        try:
            steps = [
                PackStep(action=Action(operation="model_call"), value="frozen-stub")
                for _ in range(size - 4)
            ]
            steps.extend(
                [
                    PackStep(
                        action=Action(
                            operation="read_file", resource="secret.txt", sensitivity="secret"
                        )
                    ),
                    PackStep(
                        action=Action(
                            operation="http_post", resource="out.txt", host="outside.invalid"
                        ),
                        from_step=len(steps),
                    ),
                ]
            )
            source = destination / str(size)
            pack = Pack(
                name=f"scale-{size}",
                files={"secret.txt": "SYNTHETIC_SCALE_ONLY"},
                steps=tuple(steps),
            )
            # N-4 stubs + read + effect (one intent) = N-1; include one benign stub.
            pack = pack.model_copy(
                update={
                    "steps": (
                        *pack.steps,
                        PackStep(action=Action(operation="model_call"), value="tail"),
                    )
                }
            )
            report, elapsed = timed(
                lambda: record_pack(pack, source, Policy(rules=(Rule(effect="allow"),)))
            )
            attempt["record_seconds_including_OPA_telemetry_snapshots"] = elapsed
            attempt["boundaries"] = report["records"]
            if report["records"] != size:
                raise ValueError("benchmark population differs")
            verifications = []
            for _ in range(trials):
                verified, elapsed = timed(lambda: Journal(source / "journal.jsonl").verify())
                if verified.root != report["journal_root"]:
                    raise ValueError("verification root differs")
                verifications.append(elapsed)
            attempt["journal_verification"] = distribution(verifications)
            capsule = source / "scale.sentinel"
            _, elapsed = timed(lambda: export_pack(source, capsule))
            attempt["capsule_export_seconds"] = elapsed
            investigation, elapsed = timed(lambda: CapsuleInvestigation(capsule.read_bytes()))
            attempt["raw_archive_load_verify_seconds"] = elapsed
            attempt["capsule_bytes"] = capsule.stat().st_size
            engine = create_engine(f"sqlite+pysqlite:///{source / 'index.db'}")
            metadata.create_all(engine)
            cas = FileEvidenceStore(source / "index-cas", max_bytes=65 * 1024 * 1024)
            ref = cas.put(investigation.data)
            run = StoredRun(
                investigation.verified.run_id,
                investigation.verified.root,
                size,
                ref.digest,
                ref.size,
                "sha256:" + "0" * 64,
            )
            RunRepository(engine).insert_or_get(run)
            indexes = QueryIndex(engine, cas)
            indexed, elapsed = timed(lambda: indexes.build(run, investigation))
            attempt["cold_index_build_seconds"] = elapsed
            operations = {
                "timeline_first_page": lambda: indexes.timeline(indexed, limit=100),
                "timeline_tail_page": lambda: indexes.timeline(
                    indexed, offset=size - 100, limit=100
                ),
                "selected_graph": lambda: indexes.provenance(indexed, root_step=size - 4, depth=3),
            }
            for name, operation in operations.items():
                samples = [timed(operation)[1] for _ in range(trials)]
                attempt[name] = distribution(samples)
            attempt["completed"] = True
            engine.dispose()
        except Exception as error:
            attempt["failure_type"] = type(error).__name__
            attempt["failure_message"] = str(error)
        finally:
            (destination / "results.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=25, choices=range(5, 101))
    args = parser.parse_args()
    result = measure(args.output, trials=args.trials)
    print(
        json.dumps(
            {
                "completed_sizes": [
                    row["target_boundaries"] for row in result["attempts"] if row["completed"]
                ]
            }
        )
    )
    raise SystemExit(0 if all(row["completed"] for row in result["attempts"]) else 1)
