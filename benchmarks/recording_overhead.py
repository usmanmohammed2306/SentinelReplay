"""Paired finite-program overhead; no model latency is invented to dilute cost.

Both arms execute the same trusted interpreter, initial/final snapshots and real
local file effects. The unrecorded arm omits durable journal, telemetry and report
publication. This zero-work model stub is a deliberately harsh local CPU workload,
not representative live-agent overhead. Samples alternate order.
"""

import argparse
import json
import secrets
import statistics
import time
from pathlib import Path
from typing import Any

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.environment_pack import Pack, PackStep, _run, record_pack
from sentinel_replay.evidence_store import FileEvidenceStore, blob_digest
from sentinel_replay.policy_language import Action, Decision, Policy, Rule
from sentinel_replay.workspace_snapshot import capture_workspace, restore_workspace


def measure(output: Path, trials: int = 10) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    pack = Pack(
        name="overhead-zero-work-model-stub",
        files={"public.txt": "public"},
        steps=tuple(
            [
                PackStep(action=Action(operation="model_call"), value="frozen-stub")
                for _ in range(2999)
            ]
            + [
                PackStep(
                    action=Action(operation="write_file", resource="report.txt"),
                    value="public-report",
                )
            ]
        ),
    )
    policy = Policy(rules=(Rule(effect="allow"),))
    decisions: list[Decision] = ["allowed"] * len(pack.steps)
    sources = Path(__file__).resolve().parents[1] / "src/sentinel_replay"
    archive = output / "source"
    archive.mkdir()
    identities = {}
    for path in sorted(sources.glob("*.py")):
        identities[path.name] = blob_digest(path.read_bytes())
        (archive / path.name).write_bytes(path.read_bytes())
    (archive / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    rows = []
    for trial in range(trials):
        row: dict[str, Any] = {
            "trial": trial,
            "order": ["unrecorded", "recorded"] if trial % 2 == 0 else ["recorded", "unrecorded"],
        }
        for arm in row["order"]:
            root = output / f"trial-{trial:02}-{arm}"
            start = time.perf_counter()
            if arm == "recorded":
                report = record_pack(
                    pack,
                    root,
                    policy,
                    decisions=decisions,
                    decision_source="fixed_allow_vector_no_OPA_in_timed_region",
                )
                row["journal_root"] = report["journal_root"]
            else:
                root.mkdir()
                seed = root / "seed"
                seed.mkdir()
                for name, value in pack.files.items():
                    (seed / name).write_text(value)
                store = FileEvidenceStore(root / "blobs")
                initial = capture_workspace(seed, store)
                world = root / "world"
                restore_workspace(initial, world, store)
                sequence = 0

                def discard(
                    call_id: str,
                    request: dict[str, Any],
                    response: dict[str, Any],
                    evidence: dict[str, Any],
                ) -> int:
                    nonlocal sequence
                    sequence += 1
                    return sequence - 1

                _run(pack, world, store, decisions, discard, secrets.token_bytes(32))
                capture_workspace(world, store)
            row[arm + "_seconds"] = time.perf_counter() - start
            if (root / "world/report.txt").read_text() != "public-report":
                raise ValueError("benchmark arms did not preserve the same legitimate task")
        row["overhead_percent"] = 100 * (row["recorded_seconds"] / row["unrecorded_seconds"] - 1)
        rows.append(row)
    small = pack.model_copy(
        update={"name": "localization-baseline", "steps": pack.steps[:127] + pack.steps[-1:]}
    )
    source = output / "localization-source"
    record_pack(small, source, policy, decisions=["allowed"] * len(small.steps))
    localization = localize_pack(
        source,
        output / "localization",
        FilePredicate(kind="file_exists", path="report.txt"),
        measure_linear=True,
    )
    result = {
        "schema_version": 1,
        "source_digests": identities,
        "trials": trials,
        "program_steps": len(pack.steps),
        "samples": rows,
        "median_overhead_percent": statistics.median(row["overhead_percent"] for row in rows),
        "localization": localization,
        "scope": __doc__,
        "progress_signing": "not_enabled_in_either_arm",
    }
    (output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.output)
    print(
        json.dumps(
            {
                "trials": result["trials"],
                "median_overhead_percent": result["median_overhead_percent"],
                "binary_restores": result["localization"]["binary_restores"],
                "linear_restores": result["localization"]["linear_restores"],
            }
        )
    )
