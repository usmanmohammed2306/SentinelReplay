"""Pinned, local-only Docker profile for disposable agent environment fixtures.

This builds a bounded Linux command; it does not make a host Codex process or
its MCP tools isolated. Only the declared workspace is bind-mounted.
"""

import os
from collections.abc import Sequence
from pathlib import Path

PYTHON_IMAGE = (
    "python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
)


class IsolationError(ValueError):
    """The proposed fixture workspace or command is unsafe or unsupported."""


def isolated_docker_command(workspace: Path, argv: Sequence[str]) -> list[str]:
    """Build an offline, non-root, resource-bounded execution command.

    The caller must create and own a disposable workspace. In particular, this
    function does not authorize mounting a real repository or a credential dir.
    """
    if not workspace.is_absolute() or workspace.is_symlink() or not workspace.is_dir():
        raise IsolationError("workspace must be an existing absolute non-symlink directory")
    resolved = workspace.resolve(strict=True)
    if resolved != workspace or "," in str(resolved) or "\x00" in str(resolved):
        raise IsolationError("workspace path must be canonical and mount-safe")
    if not argv or any(not item or "\x00" in item for item in argv):
        raise IsolationError("container command must be nonempty and contain no NUL")
    if os.getuid() == 0 or os.getgid() == 0:
        raise IsolationError("fixture runner must not map host root into the container")
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--mount",
        f"type=bind,source={resolved},target=/work",
        "--workdir",
        "/work",
        PYTHON_IMAGE,
        *argv,
    ]
