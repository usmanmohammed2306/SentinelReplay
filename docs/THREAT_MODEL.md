# Threat model: local evidence and replay

Status: **development model, not a passed release gate**  
Last reviewed: **2026-10-10**

Sentinel investigates actions taken by an autonomous agent. That agent may encounter a malicious prompt, invoke a tool with attacker-controlled input, or run untrusted code. The evidence system must not silently turn those actions into trustworthy facts. This document describes the required self-hosted boundary and the narrower behavior the current preview actually demonstrates.

## Assets and trust boundaries

| Asset | Current preview | Required V1 boundary |
| --- | --- | --- |
| Journal and workspace snapshot | Local files containing synthetic boundary records and bounded regular-file bytes | Agent cannot rewrite controller evidence after capture; declared gaps remain visible |
| Signing key | Mode-0600 Ed25519 file outside a *declared* agent directory | Separate controller identity and process boundary; agent access denied by test |
| Root anchor | Put-once file named by run ID and journal root | Independent storage or service whose authoritative latest root cannot be rewritten or rolled back by the agent |
| Capsule | Bounded ZIP with internal digests; optional detached development signature over exact archive bytes | Trusted key identity, freshness/compatibility policy, safe import, and signer isolation |
| Policy result | Synthetic trace evaluation | Enforced policy decisions and explicit branch class; no causal claim from a trace-only result |
| Narrow MCP effect | One named-copy gateway with durable OPA decision and digest-bound intent; same-run native command remains uncovered | All declared agent actions contained or mediated; stable effect identity and authenticated receipts |

The critical boundary is **agent execution → controller evidence**. The recorded agent must not be able to edit the signing key, anchor, or authoritative run metadata. Another boundary is **untrusted evidence → investigator**: a journal, capsule, tool output, or graph label is input to parse and verify, not a command to execute or an instruction to follow.

## Adversary and assumptions

Assume an attacker can control a model-visible prompt, a tool response, a repository file, and—in a compromised agent run—anything writable by the agent identity. They may try to exfiltrate a secret, forge a benign-looking trace, delete the end of a journal, replace a capsule member, or induce the investigator to open a hostile archive. They can rerun a local hash function. They cannot break SHA-256 or Ed25519, but they may steal a private key if the system exposes it to their process.

The current preview uses one macOS user for both synthetic agent and controller commands. A sibling directory and mode-0600 key therefore **do not isolate the signer from a malicious same-user process**. `O_NOFOLLOW`, regular-file checks, put-once creation, and restrictive modes reject several path tricks and accidental mistakes; they do not eliminate parent-directory races, same-user access, privileged compromise, rollback of old signed state, or filesystem backup substitution. No claim about resisting an operating-system administrator or compromised host is made.

## Claims the current code may make

- A verified journal's canonical hash chain detects inconsistent bytes in the file presented to the verifier. It does not authenticate the writer, stop whole-chain recomputation, or prove no tail was removed.
- `sentinel local-anchor sign` signs one exact `(run ID, record count, root, key ID)` statement with domain-separated Ed25519 bytes. `verify` checks that statement against the journal provided at verification time and an explicitly supplied public key. The output prefix is `DEV_LOCAL_*` because key trust, freshness, and process isolation are not established.
- Put-once publication refuses a second anchor file with the same run/root name. It does not make an unprivileged same-user directory append-only or prove the anchor is the most recent one.
- Capsule verification checks bounds, member shape, digests, and the journal chain. By default the capsule is **unsigned and unencrypted**; rewriting its contents and manifest together can produce a self-consistent forgery. An optional detached development signature covers the complete archive bytes and detects that rewrite *if* the investigator retains the original statement and already trusts the correct public key. It does not prove freshness or production key isolation.
- A synthetic boundary match and a trace-policy result are not verified state replay or proof that a live adaptive agent would behave the same way after intervention.
- One real Codex run on 2026-10-10 used a native command after a denied MCP proposal to copy fake bytes through an uncovered path. This is an explicit synthetic instruction, not a prompt-injection benchmark. A separate pinned Docker fixture kept a fake sibling controller file and network unavailable to a Python process, but Codex has not run inside that container.
- A digest-bound pre-effect intent lets local reconciliation verify a named outbox copy and finalize a matching missing result once. It does not authenticate the journal author, bind a supplied fixture root to the original run, or recover arbitrary external effects.

## Attack cases and expected defenses

| Attempt | Current expected result | Missing release proof |
| --- | --- | --- |
| Change one journal record without updating hashes | Chain verification fails | None for this narrow case |
| Rewrite the entire chain and its unsigned capsule manifest | Internal checks can pass; original detached capsule signature fails | Trusted signer isolation and authoritative freshness/anti-rollback rule |
| Replace an attestation's signature or verify with another key | Local signature check fails | Trusted key registry, rotation, revocation, recovery |
| Replace the journal with an older valid signed journal | It may verify if its matching old anchor is selected | Authoritative monotonic latest-root/freshness policy |
| Point an anchor root at a symlink or make its run directory group/world writable | Local verifier rejects it | Denial under a separate agent identity and race-resistant directory handling |
| Try to export a real secret in a capsule | Preview has no automatic prevention | Classification, encryption, authorization, redaction, and leak tests |
| Omit a model/tool/time/randomness boundary during replay | Strict matching fails only for declared recorded boundaries | Adapter coverage map, effect receipts, and fail-closed integration tests |
| Alter state outside the bounded workspace snapshot | The preview cannot detect or restore it | Explicit coverage declaration and verified restore/effect conformance |
| Use a native command after a protected MCP denial | One disposable same-run fake-data test observed the native copy while the denied MCP output stayed absent | Run the real agent inside an enforced boundary; mediate or contain every declared action path |
| Crash between an allowed effect and its terminal journal result | A digest-bound intent permits point-in-time byte reconciliation; mismatches do not finalize | Stable idempotency keys, trusted root identity, concurrent-mutation control, torn-write recovery, and independent evidence trust |
| Supply hostile ZIP paths, compressed members, or oversized members | Bounded capsule parser rejects these forms | Fault-injected import recovery and concurrent-filesystem race tests |

## Release evidence required

1. Run the agent under a distinct operating-system identity or sandbox. Attempt to read the controller key, replace an anchor, and mutate authoritative run metadata *from that identity*; record denied operations and platform configuration.
2. Define a single authoritative latest-root record per run with a monotonic sequence or equivalent anti-rollback rule. Test truncation, whole-chain rewrite, stale-but-valid signed roots, key replacement, and backup restoration. A signature alone is insufficient.
3. Promote the development signed-import path behind a trusted key registry and isolated signer, and require a declared freshness policy before production authenticated import or replay. Encryption and redaction must be tested separately.
4. Enumerate replay-sensitive boundaries and external effects for the real-agent adapter. Inject a missing recording and an uncovered effect; verify that the system refuses `VERIFIED_REPLAY` and names the gap.
5. Publish a redacted attack-test report with exact commands, platform, raw pass/fail results, and residual risks. Repeat it on a clean-room self-hosted installation and after backup recovery.

This is a testable contract, not a claim that those five conditions already pass. See [ADR-0003](adr/0003-local-first-release.md) for the local-first decision, [the capsule contract](CAPSULE_CONTRACT.md) for the current portable format, and [the execution plan](EXECUTION_PLAN.md) for the owning slices.
