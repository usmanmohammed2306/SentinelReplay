"""Development Ed25519 root attestations outside a declared agent workspace.

Filesystem placement alone is not a production isolation boundary. A future
deployment must run the agent under a distinct identity and test denial.
"""

import base64
import os
import re
import stat
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import canonical_bytes, load_json_unique
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import Verification

_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_ROOT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DOMAIN = b"sentinel-replay:local-root:v1\x00"
MAX_ATTESTATION_BYTES = 8 * 1024


class LocalAnchorError(ValueError):
    """Key, attestation, or filesystem trust declaration is invalid."""


class LocalAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    records: int = Field(ge=0)
    root: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    key_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    algorithm: Literal["Ed25519"] = "Ed25519"
    signature_b64: str

    def signed_fields(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "records": self.records,
            "root": self.root,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }


def _outside_agent(path: Path, agent_root: Path) -> None:
    resolved_agent = agent_root.resolve(strict=True)
    if not agent_root.is_dir() or agent_root.is_symlink():
        raise LocalAnchorError("agent root must be a real directory")
    resolved_path = path.resolve()
    if resolved_path == resolved_agent or resolved_path.is_relative_to(resolved_agent):
        raise LocalAnchorError("controller evidence must be outside the agent workspace")


def _regular_bytes(path: Path, limit: int, *, private: bool = False) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalAnchorError("key or attestation must be a regular file")
        if private and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
            raise LocalAnchorError("private key must be owned by this user and mode 0600")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise LocalAnchorError("key or attestation exceeds byte limit")
        return data
    finally:
        os.close(descriptor)


def _write_new(path: Path, data: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(data)
            destination.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_keypair(controller_root: Path, agent_root: Path) -> tuple[Path, Path]:
    """Create development keys in a new private controller directory."""
    _outside_agent(controller_root, agent_root)
    controller_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    if controller_root.is_symlink() or controller_root.stat().st_mode & 0o077:
        raise LocalAnchorError("controller directory must be private")
    private = Ed25519PrivateKey.generate()
    private_path = controller_root / "signing.ed25519.key"
    public_path = controller_root / "signing.ed25519.pub"
    _write_new(private_path, private.private_bytes_raw(), 0o600)
    _write_new(public_path, private.public_key().public_bytes_raw(), 0o644)
    _fsync_directory(controller_root)
    return private_path, public_path


def _message(fields: dict[str, object]) -> bytes:
    return _DOMAIN + canonical_bytes(fields)


def load_local_public_key(path: Path) -> tuple[Ed25519PublicKey, str]:
    data = _regular_bytes(path, 32)
    if len(data) != 32:
        raise LocalAnchorError("public key must be 32 bytes")
    return Ed25519PublicKey.from_public_bytes(data), blob_digest(data)


def load_local_private_key(path: Path, agent_root: Path) -> Ed25519PrivateKey:
    """Load a development key only when it is outside the declared agent root."""
    _outside_agent(path, agent_root)
    data = _regular_bytes(path, 32, private=True)
    if len(data) != 32:
        raise LocalAnchorError("private key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(data)


def sign_root(
    run_id: str, verification: Verification, private_path: Path, agent_root: Path
) -> LocalAttestation:
    """Sign one exact root; key placement is checked but isolation is not proven."""
    if not _RUN_ID.fullmatch(run_id) or not _ROOT.fullmatch(verification.root):
        raise LocalAnchorError("invalid run ID or journal root")
    private = load_local_private_key(private_path, agent_root)
    key_id = blob_digest(private.public_key().public_bytes_raw())
    fields: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "records": verification.records,
        "root": verification.root,
        "key_id": key_id,
        "algorithm": "Ed25519",
    }
    signature = private.sign(_message(fields))
    return LocalAttestation(
        run_id=run_id,
        records=verification.records,
        root=verification.root,
        key_id=key_id,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


def verify_signature(attestation: LocalAttestation, public_path: Path) -> bool:
    public, key_id = load_local_public_key(public_path)
    if key_id != attestation.key_id:
        return False
    try:
        signature = base64.b64decode(attestation.signature_b64, validate=True)
        public.verify(signature, _message(attestation.signed_fields()))
    except (InvalidSignature, ValueError):
        return False
    return True


def publish_anchor(attestation: LocalAttestation, anchor_root: Path, agent_root: Path) -> Path:
    """Publish a put-once local attestation outside the declared agent workspace."""
    _outside_agent(anchor_root, agent_root)
    anchor_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if anchor_root.is_symlink() or anchor_root.stat().st_mode & 0o022:
        raise LocalAnchorError("anchor directory must not be group/world writable")
    run_dir = anchor_root / attestation.run_id
    run_dir.mkdir(mode=0o700, exist_ok=True)
    if run_dir.is_symlink() or run_dir.stat().st_mode & 0o022:
        raise LocalAnchorError("run anchor directory must not be group/world writable")
    path = run_dir / f"{attestation.root.removeprefix('sha256:')}.json"
    data = (attestation.model_dump_json() + "\n").encode("utf-8")
    if len(data) > MAX_ATTESTATION_BYTES:
        raise LocalAnchorError("attestation exceeds byte limit")
    _write_new(path, data, 0o600)
    _fsync_directory(run_dir)
    _fsync_directory(anchor_root)
    return path


def verify_anchor(
    run_id: str, verification: Verification, public_path: Path, anchor_root: Path
) -> bool:
    """Check the expected root, exact anchor path, key identity, and signature."""
    if not _RUN_ID.fullmatch(run_id) or not _ROOT.fullmatch(verification.root):
        raise LocalAnchorError("invalid run ID or journal root")
    run_dir = anchor_root / run_id
    for directory in (anchor_root, run_dir):
        if directory.is_symlink() or not directory.is_dir():
            raise LocalAnchorError("anchor path must contain real directories")
        if directory.stat().st_mode & 0o022:
            raise LocalAnchorError("anchor directory must not be group/world writable")
    path = run_dir / f"{verification.root.removeprefix('sha256:')}.json"
    data = _regular_bytes(path, MAX_ATTESTATION_BYTES)
    try:
        attestation = LocalAttestation.model_validate(load_json_unique(data.decode("utf-8")))
    except (UnicodeDecodeError, ValueError) as error:
        raise LocalAnchorError(f"invalid local attestation: {error}") from error
    return (
        attestation.run_id == run_id
        and attestation.records == verification.records
        and attestation.root == verification.root
        and verify_signature(attestation, public_path)
    )
