"""One-shot local Docker volume ownership and evidence-key initialization.

Runs only as the explicit init container. A different existing key is an error,
never an implicit rotation that would strand stored ciphertext.
"""

import os
import tempfile
from pathlib import Path

from sentinel_replay.local_anchor import _fsync_directory, _regular_bytes, _write_new


def provision(
    source: Path,
    key_root: Path,
    evidence_root: Path,
    registry_source: Path | None = None,
    trust_root: Path | None = None,
) -> None:
    data = _private_volume_key(source)
    if len(data) != 32:
        raise ValueError("AES evidence key must contain exactly32 bytes")
    for root in (key_root, evidence_root):
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink():
            raise ValueError("volume root must not be a symlink")
    destination = key_root / "storage.key"
    if destination.exists() or destination.is_symlink():
        if _private_volume_key(destination) != data:
            raise ValueError("existing evidence key differs; explicit rotation is required")
    else:
        _write_new(destination, data, 0o600)
    os.chown(destination, 10001, 10001)
    for root in (key_root, evidence_root):
        os.chown(root, 10001, 10001)
        os.chmod(root, 0o700)
        _fsync_directory(root)
    if registry_source is not None and trust_root is not None:
        from sentinel_replay.canonical import load_json_unique
        from sentinel_replay.trust_registry import TrustRegistry

        registry_data = _regular_bytes(registry_source, 32768)
        registry = TrustRegistry.model_validate(load_json_unique(registry_data.decode()))
        trust_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if trust_root.is_symlink():
            raise ValueError("trust volume must not be a symlink")
        path = trust_root / "registry.json"
        if path.exists() or path.is_symlink():
            previous = TrustRegistry.model_validate_json(_regular_bytes(path, 32768))
            if registry.epoch < previous.epoch or (
                registry.epoch == previous.epoch and registry != previous
            ):
                raise ValueError("trust provisioning refuses rollback or equivocation")
        with tempfile.NamedTemporaryFile(dir=trust_root, delete=False) as temporary:
            staged = Path(temporary.name)
            try:
                temporary.write(registry_data)
                temporary.flush()
                os.fsync(temporary.fileno())
                os.chown(staged, 10001, 10001)
                os.chmod(staged, 0o600)
                os.replace(staged, path)
                _fsync_directory(trust_root)
            finally:
                staged.unlink(missing_ok=True)
        os.chown(trust_root, 10001, 10001)
        os.chmod(trust_root, 0o700)


def _private_volume_key(path: Path) -> bytes:
    # The root initializer reads a host-owned seed and a runtime-owned existing
    # key. Owner equality with the initializer is therefore the wrong invariant.
    # Both are fixed, operator-selected paths; exact bytes and0600 are required.
    value = _regular_bytes(path, 33)
    if path.stat().st_mode & 0o777 != 0o600:
        raise ValueError("provisioning key must have mode0600")
    return value


if __name__ == "__main__":
    provision(
        Path("/seed/storage.key"),
        Path("/run/sentinel-secrets"),
        Path("/var/lib/sentinel/evidence"),
        Path("/seed/trust.json"),
        Path("/run/sentinel-trust"),
    )
