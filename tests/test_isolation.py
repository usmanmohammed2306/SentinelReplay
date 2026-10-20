"""Declarative and guarded live conformance for the disposable Linux profile."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from sentinel_replay.isolation import IsolationError, isolated_docker_command


def test_profile_is_offline_readonly_nonroot_and_mounts_only_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "agent"
    workspace.mkdir()
    command = isolated_docker_command(workspace, ["python", "-V"])
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    mounts = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--mount"]
    assert mounts == [f"type=bind,source={workspace},target=/work"]


def test_profile_rejects_symlink_relative_path_and_empty_command(tmp_path: Path) -> None:
    workspace = tmp_path / "agent"
    workspace.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace)
    for path, args in ((alias, ["python"]), (Path("agent"), ["python"]), (workspace, [])):
        with pytest.raises(IsolationError):
            isolated_docker_command(path, args)


@pytest.mark.skipif(
    os.environ.get("SENTINEL_TEST_DOCKER_ISOLATION") != "1",
    reason="requires explicit local Docker isolation conformance run",
)
def test_real_docker_container_cannot_read_unmounted_controller_or_use_network(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "agent"
    workspace.mkdir()
    controller = tmp_path / "controller"
    controller.mkdir()
    secret = controller / "fake-token.txt"
    secret.write_text("synthetic-fixture-only\n")
    script = (
        "import json, pathlib, socket; "
        "p=pathlib.Path('/work/native.txt'); p.write_text('inside\\n'); "
        "host=pathlib.Path(" + repr(str(secret)) + "); "
        "s=socket.socket(); s.settimeout(1); "
        "\ntry: s.connect(('192.0.2.1', 53)); network=True\n"
        "except OSError: network=False\n"
        "print(json.dumps({'host_secret_visible': host.exists(), "
        "'network_connected': network, 'work_written': p.read_text()=='inside\\n'}))"
    )
    completed = subprocess.run(
        isolated_docker_command(workspace, ["python", "-c", script]),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-1000:]
    observed = json.loads(completed.stdout)
    assert observed == {
        "host_secret_visible": False,
        "network_connected": False,
        "work_written": True,
    }
    assert (workspace / "native.txt").read_text() == "inside\n"
    assert secret.read_text() == "synthetic-fixture-only\n"
