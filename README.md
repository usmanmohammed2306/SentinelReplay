<p align="center">
  <img src="docs/assets/sentinel-replay-banner.svg" alt="Sentinel Replay — Counterfactual Incident Forensics for Autonomous AI Agents" width="100%" />
</p>

<p align="center">
  <strong>Reconstruct the incident. Inspect the evidence. Test the boundary.</strong>
</p>

An agent reads a credential. A few steps later, the value appears in an outbound request. The trace records both actions, buried among thousands of others. Finding the suspicious line is only the beginning: which later actions depend on it, what state can be restored, and what would a different policy actually change?

Sentinel Replay builds an investigation around those questions. Its current implementation combines a hash-chained recorder, fail-closed boundary matching, workspace snapshots, incident analysis, signed evidence capsules, and a policy-controlled tool gateway.

The repository contains runnable components and retained experiment reports. The full investigation UI, comprehensive agent containment, and production release remain under development.

## What runs today

| Capability | Implemented behavior |
| --- | --- |
| Evidence journal | Canonical event hashes, hash-chain verification, bounded batch append, and durable per-event writing |
| Boundary replay | Matches recorded call identity and request digests; missing or mismatched evidence raises `ReplayMiss` |
| Incident analysis | Redacted timeline phases, declared dependency graphs, blast radius, and a synthetic three-policy comparison |
| Workspace recovery | Captures bounded regular files to content-addressed storage, restores into a new directory, and verifies covered bytes |
| Portable evidence | Bounded capsule export/import, archive verification, and optional detached development Ed25519 signatures |
| Persistent API | Signed-capsule ingestion and verified read-back through FastAPI, PostgreSQL 17, and filesystem content-addressed storage |
| Policy gateway | One named-copy MCP tool enforces an OPA decision before its effect and records a digest-bound intent |
| Effect reconciliation | Checks actual outbox bytes after an interrupted operation and can finalize a matching missing receipt once |

The implementation is Python 3.12 with Typer, Pydantic, FastAPI, SQLAlchemy, Alembic, cryptography, and OPA/Rego. Local deployment uses Docker Compose. AWS evidence adapters are optional, offline-tested components; no AWS deployment is claimed.

## Run the evidence path

With Python 3.12 and uv 0.12.17:

```bash
uv sync --frozen
uv run --frozen sentinel version
make check

# Use a fresh directory for each demonstration.
uv run --frozen sentinel demo-mini /tmp/sentinel-first-investigation
```

The mini-agent records separate incident and benign trajectories, verifies their journals, and matches their recorded boundaries without live fallback. Its output is labeled `BOUNDARY_REPLAY_MATCHED`.

Inspect the incident and compare policies:

```bash
uv run --frozen sentinel timeline \
  /tmp/sentinel-first-investigation/incident.jsonl \
  --approved-host internal.demo.invalid --output /tmp/sentinel-timeline.json

uv run --frozen sentinel provenance \
  /tmp/sentinel-first-investigation/incident.jsonl 2 \
  --output /tmp/sentinel-provenance.json

uv run --frozen sentinel mini investigate \
  /tmp/sentinel-first-investigation/incident.jsonl \
  /tmp/sentinel-first-investigation/benign.jsonl \
  --output /tmp/sentinel-policy-report.json
```

The policy comparison is labeled `TRACE_POLICY_EVALUATION`: it tests recorded actions against three policies on the declared synthetic incident/benign pair. It does not measure how a live agent adapts after a block. The demonstration uses deliberately fake data; do not put real secrets into its unencrypted recordings.

For capsule signing and the HTTP storage path, follow the [capsule contract](docs/CAPSULE_CONTRACT.md) and [local API guide](docs/SELF_HOSTED_PREVIEW.md). The API is a localhost preview with static-token access and one configured trusted public key.

## The result that exposed the boundary

A real Codex/MCP/OPA experiment first established that the named-copy gateway could deny a fake credential copy and allow a public-file copy. A later same-run experiment made the limitation concrete: OPA denied the MCP request, then the agent used one native command to copy separate fake bytes outside the gateway.

The protected outbox remained empty. The broader agent execution was still uncovered.

That negative result is retained alongside the successful integration. The coverage manifest labels the run `partial` and refuses strict-replay eligibility. A separate Docker fixture checks host-file and network separation, but the real agent has not yet run inside that container.

Read the [gateway experiment and limitations](docs/MCP_GATEWAY.md), [retained native-action report](benchmarks/results/codex-mcp-native-gap-2026-10-10.json), and [observation contract](docs/CODEX_OBSERVER.md).

## Evidence you can inspect

| Evidence | Scope |
| --- | --- |
| Local checks, October 10 | 135 tests passed, one guarded Docker test skipped, and 11 optional/integration tests deselected; format, lint, and strict typing passed |
| Real OPA integration | Two guarded local tests passed; one explicitly routed MCP tool is covered |
| Crash-gap reconciliation | Six focused tests include terminal-result-write failure, missing/mismatched bytes, symlink refusal, and repeated finalization |
| Historical 50K-event journal comparison | Five paired fresh-process trials measured 29.65% lower median whole-process peak RSS against a reconstructed former writer |
| Native-tool coverage experiment | One explicit synthetic run observed one denied MCP request and one uncovered native command |

The 50K figures belong to the source revision recorded in the raw reports. The current journal source differs; those figures are not current-checkout or production throughput measurements. The [performance note](docs/PERFORMANCE_EVIDENCE.md) retains the full source bindings, commands, environment, trial counts, and limits. Tests were not rerun for the October 20 repository import, and successful hosted CI remains pending.

## Guarantees and open boundaries

- Journal hashes establish internal consistency of presented bytes. Author identity and freshness require a separately trusted signing/anchoring boundary.
- Recorded call matching and verified workspace restoration are separate checks. The current mini-agent does not earn `VERIFIED_REPLAY`.
- Workspace snapshots cover bounded regular-file bytes and executable flags. Git state, databases, processes, and remote effects are outside that adapter.
- Provenance represents declared dependency candidates. Chronological edges do not expand contamination reachability; independent release-corpus F1 remains unmeasured.
- The MCP gateway covers one routed tool. Native shell, other tools, and arbitrary external effects are not comprehensively intercepted.
- Capsule signatures authenticate exact bytes against a supplied trusted key. Production key isolation, freshness, encryption, scoped authorization, and recovery gates remain open.

The [frozen product charter](docs/FROZEN_PRODUCT_CHARTER.md) defines the complete target: recording, incident compression, provenance, verified restoration/replay, alternate futures, intervention search, and an integrated investigation interface. [Project status](docs/STATUS.md) distinguishes implemented components from the remaining acceptance work.

## Technical documentation

- [Threat model](docs/THREAT_MODEL.md)
- [Replay and counterfactual modes](docs/adr/0001-replay-and-counterfactual-modes.md)
- [Policy grammar](docs/POLICY_PREVIEW.md)
- [Provenance evaluation protocol](docs/PROVENANCE_EVALUATION.md)
- [Scope traceability](docs/SCOPE_TRACEABILITY.md)
- [Local-first deployment decision](docs/adr/0003-local-first-release.md)

## License

No open-source license has been selected yet. Repository access does not grant permission to reuse, modify, or distribute the source.
