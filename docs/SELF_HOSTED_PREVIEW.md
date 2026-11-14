# Self-hosted local operation and recovery

This runbook describes the implemented local profile. It is loopback-only, uses a trusted operator and keeps agent execution outside the controller's writable evidence/key boundary. The [release status](STATUS.md) lists the evidence still required before full V1 acceptance.

## Services and trust

Compose starts PostgreSQL 17, a one-shot migration service, a one-shot evidence/key initializer, the FastAPI controller and the Next.js UI. PostgreSQL has no published port. API8000 and UI3000 bind127.0.0.1. API/UI run as UID10001 with read-only roots, dropped capabilities, no-new-privileges and bounded temporary storage. Native OPA 1.0.0 is pinned in the API image. The database runtime role receives SELECT/INSERT on immutable product tables; bootstrap migrations use a separate role.

CAS payloads are AES-256-GCM encrypted, with identities checked against plaintext digests and sizes after decryption. The32-byte storage key lives in a separate private volume seeded from an operator-owned0600 file. It is never returned by the API. The original capsule signature statement is retained separately from the archive. The signer private key stays outside this stack; the API receives public trust configuration only.

The operator registry supports active/retired/revoked keys and validity windows. New imports require an active key; retired keys may support historical replay, and revoked/unknown signers quarantine new replay/fork operations. An append-only SQL epoch ledger rejects registry rollback/equivocation relative to that ledger. Restoring the entire controller and ledger together can still roll back that view. Preserve a separately trusted latest checkpoint/registry witness for recovery.

The production factory additionally requires an **operator-held capsule witness directory**. It contains one authenticated final capsule statement per run ID, published atomically with no replacement. Compose mounts it read-only outside the database, CAS and their backups. Imports must match its complete signed statement. Replay, comparison and fork admission recheck the retained statement and SQL identity against it. Missing or inconsistent witnesses quarantine operations. This detects per-run replacement relative to retained operator state; it does not prove that all runs are present, establish wall-clock freshness, prevent host-admin compromise or replace the registry epoch witness.

## Prepare a private local installation

Use Python 3.12, uv 0.12.17, Docker Compose with `!override` support for the validation harness, and Node/pnpm only when developing the frontend outside Docker. Keep private configuration under `.local-controller/` or another operator-protected directory. Do not place it inside an agent workspace.

```bash
uv sync --frozen
mkdir -p .local-controller/operator/declared-agent
uv run --frozen sentinel local-anchor keygen \
  .local-controller/operator/keys .local-controller/operator/declared-agent
uv run --frozen sentinel privacy keygen .local-controller/operator/storage.key
uv run --frozen sentinel trust init \
  .local-controller/operator/keys/signing.ed25519.pub \
  .local-controller/operator/trust.json
mkdir -p .local-controller/operator/capsule-witness
chmod 755 .local-controller/operator/capsule-witness
```

Copy `deploy/local/.env.example` to a private `.env` file. Replace all three passwords/tokens with different cryptographically random values of at least32 URL-safe characters. Set the public-key, storage-key, trust-registry and operator-witness host paths to absolute paths. Restrict the `.env` and storage key to 0600. Never send credentials in a chat or commit them.

```bash
docker compose --env-file .local-controller/operator/.env \
  -f deploy/local/compose.yaml build
docker compose --env-file .local-controller/operator/.env \
  -f deploy/local/compose.yaml up --detach --wait
```

Open `http://127.0.0.1:3000` and enter the investigator bearer token. The browser stores it in an HttpOnly SameSite=Strict session cookie; it is not placed in localStorage. The BFF checks mutation origins, bounds bodies, prevents redirected bearer forwarding and proxies only run API routes. Use the configured public origin and TLS before designing any remote-access profile; remote exposure has not been validated here.

The API factory requires PostgreSQL, encrypted storage, a registry, the operator witness root and native OPA. `SENTINEL_ALLOW_PLAINTEXT_PREVIEW=1` is an explicit development escape hatch used by narrow disposable fixtures; it is not the documented production profile.

## Import and inspect

A new capsule import is streamed within a 65 MiB archive budget, fully verified, authenticated against an active configured key, put durably in encrypted CAS, then indexed in SQL. The same capsule import is idempotent; a conflicting archive under an existing run ID is rejected. A failed SQL insert can leave an orphan blob for the offline collector.

Before importing, the operator signs the capsule outside the controller and pins its final identity:

```bash
uv run --frozen sentinel capsule sign-local RUN.sentinel \
  .local-controller/operator/keys/signing.ed25519.key \
  .local-controller/operator/anchors .local-controller/operator/declared-agent
# Use the exact attestation path printed above as STATEMENT.json.
uv run --frozen sentinel capsule witness RUN.sentinel STATEMENT.json \
  .local-controller/operator/keys/signing.ed25519.pub \
  .local-controller/operator/capsule-witness .local-controller/operator/declared-agent
```

Witness statements are public verification material (0444), never signing keys. Keep the directory under separate operator ownership and outside all agent mounts; do not let the controller publish or replace witnesses. Back up this directory independently and compare it during recovery. Repeating the same valid statement is idempotent; a different statement for the same run ID fails even if signed by a valid key.

Use the signed import commands shown by `sentinel capsule --help`, or the API's octet-stream `POST /v1/runs/import` with the base64 detached statement in `X-Sentinel-Attestation`. `/openapi.json` describes the current routes. Reads require bearer grants with the requested capability and run allowlist. `SENTINEL_ACCESS_GRANTS` accepts a JSON array of hashed token grants; the separate long operator token has admin scope. See `access.py` and its negative tests before configuring additional investigators.

The UI presents timeline, provenance, replay, policies/futures, world diff and evidence. It paginates runs and events, loads Monaco assets locally, displays covered replay modes and allows inspection of completed operation receipts. Raw payload export is a separate capability. Encrypted stores default to sealed capsule downloads in the UI; the detached signature is a separate JSON file. Decrypt with `sentinel privacy decrypt` before verifying the original capsule signature.

## Background work and limits

Replay, supported forks, bisection and the fixed-corpus policy search can run as durable jobs. One controller holds the exclusive evidence-root lock; the queue is bounded, and each job runs in its own spawned process/group with a hard deadline. Requests/results are retained in encrypted CAS; status transitions and resumable SSE events are immutable SQL records. A restart marks unfinished work interrupted; completion is never inferred from a lost worker. Inspect history before retrying an uncertain operation.

JSON requests are limited to 64 KiB; there are two admitted heavy requests, a queue of eight jobs and one execution worker. Search has a 1,000-candidate/600-second ceiling. Live operation status streams use bounded30-second windows and Last-Event-ID resumption. Recorded timeline streams are finite, ordered playback; they are not a claim that arbitrary live agents are captured continuously. The finite pack caps boundaries at 50k, seed files at 100 and seed bytes at 1MB. Capsule, shard, telemetry-decompression and graph budgets fail closed.

## Backup and disaster rehearsal

Stop API and UI writers before taking the consistency set. Back up the PostgreSQL database, complete encrypted evidence root, trust registry/epoch state, and separately protected storage key. Retain signer public-key history, original detached statements and externally retained checkpoint heads. A CAS-only copy is insufficient; losing the storage key makes encrypted evidence unrecoverable. Treat backups as sensitive and manage their retention separately.

Restore into **new volumes**. Initialize schema and the same key, restore the database, copy the encrypted evidence tree, normalize ownership only on those new owned volumes, then start services. Check the expected run ID/root, exact original capsule bytes, signature, signer status, checkpoint adapters and strict covered-effect replay. Compare externally held latest witnesses before allowing operations; restored SQL alone cannot prove freshness.

The executable own-project rehearsal is:

```bash
docker build --platform linux/amd64 -t sentinel-replay-api:validation-20261113 .
docker build -t sentinel-replay-ui:validation-20261113 ui
uv run --frozen python scripts/validate_deployment.py \
  --capsule benchmarks/results/product-demo-final-2026-11-13/investigation.sentinel \
  --output .local-controller/recovery-choose-a-fresh-name
```

It generates private keys/passwords, uses unique project names and loopback ports, verifies real HTTP investigation/replay, native OPA, sealed exports, persistent job/SSE recovery, and database/CAS restoration, then removes only its own stacks/volumes. Logs, encrypted backups and keys remain private. `--browser-proof` additionally requires installed Playwright Chromium and records the actual integrated UI. The retained first rehearsal failed on initializer key ownership; that failure was fixed and later rehearsals passed. Same-host fresh-volume recovery is not independent-machine reproduction.

## Retention and audit

`sentinel retire RUN_ID --reason ...` records an admin-only logical tombstone. Reads/operations return410 afterwards; physical collection is separate. Stop the controller before `sentinel retention collect`; it defaults to dry-run and requires explicit apply. It verifies live references first, preserves shared blobs, job results and future descendants, and refuses active writers/symlinks. SQL history and backups remain. Physical unlink is not secure SSD erasure.

Access decisions are durably fsynced before access proceeds. The controller verifies its audit chain at startup and keeps an exclusive serialized writer during its lifetime; an audit outage rejects the request. Keep audits and private operator configuration outside agent mounts. Host-admin compromise and a malicious process running as the host operator remain outside the supported isolation claim.

The database image is pinned to PostgreSQL 17.12 after reviewing the November 12,2026 [security and maintenance release](https://www.postgresql.org/docs/release/17.12/). Earlier retained17.11 runs remain historical evidence. New deployments use the updated digest; this version update is not a claim that every dependency/image has received an independent security audit.

For the actual50k loopback HTTP and eight-client backpressure probe, add `--scale-capsule benchmarks/results/product-scale-final-2026-11-13/50000/scale.sentinel` to the rehearsal. It imports the separate signed50k archive, records 25 samples per query and every concurrent response status, then restores both database/CAS roots with the job history. This measures the warm sparse index over HTTP, not browser interactivity, dense graphs or a production SLO.

The published repository keeps bulky generated outputs in verified synthetic evidence bundles. Before using the50k scale-capsule option on a fresh checkout, extract `benchmarks/evidence-archives/product-scale-final-2026-11-13.tar.gz` into `benchmarks/results` after checking its digest against the archive manifest. Small unit/browser fixtures and the integrated demonstration capsule are directly present. This packaging does not change any recorded result.
