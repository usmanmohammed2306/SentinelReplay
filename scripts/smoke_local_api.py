"""Exercise the localhost API with a synthetic signed capsule; print no payloads."""

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("smoke test is restricted to a localhost HTTP API")
    token = os.environ.get("SENTINEL_API_TOKEN")
    if token is None or len(token) < 32:
        parser.error("SENTINEL_API_TOKEN must be set to the local API token")
    with urlopen(args.base_url + "/healthz", timeout=5) as response:
        if json.load(response) != {"status": "ok"}:
            raise RuntimeError("API health response differed from the expected contract")
    request = Request(
        args.base_url + "/v1/runs/import",
        data=args.capsule.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Sentinel-Attestation": base64.b64encode(args.attestation.read_bytes()).decode(),
        },
    )
    with urlopen(request, timeout=20) as response:
        if response.status not in {200, 201}:
            raise RuntimeError("signed import did not succeed")
        imported = json.load(response)
    lookup = Request(
        args.base_url + "/v1/runs/" + imported["run_id"],
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(lookup, timeout=5) as response:
        retrieved = json.load(response)
    if retrieved != imported:
        raise RuntimeError("retrieved run differs from imported metadata")
    archive = Request(
        args.base_url + "/v1/runs/" + imported["run_id"] + "/capsule",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(archive, timeout=20) as response:
        if response.read() != args.capsule.read_bytes():
            raise RuntimeError("retrieved capsule differs from imported archive")
    print(
        f"LOCAL_API_SMOKE_OK run={imported['run_id']} records={imported['records']} "
        f"root={imported['journal_root']}"
    )


if __name__ == "__main__":
    main()
