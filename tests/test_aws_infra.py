import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.aws_optional


def test_aws_evidence_template_declares_separate_retained_trust_boundaries() -> None:
    template = json.loads(
        (Path(__file__).resolve().parents[1] / "deploy/aws/evidence-stack.json").read_text()
    )
    resources = template["Resources"]
    evidence = resources["EvidenceBucket"]
    anchor = resources["AnchorBucket"]

    assert resources["EvidenceEncryptionKey"]["Properties"]["KeyUsage"] == "ENCRYPT_DECRYPT"
    assert resources["RootSigningKey"]["Properties"]["KeyUsage"] == "SIGN_VERIFY"
    assert evidence["DeletionPolicy"] == anchor["DeletionPolicy"] == "Retain"
    assert evidence["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"
    assert anchor["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"
    assert anchor["Properties"]["ObjectLockEnabled"] is True
    retention = anchor["Properties"]["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]
    assert retention["Mode"] == "GOVERNANCE"
    assert retention["Days"]["Ref"] == "AnchorRetentionDays"
    for bucket in (evidence, anchor):
        assert all(bucket["Properties"]["PublicAccessBlockConfiguration"].values())
        encryption = bucket["Properties"]["BucketEncryption"]["ServerSideEncryptionConfiguration"][
            0
        ]
        assert encryption["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"
