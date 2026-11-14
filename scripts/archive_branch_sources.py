"""Archive only source bytes matching a frozen branch experiment definition."""

import argparse
import json
from pathlib import Path

from sentinel_replay.evidence_store import blob_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=Path)
    args = parser.parse_args()
    definition = json.loads((args.experiment / "definition.json").read_text())
    source_root = Path(__file__).resolve().parents[1] / "src" / "sentinel_replay"
    archive = args.experiment / "source"
    archive.mkdir(exist_ok=False)
    matched, unavailable = [], []
    for name, expected in definition["source_digests"].items():
        if Path(name).name != name or not name.endswith(".py"):
            raise ValueError("source name is outside the declared Python module set")
        data = (source_root / name).read_bytes()
        if blob_digest(data) != expected:
            unavailable.append(name)
            continue
        (archive / name).write_bytes(data)
        matched.append(name)
    result = {"matched": matched, "unavailable_at_archive_time": unavailable}
    (archive / "archive-status.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
