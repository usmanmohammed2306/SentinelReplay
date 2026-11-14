"""Operator-held put-once capsule witnesses, mounted read-only in the controller.

The witness fixes one final capsule per run ID independently of the database and
CAS backup. It detects per-run equivocation relative to that retained witness;
it does not prove a global latest head or survive compromise of the host owner.
"""

import os
import stat
import tempfile
from pathlib import Path

from sentinel_replay.canonical import load_json_unique
from sentinel_replay.capsule import read_capsule_bytes
from sentinel_replay.local_anchor import (
    _fsync_directory,
    _outside_agent,
    _regular_bytes,
)
from sentinel_replay.signed_capsule import (
    MAX_CAPSULE_ATTESTATION_BYTES,
    CapsuleAttestation,
    verify_signed_capsule_material,
)


class WitnessError(ValueError):
    """An operator witness is missing, unsafe, malformed or inconsistent."""


def validate_witness_root(root: Path) -> None:
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
        raise WitnessError("witness root must be a real directory, not group/world writable")


def _statement(raw: bytes) -> CapsuleAttestation:
    if len(raw) > MAX_CAPSULE_ATTESTATION_BYTES:
        raise WitnessError("witness exceeds statement budget")
    return CapsuleAttestation.model_validate(load_json_unique(raw.decode()))


def require_witness(root: Path, raw: bytes) -> CapsuleAttestation:
    """Compare the full statement, including signature, against operator-held bytes."""
    try:
        validate_witness_root(root)
        expected = _statement(raw)
        observed = _statement(
            _regular_bytes(root / (expected.run_id + ".json"), MAX_CAPSULE_ATTESTATION_BYTES)
        )
        if observed != expected:
            raise WitnessError("capsule statement differs from operator witness")
        return observed
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise WitnessError("operator witness unavailable or inconsistent") from error


def publish_witness(
    capsule: Path, attestation: Path, public_key: Path, root: Path, agent_root: Path
) -> Path:
    """Operator command: authenticate before publishing, atomically and without replace."""
    _outside_agent(root, agent_root)
    raw = _regular_bytes(attestation, MAX_CAPSULE_ATTESTATION_BYTES)
    if not verify_signed_capsule_material(
        read_capsule_bytes(capsule), raw, _regular_bytes(public_key, 32)
    ):
        raise WitnessError("invalid signed capsule cannot be witnessed")
    statement = _statement(raw)
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    validate_witness_root(root)
    destination = root / (statement.run_id + ".json")
    if destination.exists():
        require_witness(root, raw)
        _fsync_directory(root)
        return destination
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".witness-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write((statement.model_dump_json() + "\n").encode())
            stream.flush()
            os.fchmod(stream.fileno(), 0o444)
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            require_witness(root, raw)
        _fsync_directory(root)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
