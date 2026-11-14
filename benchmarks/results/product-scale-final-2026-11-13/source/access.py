"""Hashed bearer grants with explicit run and capability boundaries."""

import hashlib
import hmac
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["metadata", "evidence", "replay", "export", "import", "admin"]


class AccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scopes: frozenset[Scope]
    runs: frozenset[str]


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccessPolicy:
    def __init__(self, admin_token: str, grants: tuple[AccessGrant, ...] = ()) -> None:
        if len(grants) > 128:
            raise ValueError("at most 128 access grants are supported")
        hashes = [grant.token_sha256 for grant in grants]
        if len(set(hashes)) != len(hashes) or token_digest(admin_token) in hashes:
            raise ValueError("access token hashes must be unique")
        self.admin_digest = token_digest(admin_token)
        self.grants = grants

    def authenticate(self, token: str) -> AccessGrant | None:
        digest = token_digest(token)
        if hmac.compare_digest(digest, self.admin_digest):
            return AccessGrant(
                subject="local-admin",
                token_sha256=digest,
                scopes=frozenset({"admin"}),
                runs=frozenset({"*"}),
            )
        return next(
            (grant for grant in self.grants if hmac.compare_digest(digest, grant.token_sha256)),
            None,
        )

    @staticmethod
    def permits(grant: AccessGrant, scope: Scope, run_id: str | None = None) -> bool:
        if "admin" in grant.scopes:
            return True
        return scope in grant.scopes and (
            run_id is None or "*" in grant.runs or run_id in grant.runs
        )
