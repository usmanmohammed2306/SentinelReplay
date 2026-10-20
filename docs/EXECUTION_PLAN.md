# Sentinel Replay - Binding Feature-First Execution Plan

Status: **LOCKED, ACTIVE, AND BINDING**  
Plan version: **4.2.0 (local-first release under ADR-0003)**  
Effective date: **2026-10-07**  
Owner: **single experienced engineer learning by building**  
Schedule model: **evidence-gated; no fixed calendar deadline**  
Integrated alpha: **after accepted Slice 30 and Stage 6 gate**  
Feature-complete beta: **after accepted Slice 40 and Stage 8 gate**  
Complete V1 release: **after accepted Slice 60 and every release gate**

This plan builds the Complete Flagship V1 through sixty executable vertical slices. V1 is the entire forty-three-section ambitious source specification, not a prototype or reduced MVP. Slices 1-40 build the integrated system and full feature surface. Slices 41-60 provide mandatory correctness, security, reliability, scale, clean-room, and release-proof work. A slice may take one focused session or several; progress is accepted by evidence rather than elapsed time. Scope is not reduced, and no session exists merely to create activity.

`docs/STATUS.md` identifies the one active slice. `docs/LEARNING_PYRAMID.md` defines how each slice is learned. `docs/GITHUB_WORKFLOW.md` defines how it is published.

## 1. Authority

The authority order is:

1. `docs/FROZEN_PRODUCT_CHARTER.md` - product scope and completion contract
2. `docs/adr/*.md` - accepted technical semantics
3. `docs/LEARNING_PYRAMID.md` - learning method
4. this plan - implementation order and gates
5. `docs/STATUS.md` - current slice and evidence
6. tested implementation and generated reports

When documents conflict, the higher authority wins until the conflict is corrected explicitly.

## 2. The feature-first rule

Every focused working session must move a runnable capability or its test evidence forward. A session cannot consist only of artificial activity. A difficult slice may span multiple sessions, but each session should leave inspectable code, a test, an experiment, a diagnosis, or a verified artifact.

Every slice must include:

1. one user-visible outcome through CLI, API, UI, or an inspectable artifact;
2. one failure demonstrated before implementation;
3. one focused automated test;
4. a property test with Hypothesis when the invariant has a meaningful generated input space;
5. the smallest working implementation;
6. inspection of real output rather than only a green test;
7. one student-directed modification or edge case;
8. a lab note and teach-back;
9. a focused pull request merged only after the complete slice passes CI and self-review.

Documentation, security, and performance are written or tested in the slice that creates the associated behavior. They do not become detached paperwork phases.

## 3. Session rhythm

```text
10 min  - rerun the previous session's visible capability
20 min  - explain the current concept and invariant
20 min  - write/observe the failing test
90 min  - build the smallest vertical slice
30 min  - test, inspect output, and add one edge case
20 min  - student modification and teach-back
20 min  - lab note, PR, CI review, and merge
```

Time is guidance, not a deadline. If a slice takes longer, it continues into later sessions. We do not cut its acceptance evidence, merge unfinished work, or invent filler to preserve calendar appearance.

## 4. Completion states

- `TODO`: no accepted evidence exists.
- `ACTIVE`: the only slice currently being learned and implemented.
- `BLOCKED`: a named dependency prevents progress and a recovery action is recorded.
- `DONE`: visible behavior, tests, inspection, student variation, lab note, CI, and merged PR all exist.

Only one slice is active at a time.

## 5. Fixed technology choices

| Layer | Choice |
| --- | --- |
| Core | Python 3.12, `uv`, `asyncio` |
| CLI | Typer |
| API | FastAPI |
| Schemas | Pydantic v2 |
| Metadata | PostgreSQL 17, SQLAlchemy 2, Alembic |
| Blob storage | filesystem content-addressed store behind `BlobStore` |
| Telemetry | OpenTelemetry/OTLP through a versioned adapter |
| Policy | OPA/Rego behind `PolicyEngine` |
| Isolation | Docker with a Linux environment pack |
| Snapshots | overlayfs adapter plus explicitly labeled full-directory fallback |
| Graphs | NetworkX behind a graph interface |
| Frontend | Next.js, React, TypeScript, Tailwind, shadcn/ui |
| UI libraries | React Flow, Monaco, Recharts, TanStack Virtual, Framer Motion |
| Tests | pytest, Hypothesis, Playwright |
| JavaScript | pnpm with lockfile |
| CI | GitHub Actions |
| Deployment | Self-hosted Docker Compose with PostgreSQL, isolated runtime, independent signer/anchor, backup and recovery; AWS adapter optional |

Technology changes require an ADR when they affect a frozen behavior or guarantee.

## 6. Target repository layout

```text
apps/
  api/
  web/
packages/
  contracts/
  recorder/
  journal/
  storage/
  snapshots/
  replay/
  incidents/
  provenance/
  policy/
  capsules/
  cli/
  otel_adapter/
  scripted_agent/
environment_packs/
corpus/
deploy/
benchmarks/
docs/
scripts/
```

A directory is created only when the active slice gives it executable behavior.

## 7. Cross-cutting invariants

These invariants apply from their first implementation slice onward.

### Replay

- Missing, exhausted, reordered, incompatible, or mismatched evidence raises `ReplayMiss`.
- Strict replay never falls through to a live model, network, clock, RNG, or undeclared tool.
- Request digest alone never identifies repeated calls; stable call identity and sequence position are required.
- Replay, restoration, simulation, and exploration remain separate modes under ADR-0001.

### Evidence

- Hashed values use versioned canonical serialization and domain separation.
- Sensitive payloads use references, redaction, encryption, and keyed fingerprints as applicable.
- A local hash chain is not called immutable.
- Evidence roots become trustworthy only through a signer or anchor outside the recorded agent's writable boundary.

### State restoration

- Restore operates inside an isolated root and rejects path escape.
- Untrusted paths are never followed through unsafe symlinks.
- Restore is verified after application before it is reported successful.
- Git, database, process, and remote state claims remain adapter-specific.

### Provenance

- Every edge is typed and explainable.
- Chronological edges never imply contamination.
- OTel parentage is structural evidence, not automatic causal proof.
- Blast radius traverses declared evidence-bearing edges only.

### Policy search

- Every returned candidate was actually evaluated.
- “Least disruptive” is relative to a declared corpus and transparent cost vector.
- The Pareto frontier is shown before an optional weighted recommendation.
- Trace policy evaluation does not claim to know adaptive post-block behavior.

## 8. Required checks

The repository grows these commands just in time:

```text
make format-check
make lint
make typecheck
make unit
make property
make integration
make web-test
make e2e
make security-test
make benchmark
```

A command becomes mandatory once its owning slice introduces it. Required checks may not be silently skipped or quarantined.

### Optional AWS experiment

ADR-0003 removes AWS from the binding release path. `make aws-contract` and `make aws-infra` still inspect the existing experimental adapter offline, but neither a cloud account nor a real-service result is needed for a local V1 release. The local signer/anchor, access boundaries, deployment, recovery, and scale gates remain mandatory. An optional cloud test cannot repair a failed local gate or justify a production claim about AWS.

## 9. Sixty executable slices

Slices use the stable identifiers `S01` through `S60`. They express sequence only, not calendar duration. Stage and slice gates control progress.

## Stage 1 - Record and replay something real

Goal: complete the stage with a small agent run that can be recorded, verified, inspected, and replayed from the CLI.

### Slice 1 - S01: Project pulse

Visible outcome:

```text
$ sentinel version
Sentinel Replay 0.1.0-dev
```

Build:

- verify Git identity and GitHub contribution attribution;
- initialize `main` and push the reviewed planning baseline;
- create the minimal Python package and Typer CLI;
- begin with a failing CLI smoke test;
- add only the Python formatting, linting, typing, and test configuration required now;
- add GitHub Actions for those checks;
- publish the first code PR and merge it into `main`.

Student edge case: verify unknown CLI commands fail with a useful nonzero exit.

Gate: a clean local install and GitHub CI both execute `sentinel version` successfully.

### Slice 2 - S02: Canonical event fingerprint

Visible outcome:

```text
$ sentinel hash-event event.json
sha256:...
```

Build:

- versioned canonical JSON for the types currently needed;
- domain-separated SHA-256 event hashing;
- explicit behavior for Unicode, bytes, datetimes, enums, lists, maps, nulls, and unsupported floats;
- Pydantic `RunManifest` and minimal event contracts.

Tests:

- unit tests for golden fixtures;
- Hypothesis: map insertion order never changes the digest;
- Hypothesis: list reordering changes the digest when elements differ.

Student edge case: add one unsupported value and make the failure readable.

### Slice 3 - S03: Tamper-evident journal

Visible outcome:

```text
$ sentinel journal append run.jsonl event.json
$ sentinel journal verify run.jsonl
CHAIN VALID records=1
```

Build:

- append-only record format with index, previous hash, and record hash;
- streaming verifier with earliest invalid position;
- exclusive writer behavior and durable flush rule.

Tests:

- mutation, deletion, insertion, reordering, truncation, and partial final write;
- Hypothesis: any changed canonical body invalidates that record or a downstream link.

Student edge case: corrupt the first and final records manually and compare reports.

### Slice 4 - S04: Fail-closed boundary recording

Visible outcome:

```text
$ sentinel boundary-demo --record recording.jsonl
$ sentinel boundary-demo --replay recording.jsonl
REPLAY MATCHED calls=...
```

Build:

- `BoundaryCall`, stable call ID, occurrence, sequence position, request digest, and adapter identity;
- record and `VERIFIED_REPLAY` modes;
- clock and RNG adapters;
- typed `ReplayMiss` reasons.

Tests:

- repeated identical calls replay in the original order;
- replay from the middle initializes the correct cursor;
- missing or skipped calls never trigger a live invocation;
- Hypothesis: arbitrary valid call sequences round-trip exactly.

Student edge case: delete one repeated call and observe the mismatch rather than a shifted response.

### Slice 5 - S05: First recorded agent run

Visible outcome:

```text
$ sentinel demo-mini
recorded -> verified -> replayed
```

Build:

- a small deterministic `ScriptedAgent` with read, write, clock, RNG, and controlled network-like actions;
- structural signature for its action sequence;
- one benign trajectory and one credential-to-egress incident trajectory;
- `record`, `inspect`, and `replay` CLI flow.

Tests:

- record once and replay twice with identical supported outputs;
- replay with network disabled to prove no live fallback;
- end-to-end CLI test.

Student edge case: alter one request and explain the resulting replay miss.

Stage 1 gate: the user can trace one action from agent decision to boundary call, journal record, verification, and replayed result.

## Stage 2 - Persist, classify, and see the run

Goal: make recorded runs queryable and visually understandable.

### Slice 6 - S06: Content-addressed evidence store

Visible outcome:

```text
$ sentinel blob put sample.txt
sha256:...
$ sentinel blob verify sha256:...
BLOB VALID
```

Build:

- `BlobStore` interface and filesystem CAS;
- streaming hash, atomic publish, verified read, metadata, and safe digest paths.

Tests:

- concurrent identical puts converge on one valid object;
- partial writes never become addressable;
- corruption is detected;
- Hypothesis: arbitrary byte payloads round-trip.

### Slice 7 - S07: Ingest a run into PostgreSQL

Visible outcome:

```text
$ sentinel ingest run.jsonl
RUN INGESTED steps=...
$ sentinel runs
```

Build:

- Compose PostgreSQL service;
- SQLAlchemy models, first Alembic migration, and repository interfaces;
- chain verification before persistence;
- idempotent run/step ingestion.

Tests:

- duplicate ingestion creates no duplicate events;
- invalid chains never enter accepted run tables;
- transaction rollback leaves no partial run.

### Slice 8 - S08: Detect and compress an incident

Visible outcome:

```text
$ sentinel inspect RUN_ID
3,184 events -> 8 phases
```

Build:

- deterministic rule model and initial credential, egress, persistence, evasion, tampering, unauthorized-tool, and unclassified phases;
- evidence records for every hit;
- consecutive phase compression.

Tests:

- rule output is deterministic;
- no-hit means `unclassified`, never “safe”;
- Hypothesis: phase compression expands back to the original phase sequence.

Student edge case: add one rule and one false-positive fixture.

### Slice 9 - S09: Merge OpenTelemetry without corrupting evidence

Visible outcome:

```text
$ sentinel otel import spans.json RUN_ID
MERGED exact=... ambiguous=... unmatched=...
```

Build:

- versioned OTel GenAI adapter;
- exact call-ID merge and visibly labeled fallback matching;
- trace/span/parent, model, token, and latency enrichment;
- journal remains authoritative for replay fields.

Tests:

- OTel cannot overwrite journal arguments or results;
- ambiguous matches remain unmerged;
- adapter-version fixtures protect convention drift.

### Slice 10 - S10: Live compressed timeline

Visible outcome: open a real web page showing a run list and a live 3,000-step run collapsed into phases.

Build:

- FastAPI run/timeline/incident endpoints and SSE stream;
- create the pnpm/Next.js workspace just in time;
- frontend checks and one Playwright smoke test;
- virtualized expanded rows and collapsed phase timeline.

Tests:

- API pagination and SSE event ordering;
- Playwright selects an incident phase and opens its steps;
- measured first render for the 3,000-step fixture.

Stage 2 gate: record, ingest, enrich, classify, stream, and inspect a long run through CLI and UI.

## Stage 3 - Restore state and replay from it

Goal: reproduce covered workspace and Git state, then replay from a verified checkpoint.

### Slice 11 - S11: Capture a workspace checkpoint

Visible outcome:

```text
$ sentinel snapshot capture ./workspace
snapshot_id=... files=... logical_bytes=...
```

Build:

- environment-pack contract and digest;
- canonically sorted snapshot manifest;
- regular files, directories, modes, symlinks, and deletions;
- CAS reuse and logical/new byte accounting;
- database adapter contract in unsupported-by-default state.

Tests:

- identical state yields the same snapshot ID;
- changed bytes or mode changes the ID;
- Hypothesis: manifest entry order cannot change the ID.

### Slice 12 - S12: Restore without escaping

Visible outcome:

```text
$ sentinel snapshot restore SNAPSHOT_ID ./restore
RESTORE VERIFIED
```

Build:

- isolated fresh-root restore;
- descriptor-relative or equivalent race-resistant path operations;
- safe deletions, broken symlinks, and post-restore verification.

Tests:

- traversal, absolute path, duplicate normalized path, malicious symlink, missing blob, and corrupt blob;
- Hypothesis: generated unsafe paths never escape the restore root.

Student edge case: create a symlink escape attempt and inspect the structured rejection.

### Slice 13 - S13: Restore declared Git state

Visible outcome:

```text
$ sentinel git-state capture ./repo
$ sentinel git-state restore STATE_ID ./restored-repo
GIT STATE VERIFIED
```

Build:

- worktree coverage plus HEAD, required refs/objects, index bytes, and repository identity;
- explicit exclusions for remote-server state and unsupported submodules.

Tests:

- staged, unstaged, untracked, deleted, renamed, mode-changed, and detached-HEAD fixtures.

### Slice 14 - S14: Record and reproduce effects

Visible outcome:

```text
$ sentinel effects RUN_ID
file_write ... observed+verified
```

Build:

- `EffectReceipt` linked to a boundary call;
- filesystem write/delete, subprocess, and controlled HTTP effect adapters;
- before/after digests, observed status, idempotency/reconciliation metadata;
- explicit strategies: reapply, sandbox re-execute, or unsupported.

Tests:

- a recorded return value cannot falsely imply the effect happened;
- duplicate application is detected or safely idempotent;
- unknown effect status blocks exact-completion claims.

### Slice 15 - S15: Replay from a verified checkpoint

Visible outcome:

```text
$ sentinel replay RUN_ID --from 42
RESTORE VERIFIED
VERIFIED_REPLAY completed
```

Build:

- nearest valid checkpoint selection;
- environment/adapter/policy/recording compatibility check;
- restore, cursor initialization, network-denied replay, and persisted `ReplayResult`.

Tests:

- replay from multiple checkpoints;
- wrong environment or missing evidence fails closed;
- final supported state matches the original.

Stage 3 gate: restore and replay the scripted incident from a checkpoint with no undeclared live dependency.

## Stage 4 - Explain the incident

Goal: distinguish divergence, locate reproducibility boundaries, and show evidence-backed provenance and blast radius.

### Slice 16 - S16: Structural and effect divergence

Visible outcome:

```text
$ sentinel compare ORIGINAL REPLAY
structural_divergence_at=...
effect_divergence=...
```

Build:

- structural, effect/state, and outcome signatures;
- first divergence with preceding matched evidence;
- expected policy-induced versus unexpected divergence classes.

Tests: inject an action mismatch and an uncaptured file effect and prove they produce different reports.

### Slice 17 - S17: Honest incident bisection

Visible outcome:

```text
$ sentinel bisect RUN_ID --predicate predicate.yaml
earliest_reproducing_checkpoint=... method=binary
```

Build:

- predicate interface, monotonicity declaration and validation probes;
- binary search only when valid;
- interval/linear fallback otherwise;
- separate labels for earliest divergence, earliest reproducing checkpoint, and causal hypothesis.

Tests:

- monotone fixture uses logarithmic restores;
- non-monotone fixture refuses misleading binary search;
- Hypothesis: generated monotone boolean sequences return the first true position.

### Slice 18 - S18: Extract safe provenance carriers

Visible outcome:

```text
$ sentinel carriers RUN_ID --step 143
path:... url:... secret_fingerprint:...
```

Build:

- typed path, URL, object ID, hash, error ID, artifact, and configured-secret extractors;
- document-frequency/minimum-support filtering;
- HMAC fingerprints and redacted displays for sensitive carriers.

Tests: raw secrets never enter ordinary output; small-run thresholds still preserve unique evidence.

### Slice 19 - S19: Build provenance and blast radius

Visible outcome:

```text
$ sentinel provenance RUN_ID --step 143
ancestors=3 descendants=11
```

Build:

- typed dataflow, filesystem, effect, trace-parent, control, and chronological edges;
- explainable source/confidence metadata;
- evidence-bearing reachability and blast summaries.

Tests:

- chronological edges cannot change blast radius;
- known dependency fixtures are recovered;
- false-overlap fixtures remain disconnected.

### Slice 20 - S20: Interactive forensic workspace

Visible outcome: selecting an incident highlights evidence-bearing ancestors, downstream blast radius, affected files, network requests, tools, and agents.

Build:

- capped React Flow neighborhood;
- edge filters and evidence panel;
- non-color accessibility indicators;
- provenance precision, recall, F1, root localization, and overreach report.

Tests: Playwright selects an event, filters edge types, and verifies blast counts against ground truth.

Stage 4 gate: the user can explain why one incident occurred, what may be affected, and which graph edges are evidence versus chronology.

## Stage 5 - Prevent the incident with the smallest tested policy

Goal: turn forensics into bounded, measurable policy engineering.

### Slice 21 - S21: Ask OPA for an action decision

Visible outcome:

```text
$ sentinel policy test deny-egress.yaml action.json
allow=false rule=network_external_deny
```

Build:

- normalized action input;
- allow/deny/confirm/escalate output;
- policy bundle identity and digest;
- OPA integration and journal-linked decision record.

Tests: fail closed on undefined, malformed, or unavailable decisions according to the declared policy contract.

### Slice 22 - S22: Sentinel policy DSL

Visible outcome:

```text
$ sentinel policy compile policy.yaml
compiled.rego
```

Build:

- finite typed atoms for tools, network, filesystem, secrets, processes, Git, and artifact export;
- normalization, conflict detection, Rego compilation, and readable round-trip form.

Tests:

- golden compiled fixtures;
- Hypothesis: normalized equivalent policies compile to the same digest;
- invalid combinations fail before OPA.

### Slice 23 - S23: Evaluate incident and benign traces

Visible outcome:

```text
$ sentinel policy evaluate INCIDENT --policy P1 --regression benign-v1
incident_blocked=true benign_blocks=6 mode=TRACE_POLICY_EVALUATION
```

Build:

- incident predicate and initial benign regression traces;
- trace-level evaluation with explicit adaptive-future limitation;
- disruption components for benign blocks and changed tool classes.

Tests: a blocking policy stops the recorded incident action, a permissive policy does not, benign interference is counted exactly, and neither result claims post-block adaptive behavior.

### Slice 24 - S24: Search and display the Pareto frontier

Visible outcome:

```text
$ sentinel policy-search INCIDENT
candidates=... nondominated=...
```

Build:

- bounded one-, two-, and three-atom generation;
- canonical deduplication, safe pruning, evaluation budgets, and partial-result persistence;
- nondominance calculation and transparent optional weights;
- candidate table and Recharts frontier.

Tests:

- no result is untested;
- duplicates run once;
- Hypothesis: every reported frontier member is not dominated by another result.

### Slice 25 - S25: Deterministic alternate futures

Visible outcome: one fork renders at least three policy-controlled futures with prevention and regression outcomes.

Build:

- ADR-0001 mode state machine;
- policy-feedback behavior in `ScriptedAgent`;
- deterministic child runs from a verified fork;
- parent, fork, transition, policy, environment, coverage, and divergence metadata.

Tests: rerunning a deterministic future yields identical supported evidence; invalid mode transitions fail.

Stage 5 gate: Sentinel finds and explains nondominated tested policies and produces reproducible supported futures.

## Stage 6 - Compare worlds and package the proof

Goal: reach a complete feature showcase, including a real agent adapter and portable evidence.

### Slice 26 - S26: Causal World Diff

Visible outcome: original and counterfactual worlds show aligned timeline, filesystem, Git, network, tool, agent, and outcome changes.

Build:

- machine-readable world-diff schema;
- distinguish directly blocked actions from downstream actions absent after divergence;
- UI alignment and avoided-effects summary.

Tests: known branch fixtures produce exact categorized differences.

### Slice 27 - S27: Export, verify, import, and replay a capsule

Visible outcome:

```text
$ sentinel capsule RUN_ID -o incident.sentinel
$ sentinel verify incident.sentinel
$ sentinel import incident.sentinel
$ sentinel replay-imported ...
```

Build:

- deterministic versioned archive manifest;
- journal, recordings, snapshots, policies, graphs, replays, coverage, and reports;
- offline digest/chain verification, clean import, conflict behavior, and supported replay;
- traversal and decompression limits.

Tests: export-import round trip; corruption and malicious paths fail before extraction.

### Slice 28 - S28: Sign and protect the evidence

Visible outcome:

```text
$ sentinel verify incident.sentinel
CHAIN VALID
SIGNATURE VALID
ANCHOR VALID
```

Build:

- development Ed25519 signer/verifier outside the agent sandbox;
- evidence-root anchor interface and local development anchor;
- sensitive-blob encryption interface, redaction, and audit events for export/verify;
- clear production key-management limitation.

Tests: rewritten chains, wrong keys, altered manifests, and raw-secret report leaks fail.

### Slice 29 - S29: Record one real coding agent

Visible outcome: record and inspect one real coding-agent run through the same journal, boundary, coverage, and timeline contracts.

Build:

- one real coding-agent adapter selected for accessible stable hooks;
- explicit coverage gaps and child process/external-state limitations;
- adapter contract tests using fixtures plus one live local run.

The real adapter demonstrates applicability; the deterministic environment pack remains the source of exact branch claims.

### Slice 30 - S30: One-command integrated alpha

Visible outcome:

```text
$ sentinel demo
```

It must execute:

- 3,000-step recording and compression;
- incident detection;
- provenance and blast radius;
- verified restore and strict replay;
- three or more policy candidates;
- deterministic alternate futures;
- Pareto result and world diff;
- signed capsule export, import, verification, and supported replay;
- preliminary metrics report.

Tests: one automated E2E test exercises the same path; the UI is driven by produced evidence, not a separate animation fixture.

Stage 6 gate: the integrated alpha passes on one supported environment pack. This is the earliest responsible point for a private or clearly labeled alpha demonstration; it is not the V1 release.

## Stage 7 - Break it with the full corpus

Goal: replace happy-path confidence with ground truth, adversarial inputs, privacy controls, and recovery behavior.

### Slice 31 - S31: Corpus pack A

Add executable scenarios for credential read, unauthorized egress, secret propagation, and harness tampering. Each includes ground-truth incidents, dependencies, replay coverage, policy candidates, and expected outcomes.

Visible outcome: `sentinel corpus run pack-a` publishes a machine-readable pass/fail report.

### Slice 32 - S32: Corpus pack B

Add log deletion, persistence write, unauthorized tool, and agent handoff scenarios with the same evidence contract.

Visible outcome: `sentinel corpus run pack-b` shows rule, replay, and provenance results.

### Slice 33 - S33: Corpus pack C and bounded database restore

Add environment contamination, uncaptured effect, unseeded randomness, and meaningful 3,000-step benign scenarios.

Build a bounded SQLite snapshot adapter at a declared transaction boundary and explicitly reject arbitrary or remote database rollback.

Visible outcome: `sentinel corpus run all` executes all twelve scenarios.

### Slice 34 - S34: Adversarial restore and capsule laboratory

Build fuzz/property harnesses for paths, symlinks, hardlinks, duplicate normalized entries, malformed manifests, decompression limits, corrupt blobs, and signatures.

Visible outcome: `make security-test` reports rejected attack classes and any residual unsupported cases.

### Slice 35 - S35: Authorization, privacy, and crash recovery

Build:

- local roles for raw evidence, export, replay, and policy editing;
- sensitive access/export audit events;
- crash recovery for journal append and ingestion;
- retries only for idempotent operations;
- health/readiness endpoints.

Visible outcome: a Playwright/API test proves an unauthorized user cannot view/export raw evidence and a killed ingest resumes safely.

Stage 7 gate: all twelve scenarios pass declared expectations, malicious inputs fail safely, and no critical/high defect remains on the supported path.

## Stage 8 - Reach the feature-complete beta

Goal: integrate every V1 feature, establish baseline measurements, and expose remaining failures before the mandatory hardening phase.

### Slice 36 - S36: Benchmark runner and storage retention

Build a reproducible benchmark command plus reachability-based retention/garbage-collection dry run.

Measure recording overhead, journal verification, restore time, replay throughput, policy search, logical/physical bytes, and deduplication.

Visible outcome: `sentinel benchmark` generates raw JSON and a human-readable report with environment metadata.

### Slice 37 - S37: Scale to 50,000 events

Profile and optimize ingestion, timeline queries, graph construction/neighborhood queries, API pagination, and virtualized UI at 3k, 10k, and 50k events.

Visible outcome: the benchmark report and UI show measured budgets; no manually transcribed results.

### Slice 38 - S38: Clean-room installer and recovery rehearsal

Build or fix bootstrap, Compose, migrations, health checks, demo data creation, capsule import, and recovery commands until a clean environment can install and run the system.

Visible outcome: a clean-room script installs Sentinel, runs the demo, verifies a capsule, and regenerates metrics.

Tests: execute the script in a fresh checkout/container with empty caches and databases; deliberately omit one prerequisite and verify the failure identifies the missing requirement.

### Slice 39 - S39: Public product path and proof video

Build the homepage and working demo entry points around the actual application. Add Playwright coverage for the 75-second path and produce the continuous video from executable behavior.

Visible outcome: homepage -> incident -> provenance -> rewind -> futures -> policy -> world diff -> evidence verification works without dead screens.

### Slice 40 - S40: Automated beta audit

Build the first `sentinel release-check` to run the sixteen charter acceptance clauses, required tests, corpus, capsule round trip, conformance checks, secret scan, clean-room evidence, and metric-presence checks. At this stage it is expected to expose named hardening failures rather than certify the final release.

Visible outcome:

```text
$ sentinel release-check --stage beta
SENTINEL REPLAY BETA AUDIT: PASS|FAIL WITH NAMED GATES
```

Generate the conformance ladder, threat-model baseline, architecture diagrams, limitations, and evidence-gap report from actual results.

Stage 8 gate: every V1 feature exists end to end, the beta audit names every unsupported or failing clause, and no missing requirement is silently moved to V2.

## Stage 9 - Make restore and replay defensible

Goal: revisit the highest-risk systems claims with deeper conformance tests rather than trusting the first working path.

### Slice 41 - S41: Snapshot adapter conformance matrix

Build a shared conformance suite for the overlayfs and full-directory snapshot adapters covering regular files, nested trees, permissions, timestamps in the declared contract, symlinks, hardlinks, deletions, and whiteouts.

Visible outcome: `sentinel snapshot conformance` prints a per-adapter capability matrix and refuses to label an untested property exact.

Tests: fixtures run through both adapters; Hypothesis generates mutation sequences; one student-added filesystem case must change the matrix or expose a failure.

### Slice 42 - S42: Race-resistant hostile restore

Harden descriptor-relative restore, safe path resolution, staging, atomic publication, size/count limits, rollback on failure, and post-restore verification.

Visible outcome: `sentinel restore --verify --explain` restores a valid checkpoint and produces a precise rejection report for a hostile one.

Tests: traversal, symlink swap, archive bomb, duplicate path, corrupt blob, partial write, and interrupted restore cases; inspect the unchanged target after every rejected restore.

### Slice 43 - S43: Effect reconciliation conformance

Expand effect receipts and declared adapters for filesystem writes, subprocess execution, and the bounded SQLite path. Separate recorded return values from materialized effects and unsupported remote state.

Visible outcome: `sentinel effects reconcile REPLAY_ID` reports reproduced, restored, simulated, skipped, and unsupported effects.

Tests: a matching return value with a missing side effect must fail reconciliation; repeated reconciliation must be idempotent where declared.

### Slice 44 - S44: Replay matching and coverage stress

Stress stable call identity, occurrence sequence, canonical request digests, clock/RNG interception, repeated identical calls, and missing recordings. Generate a versioned coverage report from execution evidence.

Visible outcome: `sentinel replay RUN_ID --strict --coverage` either completes without a live dependency or stops at an exact `ReplayMiss` with diagnostic context.

Tests: reordered calls, duplicate digests, altered arguments, absent recordings, undeclared boundary access, and accidental network fallback all fail closed.

### Slice 45 - S45: Divergence and bisection proof lab

Validate structural signatures, effect/state comparison, incident predicates, monotonicity checks, cached restores, and linear fallback when binary search is invalid.

Visible outcome: `sentinel bisect ... --explain` shows why the selected algorithm is valid and compares restores against linear inspection.

Tests: known earliest-divergence fixtures, non-monotone predicates, flaky predicates, and effect-only divergence. Publish the first replay/restoration confidence report.

Stage 9 gate: restore and replay claims pass the adapter conformance suites, remain fail-closed under stress, and expose unsupported state explicitly.

## Stage 10 - Calibrate forensic and counterfactual claims

Goal: turn working graphs and policy branches into measured, reproducible evidence rather than persuasive pictures.

### Slice 46 - S46: Provenance ground-truth evaluation

Run carrier extraction and typed-edge construction against the full injected-dependency corpus. Add per-edge explanations, source attribution, confidence rationale, and keyed fingerprints for sensitive carriers.

Visible outcome: `sentinel provenance evaluate corpus/` publishes precision, recall, F1, false-positive, and false-negative examples.

Tests: common-token suppression, secret redaction, cross-event identifiers, OTel parentage, and chronology-only traps; the student tunes one threshold from evidence.

### Slice 47 - S47: Blast-radius calibration and uncertainty

Measure descendant reachability by permitted edge type, exclude chronological fallback, cap interactive neighborhoods without changing totals, and explain uncertainty or missing evidence.

Visible outcome: the CLI/API/UI agree on ancestors, contaminated descendants, files, network calls, agents, and overreach for the same incident.

Tests: disconnected nodes, cycles rejected or normalized by contract, low-confidence edges, pagination, and ground-truth blast sets.

### Slice 48 - S48: Policy enforcement conformance

Harden the OPA boundary and Sentinel DSL compilation across tool, network, filesystem, secret, process, Git, and artifact atoms. Ensure decision logs connect policy inputs, versions, results, and enforcement actions.

Visible outcome: `sentinel policy conformance` shows every supported atom being allowed, denied, or confirmed through real enforcement hooks.

Tests: malformed input, compiler golden files, OPA timeout/unavailability, default decision behavior, version mismatch, and decision/enforcement disagreement.

### Slice 49 - S49: Reproducible bounded search

Harden candidate enumeration, pruning, persisted partial results, resume behavior, deterministic ordering, cost vectors, and Pareto nondominance across incident plus benign trajectories.

Visible outcome: two clean runs of `sentinel policy-search` produce the same tested candidate set and frontier; an interrupted run resumes without inventing results.

Tests: search never returns an untested policy, dominated policies stay off the frontier, limits are honored, and cost changes produce explainable frontier changes.

### Slice 50 - S50: Alternate-future and world-diff conformance

Run repeated branches through all four replay modes, preserve the exact divergence point, and compare structural, effect, filesystem, network, agent, and outcome differences.

Visible outcome: Replay Lab shows at least three evidence-backed alternatives with mode labels and a Causal World Diff whose counts trace to underlying events.

Tests: deterministic branches repeat identically; exploratory branches cannot acquire verified labels; absent actions and preserved artifacts are accounted for exactly.

Stage 10 gate: provenance, blast radius, policy search, alternate futures, and world diff are corpus-measured, reproducible, and correctly qualified.

## Stage 11 - Secure and recover the evidence path

Goal: make the supported local deployment trustworthy under unauthorized access, sensitive data, corrupted inputs, and interrupted operations.

### Slice 51 - S51: Authorization boundaries

Separate permissions for metadata, raw evidence, replay, policy editing, capsule export, and administration. Enforce the same decisions in API, CLI-mediated operations, and UI navigation.

Visible outcome: an authorization matrix is executable, and forbidden users cannot retrieve raw evidence by changing URLs or object identifiers.

Tests: role matrix, cross-run object access, export/replay escalation, stale sessions, and default-deny behavior; Playwright and API tests use the same identities.

### Slice 52 - S52: Privacy, redaction, retention, and audit

Apply structured redaction at ingestion and presentation, keyed fingerprints for correlation, configurable retention/deletion, reachability-aware blob cleanup, and append-only audit events for sensitive access/export.

Visible outcome: `sentinel privacy audit RUN_ID` finds no configured secret fixture in UI/API/capsule summaries and explains retained/deleted evidence.

Tests: nested secrets, encoded values within the declared detector boundary, shared blobs, deletion holds, audit-chain verification, and redaction consistency.

### Slice 53 - S53: Evidence keys and trust-boundary failure

Harden signed/externally anchored roots, capsule signatures, encryption-at-rest interfaces, key identifiers, rotation metadata, and explicit development-versus-production key limitations.

Visible outcome: `sentinel verify --trust-policy ...` distinguishes integrity, signer identity, anchor freshness, decryption availability, and an untrusted-but-intact artifact.

Tests: wrong key, revoked/unknown signer, stale anchor, manifest substitution, re-signed rewritten history, and missing decryption material.

### Slice 54 - S54: Crash recovery and idempotency

Add durable operation states, resumable ingestion, journal tail repair rules, idempotency keys, retry classification, and recovery commands for interrupted record, replay, export, and import operations.

Visible outcome: a fault-injection run kills each operation at controlled points and `sentinel recover` reaches one consistent documented state.

Tests: duplicate delivery, partial database commit, partial blob write, process kill, retry exhaustion, and non-idempotent effect refusal.

### Slice 55 - S55: Hostile import and dependency boundary

Complete streamed capsule/import verification with archive limits, duplicate-name rejection, schema/version handling, temporary isolation, and no trust in embedded paths or commands. Add locked dependency and secret-scan checks to the supported release path.

Visible outcome: `sentinel security-check` runs the hostile corpus and produces a machine-readable pass/fail report with residual risks.

Tests: zip-slip, decompression bomb, oversized manifest, unsupported version, signature confusion, malicious README content, corrupted indexes, and dependency/secret scan failures.

Stage 11 gate: no critical/high defect remains in the supported evidence path, and authorization, privacy, integrity, import, and recovery behavior have executable proof.

## Stage 12 - Prove, present, and release V1

Goal: reproduce the complete system from a clean environment and publish only claims backed by generated evidence.

### Slice 56 - S56: Reproducible benchmark and storage lifecycle

Run recording, verification, restore, replay, provenance, policy-search, capsule, and storage/deduplication benchmarks with captured hardware/software metadata and repeated trials. Exercise retention and garbage collection in dry-run and applied modes.

Visible outcome: `sentinel benchmark --release` creates raw JSON, summarized tables, variance, environment metadata, and linked artifacts without manual transcription.

Tests: schema validation, repeatability bounds, shared-blob reachability, interrupted GC recovery, and detection of missing or suspicious benchmark data.

### Slice 57 - S57: 50,000-event release budgets

Profile and optimize ingestion, indexed timeline queries, graph neighborhoods, API pagination, SSE backpressure, and virtualized UI at 3k, 10k, and 50k events. Record justified budget changes through an ADR rather than hiding misses.

Visible outcome: the performance dashboard and raw report agree, and each release budget is PASS or an explicitly accepted evidence-backed exception.

Tests: cold/warm paths, pagination stability, memory bounds, slow consumer behavior, and Playwright interaction on the 50k fixture.

### Slice 58 - S58: Clean-room install and disaster rehearsal

From an empty checkout and empty data volumes, install pinned dependencies, start Compose, migrate, generate demo data, run the full demo, import/verify/replay a capsule, back up, destroy the disposable environment, and restore it.

Visible outcome: one automated clean-room transcript proves installation and recovery without developer-machine state.

Tests: missing prerequisite, migration failure, unavailable service, empty cache, backup corruption, and documented rollback path.

### Slice 59 - S59: Public proof path and 75-second video

Finish the homepage and continuous real-product route: 3,184 actions to phases, provenance, blast radius, rewind, alternate futures, minimal policy, world diff, and verified capsule. Generate architecture, threat-model, conformance, limitations, and recruiter-facing material from verified facts.

Visible outcome: Playwright completes the public path without dead screens and the 75-second video uses the same executable evidence, not a separate mock.

Tests: link/accessibility smoke tests, demo reset, deterministic fixture identity, claim-to-evidence links, and a secret scan over public artifacts.

### Slice 60 - S60: Final automated release gate

Finalize `sentinel release-check` so it verifies all sixteen charter clauses, all forty-three traceability rows, required unit/property/contract/integration/E2E/security/performance checks, the twelve-scenario corpus, clean-room transcript, capsule round trip, replay-mode labels, metrics, and public-proof artifacts.

Visible outcome:

```text
$ sentinel release-check --stage release
SENTINEL REPLAY COMPLETE FLAGSHIP V1: PASS
```

If any required clause fails, the command must return nonzero and name the evidence gap. Only a passing generated report permits the V1 tag and measured resume bullets.

Stage 12 gate: the final release verifier passes, every traceability row has direct evidence, and the Complete Flagship V1 release candidate is tagged.

## 10. Stage gates

| Stage | Executable gate |
| --- | --- |
| 1 | record, verify, inspect, and replay a small agent run |
| 2 | persist, classify, stream, and visualize a 3,000-step run |
| 3 | restore verified workspace/Git state and replay from a checkpoint |
| 4 | show divergence, provenance, root evidence, and blast radius |
| 5 | evaluate policies, produce a Pareto frontier, and fork deterministic futures |
| 6 | run the complete showcase and portable signed capsule path |
| 7 | pass the twelve-scenario and adversarial security corpus |
| 8 | reach feature-complete beta and generate the named evidence-gap audit |
| 9 | pass restore, effect, replay, divergence, and bisection conformance |
| 10 | calibrate provenance, blast radius, policy search, futures, and world diff |
| 11 | pass authorization, privacy, integrity, hostile-import, and recovery gates |
| 12 | pass reproducible scale, clean-room, public-proof, and final release gates |

## 11. Required measurements

- strict replay fidelity;
- restoration fidelity;
- unexpected structural divergence rate;
- effect divergence detection accuracy;
- provenance precision, recall, F1, root localization, and blast overreach;
- validated bisection restores versus linear inspection;
- recording overhead;
- logical versus physical snapshot bytes and deduplication;
- policy prevention, benign blocks, candidate count, and search time;
- ingestion, API, graph, and UI latency at 3k, 10k, and 50k events.

Stage 6 publishes preliminary alpha measurements. Stage 8 publishes the feature-complete beta baseline and named gaps. Stage 12 publishes reproducible release measurements.

## 12. Performance budgets

Initial engineering targets, not marketing claims:

- ScriptedAgent recording overhead at 3,000 steps: <= 20 percent excluding model latency.
- Timeline first page at 3,000 events: <= 300 ms on the documented machine.
- Timeline interactive after data arrival: <= 1 second at 3,000 events.
- Selected graph neighborhood: <= 300 ms at 50,000 events with indexes.
- Journal verification: >= 50,000 small records/second.
- Policy search default: <= 1,000 candidates or 10 minutes, persisting a partial frontier.
- Capsule verification streams with bounded memory and configured archive limits.

Measured evidence may revise a budget through an ADR. Results may not be altered manually.

## 13. Scope and change control

No frozen capability is removed by this schedule. The following remain explicit non-goals: universal replay, arbitrary concurrency replay, general remote rollback, CRIU continuation, browser/VM replay, universal causal inference, custom policy VM, custom telemetry, custom containers, Kubernetes, and a microservice fleet.

Every item in the charter's Complete Flagship V1 contract is required for the Stage 12 release gate. An original requirement cannot be relabeled as V2, optional polish, or post-release work merely to make the schedule appear successful.

A change request must state:

- requested behavior;
- evidence and reason;
- affected guarantee;
- schedule and compatibility impact;
- whether the charter or an ADR changes.

If the Stage 12 release gate does not pass, named remediation slices are added and the project continues for as long as required. A calendar date cannot convert unsupported behavior into a weaker unlabeled claim or authorize fake evidence.

## 14. Progress reporting

At the end of every slice, update `docs/STATUS.md` with:

- task state;
- visible behavior delivered;
- failing and passing test commands;
- property-test evidence where applicable;
- inspected artifact/output;
- student variation and teach-back;
- PR and merge commit;
- next single slice;
- Stage 6 alpha, Stage 8 beta, and Stage 12 release-gate confidence, with a forecast range rather than a promised date.

## 15. Immediate next action

The current and only active slice is `S01: Project pulse`. It ends only when `sentinel version` works locally and in CI, the first code PR is merged, and the user can explain every file introduced.
