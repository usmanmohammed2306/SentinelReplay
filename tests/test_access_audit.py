from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sentinel_replay.access_audit import AccessAudit
from sentinel_replay.journal import Journal


def test_request_threads_preserve_one_durable_chain_and_reopen_existing_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "access.jsonl"
    audit = AccessAudit(path)
    try:
        audit.start()
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(
                workers.map(
                    lambda index: audit.append({"subject": "synthetic", "request": index}),
                    range(100),
                )
            )
    finally:
        audit.close()
    events, verified = Journal(path).read_verified()
    assert verified.records == 100
    assert {event["request"] for event in events if isinstance(event, dict)} == set(range(100))
    try:
        audit.start()
        audit.append({"kind": "restart"})
    finally:
        audit.close()
    assert Journal(path).verify().records == 101
