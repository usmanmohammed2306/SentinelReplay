# Local API deployment preview

Sentinel can now accept a signed synthetic incident capsule over HTTP, verify its exact bytes against one server-configured public key, store the archive in local content-addressed storage, and index the run in PostgreSQL 17. This is a working self-hosted **preview**, not the complete V1 deployment. It does not yet run an agent, restore an incident environment, or enforce production identity and privacy controls.

## What the local stack runs

The Compose stack starts PostgreSQL, creates a restricted `sentinel_api` database role, applies the Alembic migration using the bootstrap role, then starts the API as an unprivileged container user connected as `sentinel_api`. That role has `SELECT` and `INSERT` on the run index, not `UPDATE` or `DELETE`. PostgreSQL is reachable only on the private Compose network. The API is published on `127.0.0.1:8000`; it does not provide TLS. The API requires a bearer token for run endpoints and verifies detached capsule statements using a public key mounted read-only from the host. The corresponding private key must remain outside this stack and outside any agent workspace.

An import follows this order: bound the request body; parse and verify the complete capsule; verify its detached Ed25519 statement against the configured key; durably put the exact archive bytes in the local content-addressed store; then insert immutable run metadata in PostgreSQL. Repeating the same import is idempotent. A different capsule under the same run ID returns a conflict. An authenticated `GET /v1/runs/{run_id}/capsule` checks the stored digest, size, and indexed run metadata before returning the bytes; corruption produces a service error, not a silently altered archive. A failed database insert may leave an unreferenced content-addressed blob, so a future retention job must reconcile those blobs.

## Run the synthetic smoke test

1. Create an empty throwaway agent directory and a separate controller directory. Run `sentinel local-anchor keygen CONTROLLER_DIR AGENT_DIR`. Keep `signing.ed25519.key` out of Git and out of any agent-writable directory.
2. Copy [`deploy/local/.env.example`](../deploy/local/.env.example) to a private `deploy/local/.env`. Set **different** unique URL-safe passwords for the bootstrap and API database roles, a random API token of at least 32 characters, and the absolute path to `signing.ed25519.pub`. The `.env` file is ignored by Git. Never use the example values as credentials. The role-init script runs only when PostgreSQL initializes a new volume; adding it to an existing volume does not retrofit the role.
3. From the repository root, run `docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml up --build -d`. Check `curl --fail http://127.0.0.1:8000/healthz`; it should return `{"status":"ok"}`.
4. Record only synthetic data with `sentinel demo-mini AGENT_DIR`. Export one recording with `sentinel capsule export run-001 AGENT_DIR/incident.jsonl CAPSULE.sentinel`, then sign it with `sentinel capsule sign-local CAPSULE.sentinel CONTROLLER_DIR/signing.ed25519.key ANCHOR_DIR AGENT_DIR`.
5. With `SENTINEL_API_TOKEN` set in your shell to the same private token, run `python scripts/smoke_local_api.py --capsule CAPSULE.sentinel --attestation ANCHOR_DIR/capsules/run-001/CAPSULE.sentinel.sig.json`. The script checks health, imports the capsule, retrieves its metadata, and prints only the run ID, count, and root.

`docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml down` stops the stack while retaining PostgreSQL and evidence volumes. Do not use `down --volumes` unless you intend to delete the data in that specific deployment. Backups and recovery are not yet implemented.

## Claims this preview does not earn

- The static bearer token grants both import and full-archive read-back. It is not scoped authorization or user identity. Archives may contain sensitive incident evidence; the localhost endpoint needs a TLS-terminating, authenticated front end before remote exposure.
- The API has a restricted database role, but this is not a comprehensive least-privilege review. Its evidence volume is not encrypted at rest.
- The signer is a separate *path*, not yet a separately isolated identity or service. The configured public key has no rotation, revocation, or authoritative freshness policy.
- The ordinary unsigned capsule import and imported replay commands still exist. The API requires a detached signature, but a later `replay-imported` invocation does not recheck that signature.
- This stack contains no isolated agent runner, effect receipts, OTel collector, worker, UI, policy engine, backup job, or disaster-recovery proof. A healthy API is not `VERIFIED_REPLAY` or a passed release gate.

The local tests cover malformed signatures, request limits, idempotence, run-ID conflict, corrupt read-back, SQL migration, and a guarded PostgreSQL integration case. A live synthetic Compose smoke passed on 2026-10-07. GitHub CI has not run until the user pushes the repository. Follow [the status file](STATUS.md) and [the binding plan](EXECUTION_PLAN.md) for the remaining V1 gates.
