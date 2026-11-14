# Deterministic regular-file environment pack, version 1

This contract is frozen before its corpus measurements. It complements the live
Docker coding-agent adapter; it does not turn that adapter's native Python into
strict replay.

The pack accepts a finite typed action program, not Python or shell code. It
supports bounded basename-only regular-file reads/writes/deletion; simulated
HTTP, handoff and environment effects materialized as files; fixed model/process
stubs; and explicitly recorded clock/RNG inputs. It executes no capsule commands,
native process or real network request. Git and database state are separate
snapshot adapters. Unsupported native effects produce unknown, never success.

Every run freezes its program, policy source, decision vector, checkpoint and
adapter source identity before effects. Real OPA evaluates the complete bounded
proposal metadata batch; each decision is bound to its exact normalized action.
Denial or confirmation does not execute an effect. A durable intent precedes each
file mutation, and the terminal receipt names the resulting state digest. Missing
policy decisions or unavailable OPA stop execution. The pack agent is a known
script; policy-conditioned continuations are simulations, not unseen live attacks.

Strict replay restores and verifies a fresh covered checkpoint, checks the exact
adapter and program, matches every recording in order, uses recorded nondeterminism
without live callbacks, re-executes declared file effects only in that fresh
directory, and compares per-effect and final state digests. Missing, reordered or
changed inputs stop replay. Only that complete supported path may emit
`VERIFIED_REPLAY`, scoped to this version's regular-file/simulated-effect pack.
Unsigned internally consistent bytes still do not establish author or freshness.

Corpus ground truth is specified independently of graph construction, using
program step identities and expected dependency pairs. Resolved labels bind to
the completed journal root. The implementer authors both fixture and graph code;
these are injected synthetic labels, not independent human adjudication or
real-agent provenance accuracy. Undefined metric denominators remain undefined.

Twelve named scenarios retain raw source, decisions, positive/negative outcomes,
coverage gaps and exact denominators. The long benign scenario has at least3,000
steps. The uncaptured-effect scenario must remain unsupported. Never omit it to
inflate fidelity or prevention. A future change to this coverage requires a new
adapter identity and conformance evidence.

## Current storage and authenticity details

Each recording receives a fresh random identity before effects; repeating the same program creates a distinct run ID. A fresh32-byte provenance HMAC key is stored in the raw CAS and bound into the definition. Replay must recover that exact key; it cannot invent one. Authorized payload export includes raw replay material, so use encrypted storage/sealed export and the separate export capability for sensitive evidence.

Optional recording-time signing requires both an external private key and a protected anchor root. The default interval is1,000 durable boundaries; allowed intervals are100..50,000 so a 50k recording stays within 512 checkpoints. The ledger starts with an empty prefix and ends with the final recorded root. Its public history can travel in the capsule; the private key cannot. The controller retains the original ledger head separately. The verifier distinguishes a supplied-head match from portable history with no external freshness.

The capsule packages regular-file CAS through bounded8 MiB parts/approximately16 MiB shards rather than a ZIP member per blob. OTLP enrichment is losslessly compressed with an explicit32 MiB decompression limit. Git and SQLite manifests are bound into the definition; replay dispatches through the closed checkpoint registry and requires every declared adapter to restore successfully. Git is a quiescent regular repository snapshot; SQLite is a committed backup snapshot. Neither claims full live process, filesystem or arbitrary database rollback.

The combined nested three-policy demo is limited to 10k program actions by portable archive budgets. The separate scale harness records/exports/indexes50k boundaries. All source hashes and recorded outcomes retain their own measurement snapshot; later source changes intentionally invalidate strict replay compatibility instead of silently updating old evidence.
