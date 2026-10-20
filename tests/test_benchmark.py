import json
import subprocess
import sys
from pathlib import Path


def test_local_benchmark_reports_declared_graph_semantics() -> None:
    repository = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repository / "benchmarks" / "journal_scale.py"), "--events", "10"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == 2
    assert report["events"] == 10
    assert report["timeline_phases"] == 1
    assert report["provenance_edges"] == 9
    assert isinstance(report["provenance_seconds"], float)
    assert report["provenance_seconds"] >= 0


def test_repeated_runner_retains_raw_isolated_trials(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    output = tmp_path / "repeated.json"
    subprocess.run(
        [
            sys.executable,
            str(repository / "benchmarks" / "repeat_journal_scale.py"),
            "--events",
            "10",
            "--trials",
            "3",
            "--output",
            str(output),
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text())
    assert len(report["raw_trials"]) == 6
    assert report["summary"]["batch"]["trials"] == 3
    assert report["summary"]["stream"]["trials"] == 3
    assert {trial["result"]["root"] for trial in report["raw_trials"]} == {
        report["journal_root_all_trials"]
    }


def test_strategy_comparison_retains_same_evidence_root(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    output = tmp_path / "comparison.json"
    subprocess.run(
        [
            sys.executable,
            str(repository / "benchmarks" / "compare_journal_batch.py"),
            "--events",
            "10",
            "--trials",
            "3",
            "--output",
            str(output),
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text())
    assert len(report["raw_trials"]) == 6
    assert {trial["strategy"] for trial in report["raw_trials"]} == {
        "legacy_join",
        "current_chunked",
    }
    assert {trial["result"]["root"] for trial in report["raw_trials"]} == {
        report["journal_root_all_trials"]
    }
