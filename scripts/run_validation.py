"""Run an explicit local validation command and bind its receipt to source bytes.

Command arguments and output must contain no credentials. Logs stay private.
No shell is used and no successful result is inferred from an interrupted run.
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from sentinel_replay.canonical import event_digest
from sentinel_replay.release_audit import source_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not command or not output.is_relative_to(root / ".local-controller"):
        parser.error("explicit command and fresh private output directory required")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    sources = source_inventory(root)
    (output / "source-files.json").write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n")
    started, started_at = time.perf_counter(), datetime.now(UTC).isoformat()
    with (output / "command.log").open("xb") as log:
        result = subprocess.run(command, cwd=root, stdout=log, stderr=log, check=False)
    stable = sources == source_inventory(root)
    receipt = {
        "schema_version": 1,
        "command": command,
        "source_root": event_digest(sources),
        "exit_code": result.returncode if stable else 3,
        "command_exit_code": result.returncode,
        "source_unchanged": stable,
        "started_at_utc": started_at,
        "elapsed_seconds": time.perf_counter() - started,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))
    return int(receipt["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
