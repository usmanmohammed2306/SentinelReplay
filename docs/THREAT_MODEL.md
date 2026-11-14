# Threat model and residual boundaries

Updated November 13,2026. This document describes the current implementation, including tested negative controls and unpassed release proofs. See [STATUS.md](STATUS.md) for exact results and [ENVIRONMENT_PACK_CONTRACT.md](ENVIRONMENT_PACK_CONTRACT.md) for replay coverage.

## Assets and adversaries

Protect source evidence, declared checkpoint bytes, authorization/policy decisions, original signature statements, private payloads, storage/signing keys, durable operation state and the investigator's browser. Assume an attacker may control model-visible prompts, repository content, tool responses, an agent's writable workspace, and a supplied capsule's entire contents. They can recompute ordinary hashes and present old valid evidence. SHA-256, AES-GCM and Ed25519 are assumed cryptographically sound; their key ownership and use must be checked separately.

The custom coding agent runs in pinned non-root Docker with no network, a read-only image root, dropped capabilities and one disposable workspace mount. Controller evidence, policy sources, model credentials, signing keys and Docker socket are absent from that mount. The controller brokers covered requests. A real guarded test checks denied sibling-controller access and network use. Host-administrator compromise, a malicious Docker daemon and malicious same-user host processes are outside this container boundary. A sibling host directory plus0600 permissions alone does not isolate mutually hostile host processes.

The finite pack is trusted typed data interpreted by a closed adapter, never capsule-provided Python/shell. Native process/network/model actions are stubs or declared simulations. Git/SQLite restore uses closed adapter identifiers and bounded manifests; it never imports arbitrary adapter code. Legacy/native/custom-agent traces do not gain semantic replay from a forged mode label.

## Evidence guarantees

- The verified journal checks every presented hash-chain record. Durable pre-effect intent precedes a covered mutation. A failed recorder or scheduled signer checkpoint aborts recording; a failed intent checkpoint prevents its effect.
- Optional signed progress ledgers bind an empty prefix, monotone counts, journal prefix roots and the previous signed checkpoint. Verification rejects tail mismatch, rewrites, wrong signer and rollback **relative to a separately supplied retained ledger head**. The portable ledger cannot prove no later head exists.
- Detached capsule signatures authenticate exact archive bytes against configured operator keys. The original statement is retained. Active/retired/revoked states and validity windows are enforced for admission/operations. Registry epoch rollback/equivocation is refused relative to the persisted SQL ledger. Whole-controller/backup rollback requires an external witness to detect.
- Source digests, recording nonce, frozen program/policy/action identities, decision vector, Python compatibility and checkpoint identities bind strict finite-pack replay. Missing recordings, changed source, missing provenance key, unsupported effects or altered final state fail closed. Restored workspaces are fresh; real nondeterminism is never silently queried during strict replay.
- Provenance follows declared typed carriers/dependencies. Per-recording random HMAC keys prevent ordinary cross-run carrier equality and simple public-key dictionary attacks. The key is retained as authorized raw replay material, not returned in metadata. OTel parentage and chronology do not become contamination edges. This is not independently established causal inference.

## Privacy and access

Production-profile CAS and portable sealed export use AES-256-GCM with checked plaintext identities and authenticated metadata. At-rest encryption does not protect an authorized controller process that can read its key. Child operations may have plaintext in private bounded scratch while running; no untrusted agent is mounted there. Signer private keys remain outside the API. Keys and database/CAS backups require separate protected retention.

Bearer grants use stored token hashes, explicit capabilities and run allowlists. API checks scope before reading/exporting/operating; SQL applies allowlists before pagination. Raw payload export is separate from redacted metadata. Timeline projection omits payloads and suppresses request hashes for secret/carrier-bearing boundaries. Metadata labels remain declared identifiers: this is not a universal declassifier for arbitrary hostile strings. Signed import requires trust in the operator that admits the payload.

The browser uses HttpOnly SameSite=Strict cookies, mutation-origin checks, no localStorage token, bounded BFF requests, redirect refusal and locally hosted editor assets. Only loopback HTTP is validated. TLS/remote multi-tenant identity and remote browser exposure have no production claim.

Access audit records are fsynced before access proceeds. Startup verifies its chain once; a serialized exclusive writer avoids rescanning it per request. An audit outage rejects access. The controller and its filesystem are trusted; audit files are not immutable against the host administrator.

The self-hosted factory also requires a separately operator-held final capsule witness. Compose mounts that directory read-only; no signing private key is mounted. A witnessed run ID cannot be replaced by another validly signed capsule after resetting SQL/CAS. Replay compares the retained statement and database identity with the witness and quarantines missing/mismatched witnesses. Real Docker checks exercise write refusal and removal/recovery. This is per-run consistency relative to retained operator state, not global latest-state freshness, complete run enumeration or protection against an administrator who controls both sides.

## Availability and recovery

Archive member/byte bounds, no path traversal, duplicate-key rejection, bounded decompression, finite action/graph limits, two heavy requests, a bounded queue, one worker and hard job deadlines limit exposed work. SSE windows are bounded and resumable. This is not a concurrent-load/SLO proof.

Job request/result blobs and SQL status transitions survive restart; lost in-flight work is marked interrupted rather than inferred successful. Child processes have their own process group and private scratch. A stopped-writer database plus encrypted CAS backup was restored into fresh volumes and exact imported replay checked. Same-host recovery does not establish independent installation, external latest-state freshness, or recovery after storage-key loss.

Logical retirement immediately denies run access. Offline physical collection requires the controller lock, verifies live references first, preserves shared/future/job references, and uses no-follow descriptor-relative removal. It does not erase SQL history/backups or guarantee secure SSD deletion.

## Executed negative controls and remaining proofs

| Attempt | Observed or enforced behavior | Remaining limit |
| --- | --- | --- |
| Corrupt journal/member, duplicate JSON key, hostile archive path | Verification/import rejects | Full malicious-host filesystem race resistance is not established |
| Rewrite a self-consistent unsigned capsule | Internal hashes can agree; retained original signature detects changed bytes | Correct signer trust and separately held latest witness remain necessary |
| Remove anchored tail or present old ledger against a newer head | Prefix/tail/witness verification rejects | Portable history alone lacks absolute freshness |
| Fail intent/signing boundary before a covered write | Effect absent and no completed report | Not general rollback of arbitrary external systems |
| Revoke signer / roll back registry epoch | New replay/import is quarantined or registry returns unavailable | Already admitted work and rollback of controller plus ledger require operator handling |
| Cross-run/capability request, missing bearer, oversized JSON | Scope refusal,401/403 or413; access audit retained | Representative concurrency and remote identity remain unvalidated |
| Native Codex action after denied MCP request | Historical same-run synthetic test observed an uncovered copy | Custom Docker containment is a separate adapter; arbitrary native semantic replay is not claimed |
| Missing key/wrong AES key/tag corruption | Decryption/replay refuses | Recovery requires the original storage key |
| Crash/restart worker, second controller, active-writer collection | Interrupted state / exclusive-lock refusal / no collection | No exactly-once claim for arbitrary remote effects |
| Delete retired shared data or follow deletion symlink | Reference preservation and symlink refusal tests pass | Backups and metadata have their own retention lifecycle |

Release still requires independently reviewed labels/overreach, signer/retained-head boundary recovery review, representative overhead/load evidence, clean reproduction, hosted CI and owner approval. The local release audit exposes those gaps. Neither the threat model nor a passed unit suite establishes full production readiness.
