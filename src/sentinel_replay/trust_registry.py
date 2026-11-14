"""Operator-selected keys, rotation, revocation and local epoch rollback refusal.

The registry is mounted read-only outside the agent. The append-only SQL epoch
ledger refuses older/equivocating configurations relative to that ledger. It
does not prove wall-clock evidence freshness or detect rollback of the entire
controller/ledger together. Revocation applies to newly admitted operations.
"""

import base64
import binascii
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.database import trust_epochs
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.local_anchor import _regular_bytes


class TrustedKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    public_key_b64: str = Field(max_length=48)
    state: Literal["active", "retired", "revoked"] = "active"
    not_before: datetime | None = None
    not_after: datetime | None = None

    @model_validator(mode="after")
    def valid(self) -> "TrustedKey":
        self.raw()
        for value in (self.not_before, self.not_after):
            if value is not None and value.tzinfo is None:
                raise ValueError("trust windows require an explicit timezone")
        if self.not_before and self.not_after and self.not_before >= self.not_after:
            raise ValueError("invalid trust window")
        return self

    def raw(self) -> bytes:
        try:
            value = base64.b64decode(self.public_key_b64, validate=True)
        except binascii.Error as error:
            raise ValueError("invalid trusted public key encoding") from error
        if len(value) != 32 or blob_digest(value) != self.key_id:
            raise ValueError("trusted public key identity differs")
        return value

    def status(self, now: datetime) -> str:
        if self.state == "revoked":
            return "revoked"
        if self.not_before and now < self.not_before:
            return "not_yet_valid"
        if self.not_after and now >= self.not_after:
            return "expired"
        return self.state


class TrustRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    epoch: int = Field(ge=1, le=2**31 - 1)
    keys: tuple[TrustedKey, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique(self) -> "TrustRegistry":
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("duplicate trust-registry key")
        return self

    @classmethod
    def load(cls, path: Path, engine: Engine) -> "TrustRegistry":
        raw = _regular_bytes(path, 32768)
        if path.stat().st_mode & 0o022:
            raise ValueError("trust registry must not be group/world writable")
        result = cls.model_validate(load_json_unique(raw.decode()))
        digest = event_digest(result.model_dump(mode="json"))
        with engine.connect() as connection:
            latest = (
                connection.execute(
                    select(trust_epochs).order_by(trust_epochs.c.epoch.desc()).limit(1)
                )
                .mappings()
                .first()
            )
        if latest is not None:
            if result.epoch < latest["epoch"] or (
                result.epoch == latest["epoch"] and digest != latest["digest"]
            ):
                raise ValueError("trust-registry rollback or epoch equivocation")
            if result.epoch == latest["epoch"]:
                return result
        try:
            with engine.begin() as connection:
                connection.execute(insert(trust_epochs).values(epoch=result.epoch, digest=digest))
        except IntegrityError:
            with engine.connect() as connection:
                existing: str = connection.execute(
                    select(trust_epochs.c.digest).where(trust_epochs.c.epoch == result.epoch)
                ).scalar_one()
            if existing != digest:
                raise ValueError("trust-registry epoch equivocation") from None
        return result

    def status(self, key_id: str, *, now: datetime | None = None) -> str:
        current = now or datetime.now(UTC)
        key = next((key for key in self.keys if key.key_id == key_id), None)
        return key.status(current) if key else "unknown"

    def import_key(self, key_id: str, *, now: datetime | None = None) -> bytes:
        if self.status(key_id, now=now) != "active":
            raise ValueError("capsule signer is not active for new imports")
        return next(key.raw() for key in self.keys if key.key_id == key_id)
