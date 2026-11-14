from pathlib import Path

import pytest

from sentinel_replay.provision_storage import provision


def test_existing_runtime_owned_key_can_be_reinitialized_without_rotating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unit test avoids changing host ownership; the Docker rehearsal exercises
    # the actual root-to-UID10001 transition and restart.
    monkeypatch.setattr("sentinel_replay.provision_storage.os.chown", lambda *args: None)
    key = tmp_path / "seed.key"
    key.touch(mode=0o600)
    key.write_bytes(b"s" * 32)
    keys, evidence = tmp_path / "keys", tmp_path / "evidence"
    provision(key, keys, evidence)
    provision(key, keys, evidence)
    assert (keys / "storage.key").read_bytes() == b"s" * 32
    key.write_bytes(b"d" * 32)
    with pytest.raises(ValueError, match="existing evidence key differs"):
        provision(key, keys, evidence)
    assert (keys / "storage.key").read_bytes() == b"s" * 32
    key.chmod(0o644)
    with pytest.raises(ValueError, match="mode0600"):
        provision(key, keys, evidence)
