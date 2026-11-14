from pathlib import Path

import pytest

from sentinel_replay.capsule import export_capsule
from sentinel_replay.capsule_privacy import seal, unseal, write_private
from sentinel_replay.journal import Journal


def test_portable_encryption_authenticates_key_header_and_bytes(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    Journal(journal).append({"synthetic_secret": "fixture-only-sensitive-marker"})
    capsule = tmp_path / "incident.sentinel"
    export_capsule("private-fixture", journal, capsule)
    key = tmp_path / "storage.key"
    write_private(key, b"s" * 32)
    data = seal(capsule.read_bytes(), key)
    assert b"fixture-only-sensitive-marker" not in data
    assert unseal(data, key) == capsule.read_bytes()
    wrong = tmp_path / "wrong.key"
    write_private(wrong, b"w" * 32)
    with pytest.raises(ValueError, match="authentication"):
        unseal(data, wrong)
    for changed in (data[:-1], data + b"trailing", data[:-1] + bytes([data[-1] ^ 1])):
        with pytest.raises(ValueError):
            unseal(changed, key)
    with pytest.raises(FileExistsError):
        write_private(key, b"cannot-overwrite")
