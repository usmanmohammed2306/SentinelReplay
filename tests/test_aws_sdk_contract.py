"""Validate adapter requests against the real botocore service models, without network."""

import base64
import hashlib
import importlib
from typing import Any

import pytest

from sentinel_replay.aws_evidence import KmsRootSigner, S3EvidenceStore
from sentinel_replay.canonical import canonical_bytes
from sentinel_replay.journal import Verification

pytestmark = pytest.mark.aws_optional

SIGNING_ARN = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000001"
ENCRYPTION_ARN = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000002"


def _client(service: str) -> Any:
    boto3 = pytest.importorskip("boto3")
    return boto3.Session(
        aws_access_key_id="offline-test",
        aws_secret_access_key="offline-test",
        region_name="us-east-1",
    ).client(service)


def test_s3_put_uses_supported_conditional_checksum_and_kms_parameters() -> None:
    client = _client("s3")
    stubber_class = importlib.import_module("botocore.stub").Stubber
    data = b"offline-sdk-contract"
    hexadecimal = hashlib.sha256(data).hexdigest()
    with stubber_class(client) as stubber:
        stubber.add_response(
            "put_object",
            {"VersionId": "sdk-version-1"},
            {
                "Bucket": "evidence-bucket",
                "Key": f"sentinel/blobs/sha256/{hexadecimal[:2]}/{hexadecimal}",
                "Body": data,
                "IfNoneMatch": "*",
                "ChecksumSHA256": base64.b64encode(hashlib.sha256(data).digest()).decode(),
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": ENCRYPTION_ARN,
                "ContentType": "application/octet-stream",
                "Metadata": {"sentinel-sha256": hexadecimal},
            },
        )
        reference = S3EvidenceStore(client, "evidence-bucket", ENCRYPTION_ARN).put(data)
    assert reference.version_id == "sdk-version-1"


def test_kms_sign_verify_uses_supported_asymmetric_algorithm() -> None:
    client = _client("kms")
    stubber_class = importlib.import_module("botocore.stub").Stubber
    journal = Verification(2, "sha256:" + "a" * 64)
    fields: dict[str, object] = {
        "schema_version": 1,
        "run_id": "run-001",
        "records": 2,
        "root": journal.root,
    }
    message = b"sentinel-replay:journal-root:v1\x00" + canonical_bytes(fields)
    with stubber_class(client) as stubber:
        stubber.add_response(
            "sign",
            {"KeyId": SIGNING_ARN, "Signature": b"sdk-signature"},
            {
                "KeyId": SIGNING_ARN,
                "Message": message,
                "MessageType": "RAW",
                "SigningAlgorithm": "RSASSA_PSS_SHA_256",
            },
        )
        stubber.add_response(
            "verify",
            {"KeyId": SIGNING_ARN, "SignatureValid": True},
            {
                "KeyId": SIGNING_ARN,
                "Message": message,
                "MessageType": "RAW",
                "Signature": b"sdk-signature",
                "SigningAlgorithm": "RSASSA_PSS_SHA_256",
            },
        )
        signer = KmsRootSigner(client, SIGNING_ARN)
        assert signer.verify(signer.sign("run-001", journal))
