import json
from pathlib import Path

import pytest

from sentinel_replay.blob_bank import restore_blob_bank, write_blob_bank
from sentinel_replay.evidence_store import FileEvidenceStore, blob_digest


def test_blob_bank_shards_parts_and_many_files_round_trip(tmp_path: Path) -> None:
    source = FileEvidenceStore(tmp_path / "source", max_bytes=32 * 1024 * 1024)
    values = [b"", b"x" * (17 * 1024 * 1024)] + [f"file-{i}".encode() for i in range(1000)]
    refs = [source.put(value) for value in values]
    shards = tmp_path / "shards"
    shards.mkdir()
    artifacts = {
        name: path.read_bytes() for name, path in write_blob_bank(source.root, shards).items()
    }
    assert 1 < len(artifacts) < 64
    destination = FileEvidenceStore(tmp_path / "restored", max_bytes=32 * 1024 * 1024)
    assert restore_blob_bank(artifacts, destination) == {ref.digest for ref in refs}
    assert [destination.get(ref) for ref in refs] == values


@pytest.mark.parametrize(
    "change", ["truncated", "digest", "offset", "boolean", "missing_shard", "duplicate"]
)
def test_blob_bank_rejects_malformed_frames(tmp_path: Path, change: str) -> None:
    header = {"digest": blob_digest(b"test"), "size": 4, "offset": 0, "part_size": 4}
    value = b"test"
    name = "checkpoint-blobs-000.bin"
    if change == "truncated":
        value = b"tes"
    elif change == "digest":
        header["digest"] = blob_digest(b"else")
    elif change == "offset":
        header["offset"] = 1
    elif change == "boolean":
        header["size"] = True
    elif change == "missing_shard":
        name = "checkpoint-blobs-001.bin"
    frame = json.dumps(header).encode() + b"\n" + value
    if change == "duplicate":
        frame += frame
    with pytest.raises(ValueError):
        restore_blob_bank({name: frame}, FileEvidenceStore(tmp_path / "restored"))
