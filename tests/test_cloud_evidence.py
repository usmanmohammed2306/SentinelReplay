import base64
import hashlib
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sentinel_replay.aws_evidence import KmsRootSigner, S3AnchorStore, S3EvidenceStore
from sentinel_replay.evidence_store import BlobCorruption, FileEvidenceStore
from sentinel_replay.journal import Journal, Verification

pytestmark = pytest.mark.aws_optional


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[dict[str, Any]] = []
        self.corrupt_read = False

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.puts.append(kwargs)
        address = (kwargs["Bucket"], kwargs["Key"])
        if address in self.objects:
            raise FakeAwsError("PreconditionFailed")
        self.objects[address] = kwargs["Body"]
        return {"VersionId": "version-1"}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        address = (kwargs["Bucket"], kwargs["Key"])
        body = self.objects[address]
        if self.corrupt_read:
            body = b"X" + body[1:]
        return {"Body": FakeBody(body), "VersionId": "version-1"}


class FakeBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, amount: int) -> bytes:
        return self.body[:amount]


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeKms:
    def __init__(self, key_arn: str) -> None:
        self.key_arn = key_arn
        self.sign_calls: list[dict[str, Any]] = []
        self.verify_calls: list[dict[str, Any]] = []

    def sign(self, **kwargs: Any) -> dict[str, Any]:
        self.sign_calls.append(kwargs)
        return {"KeyId": self.key_arn, "Signature": hashlib.sha256(kwargs["Message"]).digest()}

    def verify(self, **kwargs: Any) -> dict[str, Any]:
        self.verify_calls.append(kwargs)
        return {"SignatureValid": kwargs["Signature"] == hashlib.sha256(kwargs["Message"]).digest()}


KEY_ARN = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000001"
ENCRYPTION_ARN = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000002"


def test_file_and_s3_stores_share_digest_and_detect_tampering(tmp_path: Path) -> None:
    data = b"forensic-evidence\x00"
    local = FileEvidenceStore(tmp_path / "blobs")
    local_ref = local.put(data)
    s3 = FakeS3()
    remote = S3EvidenceStore(s3, bucket="evidence-bucket", kms_key_arn=KEY_ARN)
    remote_ref = remote.put(data)

    assert local_ref.digest == remote_ref.digest
    assert local.get(local_ref) == remote.get(remote_ref) == data
    assert s3.puts[0]["IfNoneMatch"] == "*"
    assert s3.puts[0]["ServerSideEncryption"] == "aws:kms"
    assert s3.puts[0]["SSEKMSKeyId"] == KEY_ARN
    assert s3.puts[0]["ChecksumSHA256"] == base64.b64encode(hashlib.sha256(data).digest()).decode()
    assert remote.put(data) == remote_ref

    s3.corrupt_read = True
    with pytest.raises(BlobCorruption, match="digest mismatch"):
        remote.get(remote_ref)


def test_stores_reject_oversized_blobs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="maximum"):
        FileEvidenceStore(tmp_path, max_bytes=3).put(b"1234")
    with pytest.raises(ValueError, match="maximum"):
        S3EvidenceStore(FakeS3(), "evidence-bucket", KEY_ARN, max_bytes=3).put(b"1234")


def test_kms_attestation_binds_run_root_and_count() -> None:
    kms = FakeKms(KEY_ARN)
    signer = KmsRootSigner(kms, KEY_ARN)
    proof = signer.sign("run-001", Verification(5, "sha256:" + "a" * 64))

    assert signer.verify(proof)
    assert kms.sign_calls[0]["MessageType"] == "RAW"
    assert kms.sign_calls[0]["SigningAlgorithm"] == "RSASSA_PSS_SHA_256"
    assert not signer.verify(proof.model_copy(update={"records": 4}))
    assert not signer.verify(proof.model_copy(update={"root": "sha256:" + "b" * 64}))


def test_signed_root_is_published_and_loaded_from_versioned_anchor() -> None:
    s3 = FakeS3()
    kms = FakeKms(KEY_ARN)
    signer = KmsRootSigner(kms, KEY_ARN)
    proof = signer.sign("run-001", Verification(5, "sha256:" + "a" * 64))
    anchors = S3AnchorStore(s3, "anchor-bucket", KEY_ARN)

    reference = anchors.publish(proof)
    assert reference.version_id == "version-1"
    assert anchors.load(reference) == proof
    assert signer.verify(anchors.load(reference))
    assert anchors.publish(proof) == reference
    assert s3.puts[0]["IfNoneMatch"] == "*"
    assert s3.puts[0]["ServerSideEncryption"] == "aws:kms"

    s3.corrupt_read = True
    with pytest.raises(BlobCorruption):
        anchors.load(reference)

    with pytest.raises(ValueError, match="anchor reference"):
        anchors.load(
            reference.__class__(
                reference.bucket,
                "other/key",
                reference.version_id,
                reference.digest,
                reference.size,
            )
        )


def test_aws_cli_anchors_and_verifies_journal_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel_replay import cli

    journal_path = tmp_path / "run.jsonl"
    Journal(journal_path).append({"kind": "synthetic", "value": 1})
    reference_path = tmp_path / "anchor-ref.json"
    s3 = FakeS3()
    kms = FakeKms(KEY_ARN)
    monkeypatch.setattr(cli, "_aws_clients", lambda region: (s3, kms))
    runner = CliRunner()
    common = [
        "--bucket",
        "anchor-bucket",
        "--encryption-key-arn",
        ENCRYPTION_ARN,
        "--signing-key-arn",
        KEY_ARN,
        "--region",
        "us-east-1",
    ]

    anchored = runner.invoke(
        cli.app,
        ["aws", "anchor-journal", str(journal_path), "run-001", str(reference_path), *common],
    )
    verified = runner.invoke(
        cli.app,
        ["aws", "verify-anchor", str(journal_path), "run-001", str(reference_path), *common],
    )

    assert anchored.exit_code == 0, anchored.output
    assert verified.exit_code == 0, verified.output
    assert "AWS_ANCHOR_VALID" in verified.stdout
    wrong_run = runner.invoke(
        cli.app,
        ["aws", "verify-anchor", str(journal_path), "run-002", str(reference_path), *common],
    )
    assert wrong_run.exit_code != 0
    assert "run ID differs" in wrong_run.output
    Journal(journal_path).append({"kind": "synthetic", "value": 2})
    changed = runner.invoke(
        cli.app,
        ["aws", "verify-anchor", str(journal_path), "run-001", str(reference_path), *common],
    )
    assert changed.exit_code != 0
    assert "journal root or count differs" in changed.output
