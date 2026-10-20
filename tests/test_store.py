from pathlib import Path

import pytest

from sentinel_replay.evidence_store import BlobCorruption, FileEvidenceStore


def test_blob_read_and_existing_put_reject_symlink_substitution(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path / "blobs")
    ref = store.put(b"trusted")
    target = store._path(ref.digest)
    target.unlink()
    unrelated = tmp_path / "outside"
    unrelated.write_bytes(b"trusted")
    target.symlink_to(unrelated)
    with pytest.raises(BlobCorruption, match="regular file"):
        store.get(ref)
    with pytest.raises(BlobCorruption, match="regular file"):
        store.put(b"trusted")
