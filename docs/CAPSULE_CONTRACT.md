# Capsule contract: portable integrity preview

The first `.sentinel` capsule is a deterministic, bounded ZIP archive. The archive format itself is **unsigned and unencrypted**. A separate development Ed25519 statement can optionally sign the exact archive bytes, including its manifest, journal, and artifacts. That detached statement does not travel inside the ZIP and does not make the archive confidential or fresh. Do not export real credentials or private incident payloads into this preview.

## What is inside

- `manifest.json`: schema version 1, run ID, exact journal count and root, a sorted list of entry paths, SHA-256 digests, and byte sizes. Its integrity field explicitly says `hash-chain-and-digests;unsigned`.
- `journal.jsonl`: the exact journal bytes from the source file. Import verifies its full chain, not just the manifest digest.
- Optional `artifacts/NAME`: bounded regular files named with `--artifact NAME=PATH`. The caller decides whether an artifact is safe to export; no automatic redaction is implied.

The ZIP uses stored, uncompressed members and fixed metadata for repeatable bytes. Entry names are constrained to one flat artifact directory. Version, member set, duplicate names, file types, encryption flags, sizes, digests, and journal root are checked before an import directory is created. Import refuses an existing destination. `replay-imported` rechecks the imported file set, digests, and journal chain before invoking the **synthetic mini-agent** with live calls disabled.

## Limits and remaining risk

The current limits are 64 evidence entries, 32 MiB per entry, 64 MiB aggregate evidence, and 1 MiB for the manifest. A compressed member is rejected instead of decompressed. Verification currently holds bounded entry bytes in memory; streaming verification and fault-injected crash recovery remain release work.

The unsigned check detects inadvertent corruption or an attacker who cannot rewrite the manifest and all content. An attacker who controls the whole capsule can replace both. `capsule sign-local` writes a put-once detached Ed25519 statement over the exact verified archive digest, run ID, journal count/root, and key ID; `capsule verify-signed` re-verifies the archive and signature against a public key supplied by the caller. `capsule import-signed` imports the **same bounded byte string** it authenticated, rather than reopening a path after the signature check. A self-consistent rewrite of archive and manifest fails against the original statement before the import directory is created. The detached file and trusted public key must be retained separately. This **does not** provide a trusted key registry, process-identity isolation, anti-rollback freshness, rotation/revocation, or encryption. The development journal-root signer and optional offline-tested AWS root-signing experiment are separate paths.

Import is preflighted but not transactional if the local disk fails midway through writing the new destination. It does not make hostile concurrent filesystem races safe. An imported capsule replay only earns `BOUNDARY_REPLAY_MATCHED`, not `VERIFIED_REPLAY`: no covered process, Git, database, network, or effect state has been restored. General capsules still need typed policies, graph, snapshots, branches, coverage, and reports linked by schema rather than just optional named files.

## Learn it by breaking it

1. Record `sentinel mini record incident /tmp/my-incident.jsonl` and export it with `sentinel capsule export run-001 /tmp/my-incident.jsonl /tmp/my-incident.sentinel`.
2. Verify, import into a fresh directory, and run `sentinel capsule replay-imported incident /tmp/my-import`.
3. Change one byte in the imported journal. Confirm the replay command rejects it *before* invoking the mini-agent.
4. Read `tests/test_capsule.py`, then add one malformed archive case of your own. Explain whether it protects structure, byte integrity, journal semantics, or authenticity. The last category is **not yet protected**.

The binding target for a complete capsule is [Slice 27](EXECUTION_PLAN.md), with signature and hostile-import hardening in S53/S55. This preview does not mark any of those slices accepted.
