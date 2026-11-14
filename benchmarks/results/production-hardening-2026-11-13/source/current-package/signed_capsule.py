"""Detached development signatures over complete, verified capsule bytes.

This does not establish key isolation, freshness, or confidentiality. The signer
must eventually run beyond the agent's operating-system identity and sandbox.
"""

import base64
import re
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import canonical_bytes, load_json_unique
from sentinel_replay.capsule import (
    MAX_ARCHIVE_BYTES,
    CapsuleError,
    CapsuleVerification,
    import_capsule_bytes,
    read_capsule_bytes,
    verify_capsule_bytes,
)
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.local_anchor import (
    LocalAnchorError,
    _fsync_directory,
    _outside_agent,
    _regular_bytes,
    _write_new,
    load_local_private_key,
)

_DOMAIN = b"sentinel-replay:local-capsule:v1\x00"
_CAPSULE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
MAX_CAPSULE_ATTESTATION_BYTES = 8 * 1024


class SignedCapsuleError(ValueError):
    """The capsule or its development signing placement is invalid."""


class CapsuleAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    records: int = Field(ge=0)
    root: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    capsule_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    key_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    algorithm: Literal["Ed25519"] = "Ed25519"
    signature_b64: str

    def signed_fields(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "records": self.records,
            "root": self.root,
            "capsule_digest": self.capsule_digest,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }


def _message(fields: dict[str, object]) -> bytes:
    return _DOMAIN + canonical_bytes(fields)


def _read_candidate(path: Path) -> bytes:
    try:
        return read_capsule_bytes(path)
    except CapsuleError as error:
        raise SignedCapsuleError(str(error)) from error


def _prepare_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o022:
        raise SignedCapsuleError("attestation directory must be real and not group/world writable")


def sign_capsule(
    capsule_path: Path, private_path: Path, anchor_root: Path, agent_root: Path
) -> Path:
    """Validate then sign exact archive bytes; publish a put-once detached statement."""
    if not _CAPSULE_NAME.fullmatch(capsule_path.name):
        raise SignedCapsuleError("invalid capsule filename")
    try:
        capsule_data = read_capsule_bytes(capsule_path)
        result = verify_capsule_bytes(capsule_data)
        private = load_local_private_key(private_path, agent_root)
        _outside_agent(anchor_root, agent_root)
    except (CapsuleError, LocalAnchorError) as error:
        raise SignedCapsuleError(str(error)) from error
    key_id = blob_digest(private.public_key().public_bytes_raw())
    capsule_digest = blob_digest(capsule_data)
    fields: dict[str, object] = {
        "schema_version": 1,
        "run_id": result.run_id,
        "records": result.records,
        "root": result.root,
        "capsule_digest": capsule_digest,
        "key_id": key_id,
        "algorithm": "Ed25519",
    }
    statement = CapsuleAttestation(
        run_id=result.run_id,
        records=result.records,
        root=result.root,
        capsule_digest=capsule_digest,
        key_id=key_id,
        signature_b64=base64.b64encode(private.sign(_message(fields))).decode("ascii"),
    )
    run_dir = anchor_root / "capsules" / result.run_id
    for directory in (anchor_root, anchor_root / "capsules", run_dir):
        _prepare_directory(directory)
    attestation_path = run_dir / (capsule_path.name + ".sig.json")
    payload = (statement.model_dump_json() + "\n").encode("utf-8")
    if len(payload) > MAX_CAPSULE_ATTESTATION_BYTES:
        raise SignedCapsuleError("capsule attestation exceeds byte limit")
    _write_new(attestation_path, payload, 0o600)
    _fsync_directory(run_dir)
    return attestation_path


def _verify_signed_bytes(data: bytes, attestation_path: Path, public_path: Path) -> bool:
    raw_statement = _regular_bytes(attestation_path, MAX_CAPSULE_ATTESTATION_BYTES)
    public_raw = _regular_bytes(public_path, 32)
    return verify_signed_capsule_material(data, raw_statement, public_raw)


def verify_signed_capsule_material(data: bytes, raw_statement: bytes, public_raw: bytes) -> bool:
    """Verify complete archive bytes against a server-selected trusted public key."""
    try:
        if (
            len(data) > MAX_ARCHIVE_BYTES
            or len(raw_statement) > MAX_CAPSULE_ATTESTATION_BYTES
            or len(public_raw) != 32
        ):
            raise SignedCapsuleError("invalid attestation or public key size")
        statement = CapsuleAttestation.model_validate(
            load_json_unique(raw_statement.decode("utf-8"))
        )
        public = Ed25519PublicKey.from_public_bytes(public_raw)
        key_id = blob_digest(public_raw)
    except (CapsuleError, LocalAnchorError, UnicodeDecodeError, ValueError) as error:
        raise SignedCapsuleError(str(error)) from error
    if statement.capsule_digest != blob_digest(data) or statement.key_id != key_id:
        return False
    try:
        signature = base64.b64decode(statement.signature_b64, validate=True)
        public.verify(signature, _message(statement.signed_fields()))
    except (InvalidSignature, ValueError):
        return False
    # Authenticate the bounded opaque archive before parsing its members/journal.
    # A token without the trusted signing key cannot trigger expensive decoding.
    try:
        result = verify_capsule_bytes(data)
    except CapsuleError as error:
        raise SignedCapsuleError(str(error)) from error
    return (
        statement.run_id == result.run_id
        and statement.records == result.records
        and statement.root == result.root
    )


def verify_signed_capsule(capsule_path: Path, attestation_path: Path, public_path: Path) -> bool:
    """Verify the archive itself, its exact signed digest, and a supplied trusted key."""
    return _verify_signed_bytes(_read_candidate(capsule_path), attestation_path, public_path)


def import_signed_capsule(
    capsule_path: Path, attestation_path: Path, public_path: Path, destination: Path
) -> CapsuleVerification:
    """Authenticate a bounded archive and import those exact bytes, not a path re-read."""
    data = _read_candidate(capsule_path)
    if not _verify_signed_bytes(data, attestation_path, public_path):
        raise SignedCapsuleError("invalid capsule signature")
    return import_capsule_bytes(data, destination)
