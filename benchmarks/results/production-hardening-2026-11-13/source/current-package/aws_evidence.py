"""AWS S3 evidence and KMS root signatures, with injectable clients for offline tests."""

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sentinel_replay.canonical import canonical_bytes
from sentinel_replay.evidence_store import (
    DEFAULT_MAX_BLOB_BYTES,
    BlobCorruption,
    BlobRef,
    blob_digest,
    check_blob,
)
from sentinel_replay.journal import Verification

_KEY_ARN = re.compile(r"arn:aws[a-zA-Z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/[A-Za-z0-9-]+\Z")
_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_ROOT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ALGORITHM = "RSASSA_PSS_SHA_256"


class S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


class KmsClient(Protocol):
    def sign(self, **kwargs: Any) -> dict[str, Any]: ...

    def verify(self, **kwargs: Any) -> dict[str, Any]: ...


class CloudEvidenceError(ValueError):
    """The cloud service returned evidence that violates the declared contract."""


def _error_code(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    if isinstance(response, Mapping):
        detail = response.get("Error")
        if isinstance(detail, Mapping):
            code = detail.get("Code")
            if isinstance(code, str):
                return code
    return None


class S3EvidenceStore:
    """Put-once, SSE-KMS encrypted, independently hash-verified small evidence blobs."""

    def __init__(
        self,
        client: S3Client,
        bucket: str,
        kms_key_arn: str,
        *,
        prefix: str = "sentinel",
        max_bytes: int = DEFAULT_MAX_BLOB_BYTES,
    ) -> None:
        if not bucket or "/" in bucket or not _KEY_ARN.fullmatch(kms_key_arn):
            raise ValueError("invalid S3 bucket or KMS key ARN")
        if not prefix or not re.fullmatch(r"[A-Za-z0-9/_-]+", prefix):
            raise ValueError("invalid evidence prefix")
        if max_bytes < 1:
            raise ValueError("maximum blob size must be positive")
        self.client = client
        self.bucket = bucket
        self.kms_key_arn = kms_key_arn
        self.prefix = prefix.strip("/")
        self.max_bytes = max_bytes

    def _key(self, digest: str) -> str:
        BlobRef(digest, 0)
        hexadecimal = digest.removeprefix("sha256:")
        return f"{self.prefix}/blobs/sha256/{hexadecimal[:2]}/{hexadecimal}"

    def put(self, data: bytes) -> BlobRef:
        if len(data) > self.max_bytes:
            raise ValueError("blob exceeds configured maximum")
        digest = blob_digest(data)
        ref = BlobRef(digest, len(data))
        checksum = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        try:
            response = self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(digest),
                Body=data,
                IfNoneMatch="*",
                ChecksumSHA256=checksum,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self.kms_key_arn,
                ContentType="application/octet-stream",
                Metadata={"sentinel-sha256": digest.removeprefix("sha256:")},
            )
        except Exception as error:
            if _error_code(error) not in {"PreconditionFailed", "412"}:
                raise
            # A duplicate is acceptable only when the stored bytes verify independently.
            existing = self.get(ref)
            check_blob(existing, ref)
            current = self.client.get_object(Bucket=self.bucket, Key=self._key(digest))
            version_id = current.get("VersionId")
            return BlobRef(digest, len(data), version_id if isinstance(version_id, str) else None)
        version_id = response.get("VersionId")
        return BlobRef(digest, len(data), version_id if isinstance(version_id, str) else None)

    def get(self, ref: BlobRef) -> bytes:
        arguments: dict[str, object] = {"Bucket": self.bucket, "Key": self._key(ref.digest)}
        if ref.version_id is not None:
            arguments["VersionId"] = ref.version_id
        response = self.client.get_object(**arguments)
        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise CloudEvidenceError("S3 response has no readable body")
        data = body.read(self.max_bytes + 1)
        if not isinstance(data, bytes) or len(data) > self.max_bytes:
            raise BlobCorruption("blob exceeds configured maximum or is not bytes")
        check_blob(data, ref)
        return data


class RootAttestation(BaseModel):
    """A KMS signature over one exact journal root, not a claim of latest state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    records: int = Field(ge=0)
    root: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    key_arn: str
    algorithm: Literal["RSASSA_PSS_SHA_256"] = "RSASSA_PSS_SHA_256"
    signature_b64: str

    def signed_fields(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "records": self.records,
            "root": self.root,
        }


class KmsRootSigner:
    """Sign outside the recorded agent's writable trust boundary."""

    def __init__(self, client: KmsClient, key_arn: str) -> None:
        if not _KEY_ARN.fullmatch(key_arn):
            raise ValueError("a full asymmetric KMS key ARN is required")
        self.client = client
        self.key_arn = key_arn

    @staticmethod
    def _message(fields: dict[str, object]) -> bytes:
        return b"sentinel-replay:journal-root:v1\x00" + canonical_bytes(fields)

    def sign(self, run_id: str, journal: Verification) -> RootAttestation:
        if not _RUN_ID.fullmatch(run_id) or not _ROOT.fullmatch(journal.root):
            raise ValueError("invalid run ID or journal root")
        fields: dict[str, object] = {
            "schema_version": 1,
            "run_id": run_id,
            "records": journal.records,
            "root": journal.root,
        }
        response = self.client.sign(
            KeyId=self.key_arn,
            Message=self._message(fields),
            MessageType="RAW",
            SigningAlgorithm=_ALGORITHM,
        )
        signature = response.get("Signature")
        if response.get("KeyId") != self.key_arn or not isinstance(signature, bytes):
            raise CloudEvidenceError("KMS returned unexpected signing key or signature")
        return RootAttestation(
            run_id=run_id,
            records=journal.records,
            root=journal.root,
            key_arn=self.key_arn,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )

    def verify(self, attestation: RootAttestation) -> bool:
        if attestation.key_arn != self.key_arn or attestation.algorithm != _ALGORITHM:
            return False
        try:
            signature = base64.b64decode(attestation.signature_b64, validate=True)
        except ValueError:
            return False
        response = self.client.verify(
            KeyId=self.key_arn,
            Message=self._message(attestation.signed_fields()),
            MessageType="RAW",
            Signature=signature,
            SigningAlgorithm=_ALGORITHM,
        )
        return response.get("SignatureValid") is True


@dataclass(frozen=True)
class AnchorRef:
    """An exact S3 version of an attestation; the caller must retain this reference."""

    bucket: str
    key: str
    version_id: str
    digest: str
    size: int


class S3AnchorStore:
    """Publish signed roots in a separate, versioned, retention-controlled S3 bucket."""

    def __init__(
        self,
        client: S3Client,
        bucket: str,
        kms_key_arn: str,
        *,
        prefix: str = "sentinel",
    ) -> None:
        if not bucket or "/" in bucket or not _KEY_ARN.fullmatch(kms_key_arn):
            raise ValueError("invalid S3 bucket or KMS key ARN")
        if not prefix or not re.fullmatch(r"[A-Za-z0-9/_-]+", prefix):
            raise ValueError("invalid anchor prefix")
        self.client = client
        self.bucket = bucket
        self.kms_key_arn = kms_key_arn
        self.prefix = prefix.strip("/")

    def _key(self, attestation: RootAttestation) -> str:
        if not _RUN_ID.fullmatch(attestation.run_id) or not _ROOT.fullmatch(attestation.root):
            raise ValueError("invalid attestation identity")
        return (
            f"{self.prefix}/anchors/{attestation.run_id}/"
            f"{attestation.root.removeprefix('sha256:')}.json"
        )

    @staticmethod
    def _encoded(attestation: RootAttestation) -> bytes:
        return json.dumps(
            attestation.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    def publish(self, attestation: RootAttestation) -> AnchorRef:
        key = self._key(attestation)
        data = self._encoded(attestation)
        if len(data) > 16 * 1024:
            raise ValueError("attestation exceeds maximum size")
        checksum = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        try:
            response = self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                IfNoneMatch="*",
                ChecksumSHA256=checksum,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self.kms_key_arn,
                ContentType="application/json",
            )
        except Exception as error:
            if _error_code(error) not in {"PreconditionFailed", "412"}:
                raise
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response.get("Body")
            if body is None or not hasattr(body, "read") or body.read(16 * 1024 + 1) != data:
                raise CloudEvidenceError(
                    "existing anchor differs from signed attestation"
                ) from error
        version_id = response.get("VersionId")
        if not isinstance(version_id, str) or not version_id:
            raise CloudEvidenceError("anchor bucket must return an S3 VersionId")
        return AnchorRef(self.bucket, key, version_id, blob_digest(data), len(data))

    def load(self, reference: AnchorRef) -> RootAttestation:
        if (
            reference.bucket != self.bucket
            or not reference.version_id
            or not reference.key.startswith(f"{self.prefix}/anchors/")
        ):
            raise ValueError("anchor reference does not target the configured versioned bucket")
        BlobRef(reference.digest, reference.size)
        response = self.client.get_object(
            Bucket=self.bucket, Key=reference.key, VersionId=reference.version_id
        )
        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise CloudEvidenceError("S3 anchor response has no readable body")
        data = body.read(16 * 1024 + 1)
        if not isinstance(data, bytes) or len(data) > 16 * 1024:
            raise BlobCorruption("anchor exceeds maximum size or is not bytes")
        check_blob(data, BlobRef(reference.digest, reference.size))
        attestation = RootAttestation.model_validate_json(data)
        if self._key(attestation) != reference.key:
            raise CloudEvidenceError("anchor key disagrees with attestation identity")
        return attestation
