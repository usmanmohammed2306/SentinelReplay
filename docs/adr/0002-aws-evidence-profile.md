# ADR-0002: AWS evidence profile and external root anchor

Status: **Optional design record; mandatory release scope superseded by ADR-0003**  
Date: 2026-10-01

## Why this profile exists

An agent-writable JSONL journal can detect accidental corruption, but an attacker who can rewrite it can recompute its whole hash chain. Sentinel needs a trust boundary outside that agent's workspace. At the time of this decision, the user requested an AWS deployment path. The later local-first decision in ADR-0003 removes AWS from the V1 gate while preserving this experimental design.

## Decision

1. The local filesystem and S3 stores share `sha256:<hex>` content identities. Reads recompute the digest from returned bytes; S3 ETags are never treated as content hashes.
2. An S3 evidence bucket holds small content-addressed blobs with conditional `IfNoneMatch="*"` writes, a SHA-256 request checksum, explicit SSE-KMS, and version IDs where available. The initial adapter has an 8 MiB per-blob in-memory limit; streaming/multipart is a later gate, not an implied capability.
3. A distinct asymmetric AWS KMS key signs a domain-separated message containing run ID, journal record count, and exact final root. The agent process must not have `kms:Sign` permission.
4. The signed attestation is published to a **separate** S3 anchor bucket with versioning, Object Lock default retention, explicit SSE-KMS, conditional creation, and a version-pinned reference. The reference file is only a pointer; it is not itself a trusted anchor.
5. The provided CloudFormation evidence stack uses two distinct KMS keys and two retained buckets. It defaults to 30-day **GOVERNANCE** retention. Governance is not absolute immutability; principals with bypass permission can override it. Production policy must exclude `s3:BypassGovernanceRetention` from runtime identities, and an independent administrator must control retention/key policy.
6. A future AWS-supported profile would need a private network/runtime path for API/worker, RDS PostgreSQL, telemetry, IAM roles, monitoring, backup/recovery, and real-account clean-room proof. The current evidence stack is an optional experimental slice, **not** a deployed platform or V1 prerequisite.

## Evidence classes and limitations

| Claim | Current evidence | Not yet proven |
| --- | --- | --- |
| Same blob identity locally and on S3 | offline parity and corruption tests | large streaming uploads, real S3 integration |
| KMS-shaped root signature | offline client contract tests | actual KMS key/sign/verify in a user account |
| Exact S3 anchor version | version-pinned reference and offline tests | actual Object Lock retention, IAM isolation, rollback/freshness monitoring |
| Full AWS runtime | architecture requirement only | ECS/Fargate, RDS, VPC, OTel, backup, DR, load/scale test |

A KMS signature proves the signed root came from the key, assuming its key policy and IAM boundary hold. It does **not** prove it is the latest root, that no later run existed, or that the agent's effects were restored. A pinned S3 version plus retention makes deletion/overwrite harder within the declared retention/IAM boundary; a separate monotonic checkpoint or external auditor is needed for strong freshness claims.

## Security gates

- No long-lived AWS credentials in code, examples, CI, or commits. Use the SDK credential chain and short-lived roles.
- Signing role and recorded-agent role are separate; the agent receives neither `kms:Sign` nor anchor-bucket write/delete permission.
- Runtime roles get only prefix-scoped S3 read/write and the relevant encryption key operations, never broad bucket deletion or Object Lock bypass.
- Real-account tests use disposable synthetic data, a named budget, explicit region/account, and user approval before deployment.
- CloudFormation `Retain` and Object Lock can create continuing storage/KMS cost. Cleanup is a deliberate manual operation after retention expires.

## References

- [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Boto3 S3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)
- [CloudFormation KMS key](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-kms-key.html)
- [Boto3 credential chain](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html)
