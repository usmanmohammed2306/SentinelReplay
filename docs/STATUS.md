# Sentinel Replay - Project Status

Last updated: **2026-10-20 (publication metadata only; engineering results retain their original dates)**  
Plan version: **4.2.0 (local-first release under ADR-0003)**  
Overall state: **IMPLEMENTATION ACTIVE**

Plan lock: **Plan 4.2 is the only active plan. It preserves the original forty-three-section V1 and makes the earlier AWS extension optional under ADR-0003.**

## Current milestone

- Stage: 1 - Foundation, contracts, journal, recorder
- Active task: `S01: Project pulse`
- Task state: `ACTIVE`
- Stage 1 gate: `TODO`

## Completed task IDs

- Product scope frozen
- ADR-0001 accepted
- ADR-0003 accepted: self-hosted V1; AWS optional
- Binding sixty-slice evidence-gated execution plan created

## Existing evidence

- `README.md`
- `docs/FROZEN_PRODUCT_CHARTER.md`
- `docs/SCOPE_TRACEABILITY.md`
- `docs/adr/0001-replay-and-counterfactual-modes.md`
- `pyproject.toml` and `uv.lock`
- `src/sentinel_replay/cli.py`
- `tests/test_cli.py`
- `.github/workflows/ci.yml`
- Detailed execution, learning, Git workflow and student lab records remain local and are excluded from the release surface.
- Local foundation preview: canonical hashes, journal, boundary matching, scripted incident/benign trajectories
- Scale and timeline preview: bounded batch append, exclusive per-call durable writer, streaming journal verification, metadata-only phase compression, and local 3k/10k/50k probes
- Optional AWS evidence preview: local/S3 CAS, KMS root attestations, version-pinned S3 anchors, offline SDK tests, linted retained CloudFormation evidence stack
- Synthetic forensic preview: typed chronological/dataflow/control edges, blast radius, three trace-policy scores, Pareto frontier
- General declared-provenance preview: bounded verified-journal graph from explicit carrier source/sink roles and prior-call dependencies; redacted edges, chronological exclusion from blast radius, untyped-carrier gaps, and edge-budget failure. It is not a causal proof or the release provenance engine.
- Provenance scoring protocol: root-bound, separately authored typed labels produce explicit TP/FP/FN and precision/recall/F1 denominators; chronological edges are excluded and undefined denominators remain undefined. No independently labeled twelve-scenario corpus or public provenance F1 exists yet.
- Persistent API preview: token-gated signed-capsule ingestion and verified archive read-back, one server-configured trusted public key, bounded streaming request, local CAS bytes, immutable/idempotent run metadata in PostgreSQL 17, Alembic migration, a restricted API database role, and a localhost-only Compose stack. This is not scoped authorization, encrypted storage, or full API coverage.
- OPA policy preview: a finite exact-match tool/host grammar compiles to Rego with default deny and deny precedence. A bounded MCP `copy_named` tool now routes real Codex calls through a durable proposal/decision/result journal and an OPA decision before one named-file effect. A digest-pinned OPA 1.0.0 Docker contract checks policy decisions and the MCP adapter. This is coverage of **one explicitly routed tool**, not interception of Codex's native shell or other tools.
- Real coding-agent observation preview: bounded Codex CLI JSONL intake emits only safe event counts and a trace digest, explicitly labeled `AGENT_OBSERVATION_ONLY`. A synthetic forbidden-copy run and benign control produced checked file effects and verified pre-run regular-file restores; the violation was an explicit synthetic instruction, not a prompt-injection claim or intercepted replay boundary.
- Bounded local workspace preview: regular-file capture to CAS, descriptor-relative no-follow capture/restore/verification, preflighted restore into a new directory, post-restore byte verification, and nested-symlink-swap regression tests
- Unsigned capsule preview: deterministic bounded archive, manifest and journal verification, hostile member rejection before import, imported-directory re-verification, and synthetic boundary replay from an import
- Development local root attestation preview: Ed25519 signature over the exact verified journal root, run ID, and record count; put-once anchor file outside the declared agent workspace, with key-permission and symlink checks. This does not yet prove a separate process identity, append-only storage, freshness, or capsule authenticity.
- Detached development capsule attestation preview: verifies the complete bounded archive, signs its exact bytes and journal reference, and detects a self-consistent archive rewrite when the original statement and correct public key are retained. Signed import consumes the same verified bytes. It has no trusted key registry, production isolation, or anti-rollback guarantee.
- `docs/CAPSULE_CONTRACT.md` describing format, limits, and missing authenticity guarantees
- `docs/THREAT_MODEL.md` describing the current local security boundary, attack cases, and unpassed release proofs
- `docs/SELF_HOSTED_PREVIEW.md` describing the reproducible local API stack and its security/recovery gaps
- `docs/POLICY_PREVIEW.md` describing the bounded policy grammar, OPA conformance test, and limited MCP gateway
- `docs/MCP_GATEWAY.md` describing the covered Codex/MCP/OPA path, retained decision journal, and bypass limitation
- Gateway semantic auditor: validates the verified journal's proposal/decision/result grammar, rejects orphan/duplicate effects and policy-digest mismatches, and reports interrupted allowed requests as unknown rather than completed.
- Named-file effect intent and reconciliation: current gateway durably records bounded source bytes/digest before copying; a no-follow inspector detects missing/mismatched outbox bytes and can finalize a matched crash-gap result once without repeating the write. This is local point-in-time recovery, not a general retry, isolation, or production durability claim.
- Conservative real-agent coverage manifest: the MCP smoke records gateway-request and observed-native-action counts, names missing authenticated call correlation and incomplete observation, and never promotes this partial coverage to strict replay. A later same-run synthetic experiment observed the native gap, but complete action coverage remains unproven.
- Disposable Docker isolation profile: one Linux/Python fixture runs with only the declared workspace mounted, no network, read-only image root, non-root UID, dropped capabilities, no-new-privileges, and resource limits. A guarded local Docker test observed a writable workspace, inaccessible sibling fake controller file, and failed test-address network connection. The real Codex/MCP run is not inside this container yet.
- Repeated synthetic performance evidence: batch journal writes use bounded 1,024-row joins instead of a second full-batch allocation; five-pair reconstructed-strategy comparison and separate five-trial-per-mode throughput reports retain raw JSON, code digests, and explicit limitations in `docs/PERFORMANCE_EVIDENCE.md`.
- `docs/PROVENANCE_EVALUATION.md` describing the independent-label protocol and metric denominators
- `docs/CODEX_OBSERVER.md` describing the real-agent event intake, bounded smoke, and unsupported replay coverage
- `docs/adr/0003-local-first-release.md`; optional `docs/adr/0002-aws-evidence-profile.md` and `deploy/aws/README.md`

## Required next work

The existing private repository received its initial code import on 2026-10-20 under a one-time publication instruction. This preserved the original README commit and the actual import date. GitHub identity and remote were verified; no learning slice was accepted by the push.

Finish `S01: Project pulse` through the existing student workflow: make one genuine modification on a branch, review its PR, run the required CI under the applicable resource permissions, and complete the teach-back. Those acceptance requirements remain pending in the local learning records.

## Test status

- Initial red state observed: `ModuleNotFoundError` before the package existed.
- Secondary red state observed: Typer collapsed the one-command app and rejected `sentinel version`.
- Red state for evidence import observed before implementation: `ModuleNotFoundError` for the boundary module.
- Red state for complete-capsule authentication observed before implementation: missing signed-capsule module and signed-import API; duplicate-key attestation tests also failed before parser hardening.
- Required `make check`: **135 passed, 1 guarded Docker test skipped, 11 optional/integration tests deselected** on 2026-10-10, including agent coverage, six named-file reconciliation cases, and two Docker-profile shape checks; Ruff format/lint and strict mypy passed. Other covered suites include journal properties, workspace path-swap defenses, capsule corruption, policy/gateway semantics, and synthetic forensic checks. Local checks are not remote CI or a production release gate.
- Guarded disposable Linux isolation conformance: **1 passed** on 2026-10-10 with a digest-pinned locally cached Python image and Docker 29.8.0. Only the declared fixture workspace was mounted and writable; an unmounted sibling fake controller file was invisible and test-address network connection failed. This did not execute Codex in the container.
- Guarded PostgreSQL 17 integration: **1 passed** against an explicitly disposable localhost container after `alembic upgrade head`.
- Guarded OPA 1.0.0 conformance: **2 passed** (plus the in-memory MCP test), covering five tool/host decisions and a denied/allowed MCP gateway pair in pinned, network-disabled Docker containers on local macOS. The GitHub job has not run yet.
- Live Codex/MCP/OPA synthetic smoke on 2026-10-07: **2 observed gateway proposals**, decisions `denied` then `allowed`, 5 verified hash-chain journal records, denied output absent, allowed public output byte-verified. The nine-event Codex stream showed **0 native command and 0 native file-change events in this run**; it cannot prove native tools are unavailable in general. [Metadata](../benchmarks/results/codex-mcp-gateway-2026-10-07.json), [redacted journal](../benchmarks/results/codex-mcp-gateway-2026-10-07.journal.jsonl), and the [frozen policy fixture](../benchmarks/fixtures/codex-mcp-gateway-policy.json) are retained. A separate semantic audit of that exact journal and policy reported 1 denied, 1 completed, and 0 interrupted-unknown requests; it still does not prove the journal's author. The Codex invocation explicitly approved only this temporary MCP server in its config; it did not disable or intercept native tools. This is neither a general attack-prevention rate nor a verified replay.
- Live Codex/MCP/OPA negative smoke on 2026-10-10: **1 denied MCP request and 1 observed native command in the same nine-event run**. The protected MCP outbox stayed empty while the native command byte-copied a separate fake fixture inside its disposable workspace. [Metadata](../benchmarks/results/codex-mcp-native-gap-2026-10-10.json) and [two-record verified journal](../benchmarks/results/codex-mcp-native-gap-2026-10-10.journal.jsonl) are retained; raw Codex events and temporary fixture were removed. This is explicit synthetic instruction evidence of an uncovered path, not a realistic adversarial success rate or an OPA failure.
- Real Codex CLI `0.162.0-alpha.2` local smokes: **3 passed** on 2026-10-07 in fresh temporary agent workspaces. A harmless file-create task, an explicit synthetic forbidden-credential copy, and a benign public-file copy each yielded 7 events, 1 completed command, a completed turn, and the expected file outcome. The latter two also captured pre/post bounded regular-file manifests and verified a clean restore of the pre-run files. Raw events, fake credential bytes, and temporary workspaces were removed. No agent replay, tool interception, prompt-injection success rate, or general restoration proof was established.
- Optional `make aws-contract`: **8 passed** with no AWS calls.
- Optional `make aws-infra`: **passed** with `cfn-lint`; no deployment or AWS service validation.
- Ruff format check: **passed**.
- Ruff lint: **passed**.
- Strict mypy: **passed**.
- Installed CLI: **`Sentinel Replay 0.1.0-dev` observed**.
- Unknown command: **exit 2 with a useful `No such command` message observed**.
- `sentinel demo-mini /tmp/sentinel-mini.j3FJWL`: incident and benign trajectories each recorded 5 actions, matched 2 strict boundary replays, and emitted distinct signatures and journal roots.
- `sentinel mini record/inspect/replay` commands are locally tested; `inspect` lists hashes and call identities without printing response bodies.
- `sentinel mini investigate` produced `TRACE_POLICY_EVALUATION incident=yes root_step=2 egress_step=3 blast_radius=[3, 4] frontier=deny_demo_host`; the JSON report did not contain the raw demo token.
- AWS anchor verification checks the expected run ID, journal root, record count, pinned S3 version, and KMS signature; all AWS behavior remains offline-tested only.
- `sentinel workspace snapshot/restore/verify` manually captured and restored 3 files with matching manifest digest. Descriptor-relative no-follow reads and writes reject tested nested-symlink swaps; coverage is still only bounded regular-file bytes and executable flags, not a point-in-time or complete hostile-race guarantee.
- `sentinel capsule export/verify/import/replay-imported` has an offline synthetic round-trip test. The archive is deliberately **unsigned and unencrypted**; its manifest and digests do not establish author identity or freshness. Replay is still only `BOUNDARY_REPLAY_MATCHED`.
- `sentinel local-anchor keygen/sign/verify` has a development Ed25519 round-trip test. Its key and anchor are placed outside the declared agent workspace, but same-user filesystem placement is not a security boundary. No process-identity denial test, rotation/recovery exercise, or fresh-root guarantee exists yet.
- `sentinel capsule sign-local/verify-signed/import-signed` has detached exact-archive signature and same-byte import tests, including self-consistent rewrite, source-swap, and duplicate-key rejection. The archive remains unsigned by default; the ordinary `capsule import` and `replay-imported` commands do not require the detached signature, and it does not prove trusted key ownership or freshness.
- `sentinel timeline` produces redacted phases and rule findings from verified boundary metadata. A rule hit is not causal proof; absent hits do not prove safety. It is not the general incident/provenance engine.
- `sentinel provenance JOURNAL ROOT_STEP --output REPORT` emits a redacted, bounded declared-dependency graph over a fully verified journal. A 3,000-event benign test remains within the edge budget; the graph is a preview, not validated real-agent provenance F1 or independent causal evidence.
- A 2026-10-07 fresh-volume local Compose build and startup succeeded with PostgreSQL 17, migration service, and unprivileged API container. `GET /healthz` returned `{"status":"ok"}` and `scripts/smoke_local_api.py` imported, indexed, and retrieved the exact bytes of a five-record signed synthetic capsule over real localhost HTTP. An in-container database query observed `current_user=sentinel_api`, `SELECT=true`, `INSERT=true`, `UPDATE=false`, and `DELETE=false` on `runs`. This validates a narrow role boundary on one macOS/Docker host, not clean-room portability, backup/recovery, TLS, or complete least privilege.
- A fresh 2026-10-07 synthetic CLI smoke in `/private/tmp/sentinel-qa-Fj2lft` completed `demo-mini → provenance(root step 2) → local-anchor keygen → capsule export → capsule sign-local → capsule import-signed`. The graph reported 5 nodes, 6 edges, and declared blast radius `[3, 4]`; signed import preserved the five-record root. The temporary signing key is synthetic development material, not a production credential.
- `make benchmark-journal` and `make benchmark-journal-stream` ran on local macOS arm64/Python 3.12.14 at 3k, 10k, and 50k synthetic events. In one 50k batch probe, append took **0.544 s**, chain verification **0.776 s**, and one-phase timeline compression **0.798 s**, with process peak RSS **64.0 MB**. In one 50k per-call durable-stream probe, append took **1.913 s**, verification **0.716 s**, timeline compression **0.541 s**, and peak RSS **24.0 MB**. These are one-run local observations, not repeated release measurements or claims about API/UI latency, full agent overhead, or concurrent production traffic.
- The updated benchmark schema v2 also includes declared-provenance construction. One 2026-10-07 local macOS arm64/Python 3.12.14 batch run at 3k/10k/50k events reported graph times of **0.031 / 0.106 / 0.559 s**, with exactly **2,999 / 9,999 / 49,999 chronological edges** and no contamination reachability. The 50k run used **64.0 MB peak process RSS**. These are separate one-run synthetic observations, not p50/p95 release evidence, validated provenance F1, or real-agent throughput.
- On 2026-10-10, five fresh-process 50K-event trials per mode measured median **0.490099 s batch append (102,020 records/s)**, **0.546619 s batch-journal verification (91,471 records/s)**, and **1.652650 s per-event durable-stream append (30,254 records/s)**. A separate five-pair alternating comparison against a benchmark-only reconstruction of the former joined writer measured **29.65% lower median peak whole-process RSS** (67,190,784 → 47,267,840 bytes) with ~0.5 s median batch append for both. [Raw trials and limitations](PERFORMANCE_EVIDENCE.md) are retained; these are synthetic one-host component measurements, not real-agent throughput, concurrent p95, or a production SLO.
- These are synthetic local boundary matches; no checkpoint restoration, real external effect, or `VERIFIED_REPLAY` claim exists yet.
- AWS signing/encryption requests remain an **optional offline-only experiment**. No real AWS account, IAM boundary, Object Lock behavior, CloudFormation deployment, or full AWS runtime has been verified or is required for local V1.
- GitHub CI: **pending successful run**. The initial private code import used `[skip ci]` under the instruction against new test runs.
- Production release gate: **not implemented or passed**. PostgreSQL metadata, a narrow API, and one OPA-backed real-agent MCP tool exist as previews, but the full API/UI, OTel, all-action interception/coverage, comprehensive restore/effect reconciliation, full policy grammar/search, twelve-scenario corpus, repeated end-to-end scale benchmarks, independent signer/anchor trust proof, scoped authorization/privacy, backup/recovery, and self-hosted clean-room install remain missing. AWS is not a gate.

## Blockers

- Initial private code import is pushed to `usmanmohammed2306/SentinelReplay`; successful CI, student PR/review and teach-back remain pending.
- GitHub CLI is not installed; the PR can be created in the browser or after installing/authenticating `gh`.
- The public-repository license choice remains unresolved.

## Decisions pending during S01

- select the project license before making the repository public;
- confirm the exact Python/tooling versions captured by the Slice 1 lockfile; later dependencies are pinned just in time by their owning task.

The repository owner, private visibility, and commit identity were verified for the initial import. The unresolved license choice still blocks a public release.

## Schedule confidence

- Calendar deadline: **none**
- Integrated alpha: **after Slice 30 and the Stage 6 gate**
- Feature-complete beta: **after Slice 40 and the Stage 8 gate**
- Complete V1: **after Slice 60 and every release gate; failed gates continue as named remediation slices**
- Release class: **Complete Flagship V1; all 43 original specification sections remain in scope**

## Pace evidence

- Focused implementation sessions completed: **at least 3 local sessions; student/GitHub gates pending**
- Accepted slices: **0 / 60**
- Rolling median sessions per accepted slice: **not available**
- Current calendar forecast: **unassessed until the Stage 1 gate; informational only**

## Locked planning decision

- Complete Flagship V1 contains all forty-three original specification sections; the later AWS extension has been withdrawn from release scope by the user.
- Sixty ordered slices define the implementation and hardening sequence, not elapsed days.
- Alpha, beta, and release are evidence gates rather than dates.
- Scope cannot be cut or evidence weakened to protect a forecast.
- The only active slice is listed at the top of this file.
