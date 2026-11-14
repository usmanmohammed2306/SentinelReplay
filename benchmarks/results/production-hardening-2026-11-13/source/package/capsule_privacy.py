"""Authenticated portable encryption; signatures still establish separate authorship."""

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sentinel_replay.capsule import MAX_ARCHIVE_BYTES, verify_capsule_bytes
from sentinel_replay.local_anchor import _fsync_directory, _regular_bytes, _write_new

MAGIC = b"SENTINEL-SEALED-CAPSULE-1\x00"
MAX_SEALED_BYTES = MAX_ARCHIVE_BYTES + len(MAGIC) + 8 + 12 + 16


def _key(path: Path) -> bytes:
    value = _regular_bytes(path, 32, private=True)
    if len(value) != 32:
        raise ValueError("capsule encryption requires a private32-byte AES key")
    return value


def seal(data: bytes, key_path: Path) -> bytes:
    verify_capsule_bytes(data)
    header = MAGIC + len(data).to_bytes(8, "big")
    nonce = os.urandom(12)
    return header + nonce + AESGCM(_key(key_path)).encrypt(nonce, data, header)


def unseal(data: bytes, key_path: Path) -> bytes:
    header_size = len(MAGIC) + 8
    if not header_size + 28 <= len(data) <= MAX_SEALED_BYTES or not data.startswith(MAGIC):
        raise ValueError("invalid sealed capsule envelope")
    length = int.from_bytes(data[len(MAGIC) : header_size], "big")
    if length > MAX_ARCHIVE_BYTES or len(data) != header_size + 28 + length:
        raise ValueError("invalid sealed capsule length")
    header = data[:header_size]
    nonce = data[header_size : header_size + 12]
    try:
        plain = AESGCM(_key(key_path)).decrypt(nonce, data[header_size + 12 :], header)
    except InvalidTag as error:
        raise ValueError("sealed capsule failed authentication") from error
    verify_capsule_bytes(plain)
    return plain


def write_private(path: Path, data: bytes) -> None:
    if not path.parent.is_dir():
        raise ValueError("private output requires an existing directory")
    _write_new(path, data, 0o600)
    _fsync_directory(path.parent)
