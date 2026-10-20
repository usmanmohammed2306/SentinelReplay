# Optional AWS evidence profile — deployment runbook (not deployed)

This directory contains a **real CloudFormation template**, not a claim that an AWS environment has been created. No command in this runbook was run against your account. Under [ADR-0003](../../docs/adr/0003-local-first-release.md), AWS is optional and **not required for V1**. Do not deploy this experiment without a new explicit request and approval. If that ever happens, review costs, retention, IAM, and the target region first.

## What is implemented

```text
local verified journal ── KMS asymmetric Sign ── signed root attestation
                                                  │
                                                  ▼
                                       version-pinned S3 anchor bucket
                                       (Object Lock + SSE-KMS)

evidence bytes ── SHA-256 content ID ── conditional S3 PutObject
                                      (checksum + SSE-KMS + versioning)
```

The CLI uses normal Boto3 credential resolution. No access keys are embedded. The CloudFormation template creates two distinct KMS keys, an evidence bucket, an anchor bucket, public-access blocks, TLS-only policies, versioning, and default 30-day GOVERNANCE Object Lock on anchors. It retains keys and buckets when the stack is removed.

## Before any deployment

1. Choose one AWS account and region and confirm a spending budget. S3 storage/requests, KMS keys/requests, and Object Lock retention can incur cost.
2. Choose globally unique bucket names. Review `evidence-stack.json` with an AWS administrator. `make aws-infra` passes the CloudFormation schema linter locally; still validate with AWS CLI/CloudFormation in the target account. Local lint is **not** service acceptance.
3. Decide retention and legal requirements. GOVERNANCE is bypassable by a privileged principal. Do not use this default as a compliance claim.
4. Create separate roles: a forensic controller may call KMS `Sign` and write anchors; the recorded agent may not. Do not let the agent assume the controller role or write/delete the anchor bucket.
5. Give the runtime only scoped `s3:PutObject`, `s3:GetObject`, `s3:GetObjectVersion` on its evidence prefix; KMS data-key/decrypt access to the symmetric key; and no `s3:DeleteObject`, `kms:ScheduleKeyDeletion`, or `s3:BypassGovernanceRetention`. Scope controller permissions separately to anchor writes and signing/verification.
6. Arrange CloudTrail/S3 access audit, alarms, key policy review, backup/replication, and lifecycle cost review before handling real data.

## Template review and optional deployment

These commands are examples **for you to run only after the review above**. Replace names and region; do not paste real credentials into the repository.

```console
aws cloudformation validate-template --template-body file://deploy/aws/evidence-stack.json --region YOUR_REGION

aws cloudformation deploy \
  --stack-name sentinel-replay-evidence-dev \
  --template-file deploy/aws/evidence-stack.json \
  --parameter-overrides EvidenceBucketName=YOUR_UNIQUE_EVIDENCE_BUCKET AnchorBucketName=YOUR_UNIQUE_ANCHOR_BUCKET AnchorRetentionDays=30 \
  --region YOUR_REGION
```

The stack output gives bucket names and both key ARNs. CloudFormation stack deletion does **not** delete retained keys/buckets. Do not attempt cleanup while Object Lock retention is active.

## Local command path after deployment

Install the optional SDK profile:

```console
uv sync --frozen --extra aws
```

Store one *synthetic* blob:

```console
sentinel aws put-blob synthetic.txt \
  --bucket YOUR_UNIQUE_EVIDENCE_BUCKET \
  --encryption-key-arn YOUR_SYMMETRIC_KEY_ARN \
  --region YOUR_REGION
```

Anchor a local verified journal, then check that exact remote version against it:

```console
sentinel aws anchor-journal run.jsonl run-001 anchor-ref.json \
  --bucket YOUR_UNIQUE_ANCHOR_BUCKET \
  --encryption-key-arn YOUR_SYMMETRIC_KEY_ARN \
  --signing-key-arn YOUR_ASYMMETRIC_KEY_ARN \
  --region YOUR_REGION

sentinel aws verify-anchor run.jsonl run-001 anchor-ref.json \
  --bucket YOUR_UNIQUE_ANCHOR_BUCKET \
  --encryption-key-arn YOUR_SYMMETRIC_KEY_ARN \
  --signing-key-arn YOUR_ASYMMETRIC_KEY_ARN \
  --region YOUR_REGION
```

`anchor-ref.json` pins the S3 VersionId. Keep it with investigation metadata, but remember that a local pointer alone does not establish freshness. The CLI refuses an existing reference path and a changed local journal root. The SDK path is unit-tested with in-memory clients; **no real AWS integration has passed yet**.

## Next AWS gates

- CloudFormation service validation in the target account; offline SDK `Stubber` and `cfn-lint` checks already pass.
- Real-account synthetic smoke for S3 PUT/GET corruption, KMS Sign/Verify, anchor versioning and retention, IAM-denied agent signing, and audit logs.
- Private VPC deployment for API/worker, RDS PostgreSQL, managed telemetry export, backup/recovery, least-privilege roles, secrets, and cost/performance tests.
- Clean-room AWS install and disaster rehearsal before ever claiming a separately supported AWS profile; the self-hosted V1 release does not need this.

The [AWS ADR](../../docs/adr/0002-aws-evidence-profile.md) defines the trust boundary and the claims this profile may make.
