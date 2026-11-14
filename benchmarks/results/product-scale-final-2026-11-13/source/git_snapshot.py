"""Quiescent regular-file Git checkpoint, with safe configuration on restore.

Captures worktree, index, HEAD, refs and local objects. Linked worktrees, partial
clones, alternate object stores, symlinks and hostile concurrent mutation are
unsupported. Hooks, remotes and user configuration are never restored/executed.
"""

import configparser
import os
import re
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import event_digest
from sentinel_replay.evidence_store import BlobRef, FileEvidenceStore, blob_digest
from sentinel_replay.local_anchor import _regular_bytes
from sentinel_replay.workspace_snapshot import (
    MAX_FILES,
    MAX_TOTAL_BYTES,
    FileEntry,
    WorkspaceManifest,
    _digest_entries,
    _open_covered_file,
    restore_workspace,
    verify_workspace,
)

_CONFIG = (
    b"[core]\n\trepositoryformatversion = 0\n\tbare = false\n"
    b"\tfilemode = true\n\thooksPath = /dev/null\n\tfsmonitor = false\n"
)


class GitCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    adapter: Literal["git-regular-quiescent-v1"] = "git-regular-quiescent-v1"
    worktree: WorkspaceManifest
    metadata: WorkspaceManifest
    checkpoint_digest: str
    adapter_source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    coverage: Literal["worktree_index_head_refs_local_objects_safe_config"] = (
        "worktree_index_head_refs_local_objects_safe_config"
    )


def _manifest(
    root: Path, paths: list[str], store: FileEvidenceStore, *, git: bool = False
) -> WorkspaceManifest:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    entries = []
    total = 0
    try:
        for relative in paths:
            source = _open_covered_file(descriptor, relative)
            try:
                before = os.fstat(source)
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("Git snapshot supports regular files only")
                with os.fdopen(source, "rb", closefd=False) as reader:
                    data = reader.read(MAX_TOTAL_BYTES - total + 1)
                after = os.fstat(source)
                if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ) or len(data) != before.st_size:
                    raise ValueError("Git file changed during capture")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError("Git snapshot exceeds byte budget")
                ref = store.put(data)
                entries.append(
                    FileEntry(
                        path=relative,
                        digest=ref.digest,
                        size=ref.size,
                        executable=bool(before.st_mode & 0o111),
                    )
                )
            finally:
                os.close(source)
        if git:
            ref = store.put(_CONFIG)
            entries.append(
                FileEntry(path="config", digest=ref.digest, size=ref.size, executable=False)
            )
    finally:
        os.close(descriptor)
    ordered = tuple(sorted(entries, key=lambda entry: entry.path))
    return WorkspaceManifest(entries=ordered, manifest_digest=_digest_entries(ordered))


def _paths(root: Path, *, git: bool) -> list[str]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts
        if not git and parts[0] == ".git":
            continue
        if git and not (
            relative in {"HEAD", "index", "packed-refs", "shallow"}
            or parts[0] in {"refs", "objects"}
        ):
            continue
        if git and relative.startswith("objects/info/"):
            continue
        if path.is_symlink():
            raise ValueError("Git snapshot refuses symlinks")
        if path.is_dir():
            continue
        if relative.endswith(".lock"):
            raise ValueError("Git state has an active lock")
        result.append(relative)
        if len(result) > MAX_FILES - int(git):
            raise ValueError("Git snapshot exceeds file budget")
    return result


def capture_git(root: Path, store: FileEvidenceStore) -> GitCheckpoint:
    metadata = root / ".git"
    if root.is_symlink() or metadata.is_symlink() or not metadata.is_dir():
        raise ValueError(
            "Git snapshot requires an ordinary private worktree with a real .git directory"
        )
    if any((metadata / name).is_symlink() for name in ("objects", "refs")) or any(
        (metadata / name).exists() or (metadata / name).is_symlink()
        for name in ("HEAD.lock", "index.lock", "packed-refs.lock")
    ):
        raise ValueError("Git boundary has a symlink or active lock")
    if any(
        (metadata / name).exists()
        for name in (
            "commondir",
            "objects/info/alternates",
            "info/grafts",
            "info/sparse-checkout",
            "reftable",
        )
    ) or list((metadata / "objects").rglob("*.promisor")):
        raise ValueError(
            "linked, alternate, sparse, reftable and partial repositories are unsupported"
        )
    config = configparser.ConfigParser(interpolation=None, strict=True, allow_no_value=True)
    try:
        config.read_string(_regular_bytes(metadata / "config", 65536).decode())
        if config.get("core", "repositoryformatversion", fallback="0") != "0" or config.has_section(
            "extensions"
        ):
            raise ValueError("Git repository format is unsupported")
    except configparser.Error as error:
        raise ValueError("Git configuration cannot be normalized safely") from error
    head = _regular_bytes(metadata / "HEAD", 512).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head) and (
        not re.fullmatch(r"ref: refs/[A-Za-z0-9_./-]+", head)
        or any(part in {"", ".", ".."} for part in head[5:].split("/"))
    ):
        raise ValueError("Git HEAD reference is unsupported")
    trees = []
    for _ in range(2):
        trees.append(
            (
                _manifest(root, _paths(root, git=False), store),
                _manifest(metadata, _paths(metadata, git=True), store, git=True),
            )
        )
    if trees[0] != trees[1]:
        raise ValueError("Git boundary was not quiescent")
    worktree, internal = trees[0]
    digest = event_digest(
        {
            "adapter": "git-regular-quiescent-v1",
            "worktree": worktree.manifest_digest,
            "metadata": internal.manifest_digest,
        }
    )
    return GitCheckpoint(
        worktree=worktree,
        metadata=internal,
        checkpoint_digest=digest,
        adapter_source_digest=blob_digest(Path(__file__).read_bytes()),
    )


def restore_git(checkpoint: GitCheckpoint, destination: Path, store: FileEvidenceStore) -> bool:
    if checkpoint.adapter_source_digest != blob_digest(Path(__file__).read_bytes()):
        raise ValueError("Git adapter identity differs from the checkpoint")
    expected = event_digest(
        {
            "adapter": checkpoint.adapter,
            "worktree": checkpoint.worktree.manifest_digest,
            "metadata": checkpoint.metadata.manifest_digest,
        }
    )
    if expected != checkpoint.checkpoint_digest:
        raise ValueError("Git checkpoint binding differs")
    if any(entry.path.split("/")[0] == ".git" for entry in checkpoint.worktree.entries):
        raise ValueError("Git worktree manifest may not inject metadata")
    for entry in checkpoint.metadata.entries:
        path = entry.path
        if (
            not (
                path in {"config", "HEAD", "index", "packed-refs", "shallow"}
                or path.startswith(("refs/", "objects/"))
            )
            or path.startswith("objects/info/")
            or path.endswith((".lock", ".promisor"))
        ):
            raise ValueError("unsupported Git metadata in checkpoint")
    configs = [entry for entry in checkpoint.metadata.entries if entry.path == "config"]
    if len(configs) != 1 or store.get(BlobRef(configs[0].digest, configs[0].size)) != _CONFIG:
        raise ValueError("Git checkpoint contains unsafe configuration")
    restore_workspace(checkpoint.worktree, destination, store)
    if not verify_workspace(checkpoint.worktree, destination):
        raise ValueError("Git worktree restore differs")
    restore_workspace(checkpoint.metadata, destination / ".git", store)
    if not verify_workspace(checkpoint.metadata, destination / ".git"):
        raise ValueError("Git metadata restore differs")
    config = destination / ".git/config"
    if config.read_bytes() != _CONFIG:
        raise ValueError("Git restore refuses untrusted configuration")
    # Do not decode attacker-controlled Git objects or execute Git in the
    # controller. This is a byte-restoration adapter, not an object-health or
    # native Git replay claim. Conformance uses an explicitly trusted fixture.
    return True
