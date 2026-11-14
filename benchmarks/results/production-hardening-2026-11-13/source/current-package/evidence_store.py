"""Content-addressed evidence with the same digest contract across backends."""

import errno
import hashlib
import os
import re
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_BLOB_BYTES = 8 * 1024 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class BlobCorruption(ValueError):
    """A stored blob does not match its claimed digest or size."""


@dataclass(frozen=True)
class BlobRef:
    digest: str
    size: int
    version_id: str | None = None

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.digest) or self.size < 0:
            raise ValueError("invalid blob reference")


def blob_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def check_blob(data: bytes, ref: BlobRef) -> None:
    if len(data) != ref.size:
        raise BlobCorruption("blob size mismatch")
    if blob_digest(data) != ref.digest:
        raise BlobCorruption("blob digest mismatch")


class FileEvidenceStore:
    """Local foundation store; a trusted root and external anchor are separate concerns."""

    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> None:
        if max_bytes < 1:
            raise ValueError("maximum blob size must be positive")
        self.root = root
        self.max_bytes = max_bytes

    def _path(self, digest: str) -> Path:
        if not _DIGEST.fullmatch(digest):
            raise ValueError("invalid blob digest")
        hexadecimal = digest.removeprefix("sha256:")
        return self.root / "sha256" / hexadecimal[:2] / hexadecimal

    def put(self, data: bytes) -> BlobRef:
        if len(data) > self.max_bytes:
            raise ValueError("blob exceeds configured maximum")
        ref = BlobRef(blob_digest(data), len(data))
        destination = self._path(ref.digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Link a durable private temporary file into place without overwriting a prior blob.
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
                with suppress(FileExistsError):
                    os.link(temporary_path, destination)
                directory = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary_path.unlink(missing_ok=True)
        check_blob(self.get(ref), ref)
        return ref

    def get(self, ref: BlobRef) -> bytes:
        path = self._path(ref.digest)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise BlobCorruption("blob must be a regular file") from error
            raise
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise BlobCorruption("blob must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                data = source.read(self.max_bytes + 1)
        finally:
            os.close(descriptor)
        if len(data) > self.max_bytes:
            raise BlobCorruption("blob exceeds configured maximum")
        check_blob(data, ref)
        return data
