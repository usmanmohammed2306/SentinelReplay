import json
import sys
from pathlib import Path
from runpy import run_path

execute = run_path(str(Path(__file__).parent.parent / "scripts/run_validation.py"))["execute"]


def test_actual_command_receipt_binds_output_log_and_source_changes(tmp_path: Path) -> None:
    source = tmp_path / "src/example.py"
    source.parent.mkdir()
    source.write_text("initial = True\n")
    artifact = tmp_path / "result.json"
    receipt = execute(
        tmp_path,
        tmp_path / "first",
        artifact,
        [sys.executable, "-c", "print('validation output')"],
        summary=True,
    )
    assert receipt["exit_code"] == 0
    assert receipt["source_root_before"] == receipt["source_root_after"]
    assert receipt["artifact"]["path"] == "result.json"
    assert (tmp_path / receipt["log"]["path"]).read_text() == "validation output\n"
    assert json.loads(artifact.read_text())["exit_code"] == 0
    changed = execute(
        tmp_path,
        tmp_path / "second",
        None,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('src/example.py').write_text('changed = True\\n')",
        ],
    )
    assert changed["command_exit_code"] == 0
    assert changed["exit_code"] == 3
    assert changed["source_root_before"] != changed["source_root_after"]


def test_failed_command_is_retained_and_never_promoted(tmp_path: Path) -> None:
    receipt = execute(
        tmp_path, tmp_path / "failure", None, [sys.executable, "-c", "raise SystemExit(7)"]
    )
    assert receipt["exit_code"] == 7
    assert json.loads((tmp_path / "failure/receipt.json").read_text())["exit_code"] == 7
