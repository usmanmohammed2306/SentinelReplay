import json
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

from sentinel_replay.canonical import canonical_bytes


def test_v1_canonical_wire_vectors_preserve_historical_hash_inputs() -> None:
    values = [
        None,
        True,
        1,
        "1",
        -(2**100),
        'λ\n"',
        b"\x00\xff",
        [1, False, None],
        {"z": [], "a": {"value": 3}},
        datetime(2026, 1, 1, tzinfo=UTC),
        HTTPStatus.OK,
    ]
    expected = json.loads((Path(__file__).parent / "fixtures/canonical-v1.json").read_text())
    assert [canonical_bytes(value).decode() for value in values] == expected
