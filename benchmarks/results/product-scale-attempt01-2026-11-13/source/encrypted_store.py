"""AES-256-GCM envelope storage with plaintext content identities.

The encryption key must live outside the evidence/backup root. The untrusted
index selects a ciphertext CAS object; AAD binds its plaintext digest and size,
so substituting another valid ciphertext cannot satisfy the requested reference.
Host/key compromise and authoritative freshness remain separate guarantees.
"""

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sentinel_replay.canonical import load_json_unique
from sentinel_replay.evidence_store import (
    DEFAULT_MAX_BLOB_BYTES,
    BlobCorruption,
    BlobRef,
    FileEvidenceStore,
    blob_digest,
    check_blob,
)
from sentinel_replay.local_anchor import _regular_bytes

_MAGIC = b"SENTINEL-GCM-1\x00"


class EncryptedEvidenceStore:
    def __init__(
        self, root: Path, key_path: Path, *, max_bytes: int = DEFAULT_MAX_BLOB_BYTES
    ) -> None:
        if key_path.resolve().is_relative_to(root.resolve()):
            raise ValueError("encryption key must be outside the evidence root")
        key = _regular_bytes(key_path, 33, private=True)
        if len(key) != 32:
            raise ValueError("AES-256 evidence key must be exactly 32 bytes")
        self.root, self.max_bytes = root, max_bytes
        self.cipher = AESGCM(key)
        self.objects = FileEvidenceStore(root / "ciphertext", max_bytes=max_bytes + 128)

    def _index(self, ref: BlobRef) -> Path:
        return self.root / "refs" / ref.digest.removeprefix("sha256:")

    @staticmethod
    def _aad(ref: BlobRef) -> bytes:
        return _MAGIC + ref.digest.encode() + str(ref.size).encode()

    def put(self, data: bytes) -> BlobRef:
        if len(data) > self.max_bytes:
            raise ValueError("blob exceeds configured maximum")
        ref = BlobRef(blob_digest(data), len(data))
        index = self._index(ref)
        if index.exists() or index.is_symlink():
            check_blob(self.get(ref), ref)
            return ref
        nonce = os.urandom(12)
        ciphertext = _MAGIC + nonce + self.cipher.encrypt(nonce, data, self._aad(ref))
        cipher_ref = self.objects.put(ciphertext)
        index.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        encoded = json.dumps({"digest": cipher_ref.digest, "size": cipher_ref.size}).encode()
        with tempfile.NamedTemporaryFile(dir=index.parent, delete=False) as temporary:
            path = Path(temporary.name)
            try:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                with suppress(FileExistsError):
                    os.link(path, index)
                descriptor = os.open(index.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                path.unlink(missing_ok=True)
        check_blob(self.get(ref), ref)
        return ref

    def get(self, ref: BlobRef) -> bytes:
        if ref.size > self.max_bytes:
            raise BlobCorruption("blob exceeds configured maximum")
        try:
            index = load_json_unique(_regular_bytes(self._index(ref), 1024).decode())
            if not isinstance(index, dict) or set(index) != {"digest", "size"}:
                raise BlobCorruption("invalid ciphertext reference")
            ciphertext = self.objects.get(BlobRef(index["digest"], index["size"]))
            if not ciphertext.startswith(_MAGIC) or len(ciphertext) < len(_MAGIC) + 28:
                raise BlobCorruption("invalid ciphertext envelope")
            nonce = ciphertext[len(_MAGIC) : len(_MAGIC) + 12]
            data = self.cipher.decrypt(nonce, ciphertext[len(_MAGIC) + 12 :], self._aad(ref))
        except (InvalidTag, TypeError, ValueError) as error:
            raise BlobCorruption("encrypted evidence failed authentication") from error
        check_blob(data, ref)
        return data
