"""Run an explicit local validation and retain its source, log and output bindings.

This is an execution receipt, not independent reviewer identity or a signature.
Arguments and logs must be reviewed for secrets before publication. Never put a
credential in command arguments. Failed commands retain their nonzero receipt.
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel_replay.canonical import event_digest
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.release_audit import source_inventory


def execute(
    repository: Path,
    output: Path,
    artifact: Path | None,
    command: list[str],
    *,
    summary: bool = False,
) -> dict[str, Any]:
    if not command or not output.resolve().is_relative_to(repository.resolve()):
        raise ValueError("explicit command and repository-local receipt directory required")
    if artifact is not None and not artifact.resolve().is_relative_to(repository.resolve()):
        raise ValueError("artifact must be inside the repository")
    if summary and artifact is None:
        raise ValueError("summary requires an artifact destination")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    before = source_inventory(repository)
    (output / "source.json").write_text(json.dumps(before, indent=2, sort_keys=True) + "\n")
    start, started_at = time.perf_counter(), datetime.now(UTC).isoformat()
    with (output / "command.log").open("xb") as stream:
        result = subprocess.run(
            command,
            cwd=repository,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=1800,
        )
    after = source_inventory(repository)
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "command": command,
        "exit_code": result.returncode if before == after else 3,
        "command_exit_code": result.returncode,
        "started_at_utc": started_at,
        "elapsed_seconds": f"{time.perf_counter() - start:.9f}",
        "source_root": event_digest(before),
        "source_root_before": event_digest(before),
        "source_root_after": event_digest(after),
        "source_unchanged": before == after,
        "scope": "local execution receipt; no independent authentication of experimenter identity",
    }

    def reference(path: Path) -> dict[str, str]:
        return {"path": str(path.relative_to(repository)), "digest": blob_digest(path.read_bytes())}

    receipt["log"] = reference(output / "command.log")
    if summary and artifact is not None:
        with artifact.open("x") as summary_stream:
            summary_stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if artifact is not None and artifact.is_file():
        receipt["artifact"] = reference(artifact)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    receipt = execute(
        Path(__file__).resolve().parents[1],
        args.output.resolve(),
        args.artifact.resolve() if args.artifact else None,
        command,
        summary=args.summary,
    )
    print(
        json.dumps({key: receipt[key] for key in ("exit_code", "source_root", "source_unchanged")})
    )
    raise SystemExit(receipt["exit_code"] or (0 if receipt["source_unchanged"] else 1))
