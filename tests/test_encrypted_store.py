import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sentinel_replay.encrypted_store import EncryptedEvidenceStore
from sentinel_replay.evidence_store import BlobCorruption


def make_key(path: Path) -> Path:
    path.touch(mode=0o600)
    path.write_bytes(os.urandom(32))
    return path


@given(st.binary(max_size=2048))
@settings(max_examples=15)
def test_authenticated_round_trip_with_no_plaintext_storage(data: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = EncryptedEvidenceStore(root / "evidence", make_key(root / "key"))
        reference = store.put(data)
        assert store.get(reference) == data
        assert store.put(data) == reference
        if len(data) >= 16:
            assert all(
                data not in path.read_bytes() for path in store.root.rglob("*") if path.is_file()
            )


def test_wrong_key_tamper_and_unsafe_key_placement_fail_closed(tmp_path: Path) -> None:
    key = make_key(tmp_path / "key")
    store = EncryptedEvidenceStore(tmp_path / "evidence", key)
    reference = store.put(b"private-synthetic-canary-value")
    other = EncryptedEvidenceStore(store.root, make_key(tmp_path / "other-key"))
    with pytest.raises(BlobCorruption):
        other.get(reference)
    path = next((store.root / "ciphertext/sha256").glob("*/*"))
    path.write_bytes(path.read_bytes()[:-1] + b"x")
    with pytest.raises(BlobCorruption):
        store.get(reference)
    key.chmod(0o644)
    with pytest.raises(ValueError):
        EncryptedEvidenceStore(store.root, key)
    nested = make_key(store.root / "nested-key")
    with pytest.raises(ValueError, match="outside"):
        EncryptedEvidenceStore(store.root, nested)
