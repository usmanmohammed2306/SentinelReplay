"""Bounded checkpoint blob frames inside ordinary capsule artifacts.

Sharding avoids one archive member per workspace file. Readers support earlier
single-blob members, validate every part and digest, and buffer at most one
32MiB object. Frames contain data only; no paths or executable instructions.
"""

import io
import json
import re
from pathlib import Path

from sentinel_replay.canonical import load_json_unique
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore

MAX_BLOB = 32 * 1024 * 1024
PART_BYTES = 8 * 1024 * 1024
SHARD_BYTES = 16 * 1024 * 1024 + 4096


def write_blob_bank(source: Path, destination: Path) -> dict[str, Path]:
    store = FileEvidenceStore(source, max_bytes=MAX_BLOB)
    artifacts: dict[str, Path] = {}
    buffer = bytearray()

    def flush() -> None:
        if not buffer:
            return
        name = f"checkpoint-blobs-{len(artifacts):03d}.bin"
        path = destination / name
        path.write_bytes(buffer)
        artifacts[name] = path
        buffer.clear()

    paths = sorted((source / "sha256").glob("*/*"))
    if len(paths) > 4096:
        raise ValueError("checkpoint blob inventory exceeds budget")
    for path in paths:
        ref = BlobRef("sha256:" + path.name, path.stat().st_size)
        data = store.get(ref)
        for offset in range(0, max(1, ref.size), PART_BYTES):
            part = data[offset : offset + PART_BYTES]
            header = (
                json.dumps(
                    {
                        "digest": ref.digest,
                        "size": ref.size,
                        "offset": offset,
                        "part_size": len(part),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
                + b"\n"
            )
            if len(buffer) + len(header) + len(part) > SHARD_BYTES:
                flush()
            buffer.extend(header)
            buffer.extend(part)
    flush()
    return artifacts


def restore_blob_bank(artifacts: dict[str, bytes], store: FileEvidenceStore) -> set[str]:
    seen: set[str] = set()
    for name, value in artifacts.items():
        if name.startswith("blob-"):
            expected = "sha256:" + name[5:]
            BlobRef(expected, len(value))
            if store.put(value).digest != expected:
                raise ValueError("checkpoint blob identity differs")
            seen.add(expected)
    current: dict[str, object] | None = None
    buffer = bytearray()
    banks = sorted(name for name in artifacts if name.startswith("checkpoint-blobs-"))
    if banks != [f"checkpoint-blobs-{index:03d}.bin" for index in range(len(banks))]:
        raise ValueError("checkpoint blob shards are missing or malformed")
    for name in banks:
        source = io.BytesIO(artifacts[name])
        while source.tell() < len(artifacts[name]):
            line = source.readline(513)
            if len(line) > 512 or not line.endswith(b"\n"):
                raise ValueError("invalid blob-frame header")
            header = load_json_unique(line.decode())
            if not isinstance(header, dict) or set(header) != {
                "digest",
                "size",
                "offset",
                "part_size",
            }:
                raise ValueError("invalid blob-frame fields")
            if any(type(header[key]) is not int for key in ("size", "offset", "part_size")):
                raise ValueError("blob frame lengths must be integers")
            digest = header["digest"]
            size = header["size"]
            offset = header["offset"]
            part_size = header["part_size"]
            if (
                not isinstance(size, int)
                or not isinstance(offset, int)
                or not isinstance(part_size, int)
            ):
                raise ValueError("blob frame lengths must be integers")
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
                or not 0 <= size <= MAX_BLOB
                or not 0 <= part_size <= PART_BYTES
                or offset + part_size > size
                or (part_size == 0 and size != 0)
            ):
                raise ValueError("blob-frame bounds or digest are invalid")
            if current is None:
                if offset != 0 or digest in seen or len(seen) >= 4096:
                    raise ValueError("duplicate, excessive or out-of-order checkpoint blob")
                current = {"digest": digest, "size": size}
            if current != {"digest": digest, "size": size} or offset != len(buffer):
                raise ValueError("noncontiguous checkpoint blob parts")
            data = source.read(part_size)
            if len(data) != part_size:
                raise ValueError("truncated checkpoint blob part")
            buffer.extend(data)
            if len(buffer) == size:
                if store.put(bytes(buffer)).digest != digest:
                    raise ValueError("checkpoint blob digest mismatch")
                seen.add(digest)
                buffer.clear()
                current = None
    if current is not None:
        raise ValueError("checkpoint blob is incomplete")
    return seen
