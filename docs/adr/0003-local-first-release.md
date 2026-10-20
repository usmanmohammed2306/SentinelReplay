# ADR-0003: Local-first production release; AWS optional

Status: **Accepted**  
Date: 2026-10-07

## Decision

Complete Flagship V1 is a self-hosted, reproducible local deployment. Its production gate still requires the complete sixteen-clause demo, REST/SSE API and UI, PostgreSQL metadata, isolated agent execution, verified covered-state restore, signed and externally anchored evidence roots, policy evaluation, the twelve-scenario corpus, security and recovery tests, 3k/10k/50k measurements, and a clean-room install. “Local” does not mean a single-process toy or permission to weaken any replay or evidence claim.

AWS is no longer a V1 requirement. No AWS account, region, budget, deployment, or real-service test is needed to accept the project. The existing S3/KMS adapter, CloudFormation template, and offline tests remain as an **optional experimental profile**; they do not provide release evidence and must not be described as a deployed product. Do not incur cloud cost without a new explicit request and approval.

The production trust boundary must be demonstrated without AWS: the signer and anchor must be outside the recorded agent's writable sandbox, with documented key ownership, rotation, verification, and recovery. A local process that can rewrite both the journal and its own anchor does not satisfy this requirement.

## Why this changed

The user withdrew the AWS requirement after requesting it earlier. This decision supersedes the mandatory-AWS portion of ADR-0002 and charter revision 1.6. It does **not** repeal the original forty-three-section product specification or the evidence-integrity requirements that AWS had been one possible way to meet.

## Consequences

- S06, S28, S38, S53, S58, and S60 must be accepted on local/self-hosted evidence; optional AWS checks cannot substitute for missing local gates.
- Core CI installs and tests the local product. Offline AWS contract and infrastructure checks remain available by explicit command, outside the required release path.
- The current `us-west-2` and `$25` preference is inactive because there will be no AWS deployment under this decision.
- The project remains job-focused through technical depth and measured proof, not through adding an unverified cloud platform logo.
