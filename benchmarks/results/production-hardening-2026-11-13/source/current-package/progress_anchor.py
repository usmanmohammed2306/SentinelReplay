"""Signed, prefix-consistent recording checkpoints in a protected local ledger.

Every signature binds the preceding signed checkpoint. A separately retained
ledger-head digest detects rollback relative to that witness. A portable ledger
alone cannot establish that no later checkpoint exists elsewhere.
"""

import base64
import binascii
import io
from pathlib import Path
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import canonical_bytes, event_digest, load_json_unique
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.journal import GENESIS, Journal, verify_journal_bytes
from sentinel_replay.local_anchor import _outside_agent, _regular_bytes, load_local_private_key

DOMAIN = b"sentinel-replay:progress-anchor:v1\x00"
MAX_LEDGER_BYTES = 1024 * 1024
MAX_CHECKPOINTS = 512


class ProgressCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    sequence: int = Field(ge=0, lt=MAX_CHECKPOINTS)
    records: int = Field(ge=0, le=50000)
    root: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    previous_checkpoint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    key_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    signature_b64: str = Field(max_length=88)

    def fields(self) -> dict[str, Any]:
        return self.model_dump(exclude={"signature_b64"})


def _checkpoints(data: bytes, keys: dict[str, bytes], run_id: str) -> list[ProgressCheckpoint]:
    if len(data) > MAX_LEDGER_BYTES:
        raise ValueError("progress ledger exceeds byte budget")
    verify_journal_bytes(data)
    result: list[ProgressCheckpoint] = []
    previous = GENESIS
    last_records = -1
    for line in io.BytesIO(data):
        row = load_json_unique(line.decode())
        checkpoint = ProgressCheckpoint.model_validate(row["event"])
        if (
            checkpoint.run_id != run_id
            or checkpoint.sequence != len(result)
            or checkpoint.previous_checkpoint != previous
            or checkpoint.records <= last_records
        ):
            raise ValueError("progress checkpoint identity, order or prefix count differs")
        if not result and (checkpoint.records != 0 or checkpoint.root != GENESIS):
            raise ValueError("recording must start with its signed empty prefix")
        raw = keys.get(checkpoint.key_id)
        if raw is None or blob_digest(raw) != checkpoint.key_id:
            raise ValueError("progress signer is not in the supplied trust set")
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(
                base64.b64decode(checkpoint.signature_b64, validate=True),
                DOMAIN + canonical_bytes(checkpoint.fields()),
            )
        except (InvalidSignature, binascii.Error, ValueError) as error:
            raise ValueError("invalid progress checkpoint signature") from error
        result.append(checkpoint)
        previous = event_digest(checkpoint.model_dump())
        last_records = checkpoint.records
    return result


def verify_progress(
    ledger: bytes,
    journal: bytes,
    run_id: str,
    keys: dict[str, bytes],
    *,
    expected_head: str | None = None,
    require_complete: bool = True,
) -> dict[str, Any]:
    checkpoints = _checkpoints(ledger, keys, run_id)
    if not checkpoints:
        raise ValueError("recording has no signed checkpoints")
    head = verify_journal_bytes(ledger).root
    if expected_head is not None and expected_head != head:
        raise ValueError("progress ledger differs from the separately retained witness")
    verified = verify_journal_bytes(journal)
    wanted = {checkpoint.records for checkpoint in checkpoints}
    roots = {0: GENESIS}
    for index, line in enumerate(io.BytesIO(journal), 1):
        if index in wanted:
            roots[index] = load_json_unique(line.decode())["hash"]
    if any(roots.get(item.records) != item.root for item in checkpoints):
        raise ValueError("journal no longer extends the signed prefixes")
    if require_complete and (
        checkpoints[-1].records != verified.records or checkpoints[-1].root != verified.root
    ):
        raise ValueError("recording tail is not anchored by the supplied ledger")
    return {
        "ledger_head": head,
        "journal_root": verified.root,
        "checkpoint_records": [item.records for item in checkpoints],
        "complete": checkpoints[-1].records == verified.records,
        "freshness": "matches_separately_supplied_head"
        if expected_head
        else "portable_history_only_no_external_freshness",
    }


class ProgressAnchors:
    def __init__(self, private_key: Path, root: Path, agent_root: Path) -> None:
        self.private = load_local_private_key(private_key, agent_root)
        _outside_agent(root, agent_root)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o022:
            raise ValueError("progress anchor root must be a protected real directory")
        self.path = root / "progress.jsonl"
        raw = self.private.public_key().public_bytes_raw()
        self.key_id, self.keys = blob_digest(raw), {blob_digest(raw): raw}

    def checkpoint(self, journal: Path, run_id: str, records: int) -> None:
        data = _regular_bytes(journal, 32 * 1024 * 1024)
        verified = verify_journal_bytes(data)
        if verified.records != records:
            raise ValueError("recording advanced outside the declared signing boundary")
        with Journal(self.path).writer() as writer:
            prior = _regular_bytes(self.path, MAX_LEDGER_BYTES)
            checkpoints = _checkpoints(prior, self.keys, run_id)
            if checkpoints:
                verify_progress(prior, data, run_id, self.keys, require_complete=False)
                if records == checkpoints[-1].records and verified.root == checkpoints[-1].root:
                    return
            elif records != 0:
                raise ValueError("live recording requires an initial empty-prefix checkpoint")
            fields: dict[str, Any] = {
                "schema_version": 1,
                "run_id": run_id,
                "sequence": len(checkpoints),
                "records": records,
                "root": verified.root,
                "previous_checkpoint": event_digest(checkpoints[-1].model_dump())
                if checkpoints
                else GENESIS,
                "key_id": self.key_id,
            }
            checkpoint = ProgressCheckpoint(
                **fields,
                signature_b64=base64.b64encode(
                    self.private.sign(DOMAIN + canonical_bytes(fields))
                ).decode(),
            )
            writer.append(checkpoint.model_dump())
