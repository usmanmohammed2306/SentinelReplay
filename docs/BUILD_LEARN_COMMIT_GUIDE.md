# Sentinel Replay — build it, learn it, publish it

This is the companion field guide to the [binding execution plan](EXECUTION_PLAN.md), not a replacement for it. The plan defines what V1 must do and how it is accepted. This guide tells you what to *build, break, explain, and commit* on each working day.

The ambition is real: the full V1 includes recording, verified restoration, incident forensics, policy search, alternate futures, a UI, twelve scenarios, and release evidence. A single engineer can pursue it, but **60 slices are not 60 guaranteed calendar days**. A difficult slice may take several days. Do not call a slice done because the date changed. The day numbers below are the ideal sequence of focused workdays; if a gate fails, keep the same slice active, make a truthful progress commit, and resume it the next day.

## Your ownership rule

I can help write code, tests, explanations, and reviews. You own the understanding and the GitHub activity. Before merging any slice, you should be able to say:

1. What real problem does this change solve?
2. What invariant does its test protect?
3. What input makes it fail, and what does it *not* guarantee?
4. What small change did you personally make or direct after inspecting the output?

If you cannot answer those questions, the code is a study artifact, not an accepted slice. Never use a generated green square as a substitute for comprehension.

## The daily loop

Read `docs/STATUS.md` and yesterday's lab note. Run the smallest previous demonstration. Write down a prediction about today's failure. Make or inspect a failing test. Implement the smallest visible behavior, run focused tests and `make check`, inspect the artifact, and change one edge case yourself. Then write a short lab note using `docs/learning/LAB_NOTE_TEMPLATE.md`. Commit only a coherent change, push your branch, self-review the diff, and merge after CI and your teach-back pass. This is the [learning pyramid](LEARNING_PYRAMID.md) in daily form.

Current local starter code already includes working examples of S01–S05 concepts, plus batch journal, metadata-only timeline, bounded declared-provenance and synthetic forensic previews, regular-file workspace, unsigned-by-default capsule, development Ed25519 root and detached capsule signers, a PostgreSQL/API signed-ingest preview, an OPA-checked finite policy preview, a metadata-only real Codex event observer, one bounded Codex/MCP/OPA tool gateway, and an optional offline AWS experiment, but **none is accepted**: the first GitHub push/CI, fuller slice gates, and your teach-back remain. On Day 1 you may publish the current tested tree as an honest *research preview* after reviewing it. Days 2–5 harden and understand the foundation; later days turn previews into general, accepted capabilities. Do not split prebuilt files into fake historical commits; publish real improvements made on each day.

Use a branch such as `learn/s03-journal-chain`. Suggested commit messages are examples, not exact scripts. Your Git identity, remote, push, PR, and merge are yours to operate. `docs/GITHUB_WORKFLOW.md` has the detailed rules. The repository must never receive a real credential, unredacted incident payload, `.env`, or an unreviewed generated artifact.

## Days 1–5: earn the evidence foundation

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 1 · S01 | Review the package, CLI, CI, `demo-mini`, timeline, and bounded investigation; run `sentinel version` and `make check`. Publish the tested research preview, then check CI on GitHub. | Explain the Typer command group, lockfile, strict boundary-match label, and why CI must run the same checks. Try an unknown command. | `chore: publish tested Sentinel research preview` |
| 2 · S02 | Add golden canonical hash fixtures and schema round-trips; inspect exact bytes behind one digest. | Change Unicode normalization or one unsupported value; explain why equal-looking data can hash differently. | `test(contracts): lock canonical event fingerprints` |
| 3 · S03 | Harden the current exclusive streaming/batch writers with mutation, reordering, deletion, crash-tail, and concurrent-writer tests; inspect the first corrupt record and rerun both local scale probes. | Explain why a hash chain detects edits but is not immutable without an external anchor, and compare batch throughput with durable per-call recording. | `feat(journal): harden exclusive append and corruption detection` |
| 4 · S04 | Add typed replay-miss reasons, repeated-call occurrence, and clock/RNG adapter tests. Inspect recording JSONL and replay a repeated call. | Delete or reorder one call; prove no live fallback occurs. Explain request digest versus call identity. | `feat(replay): make boundary matching fail closed` |
| 5 · S05 | Add CLI `record`, `inspect`, and `replay` for the mini-agent; compare benign and incident signatures after two replays. | Alter a request and see a replay miss. Explain why matched *boundaries* are not yet verified state restoration. | `feat(demo): inspect and replay the first agent run` |

Stage 1 is accepted only after you can trace an action from agent decision → boundary request → journal row → verifier → replayed response. The current `demo-mini` uses **synthetic responses and effects**. It does not perform external HTTP or restore process/filesystem state, so it says `BOUNDARY_REPLAY_MATCHED`, not `VERIFIED_REPLAY`.

## Days 6–10: make a run persistent and readable

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 6 · S06 | Harden the local content-addressed store behind the `BlobStore` contract; inspect deduplicated writes, verified reads, and symlink rejection. | Corrupt or substitute a blob and require verification failure; explain digest identity, atomic publication, and why the signed-capsule API raises the 8 MiB starter limit only for its bounded archive. | `feat(storage): verify local content-addressed evidence` |
| 7 · S07 | Harden the PostgreSQL signed-ingest preview into normalized run metadata with migration drift, transaction, and authorization tests. | Retry ingestion, race two conflicting imports, and explain why a durable blob can remain orphaned after a rejected SQL insert. Learn the boundary between two storage systems. | `feat(ingest): persist normalized runs in postgres` |
| 8 · S08 | Extend the current metadata-only timeline rules into versioned incident rules and phase compression over normalized runs; inspect a 3k-step timeline. | Add a false-positive counterexample. Explain what a rule miss means and why a trace hit is not causal proof. | `feat(incidents): classify and compress run phases` |
| 9 · S09 | Merge OTLP spans through a versioned adapter while keeping journal evidence authoritative. | Feed missing/duplicate parents; prove trace parentage is not causal proof. | `feat(telemetry): enrich steps with validated otel spans` |
| 10 · S10 | Stream and paginate a live compressed timeline in API and first UI page. | Load a long benign run; test stable ordering and backpressure. | `feat(timeline): stream and virtualize run phases` |

## Days 11–15: make rewind a defensible word

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 11 · S11 | Harden the current bounded regular-file capture into a declared checkpoint with manifest and byte hashes; measure a concurrent-mutation case. | Mutate a covered file and show the checkpoint detects it; name empty directories, metadata, Git, database, and process state as uncovered. | `feat(snapshot): capture declared workspace state` |
| 12 · S12 | Harden the current preflighted restore into a race-resistant isolated root; verify bytes after restore. | Try `../`, symlink swaps, and destination-parent races; require a hard failure. | `feat(restore): verify isolated workspace restoration` |
| 13 · S13 | Capture and restore declared Git worktree/index/HEAD state. | Test staged and unstaged files, untracked files, and a missing object. | `feat(git-state): restore declared repository state` |
| 14 · S14 | Record effect decisions and receipts; reconcile observed effects. | Simulate an effect that was recorded but not applied; identify uncertainty. | `feat(effects): reconcile effect receipts` |
| 15 · S15 | Restore a checkpoint, then replay from it under the coverage contract. | Remove one recording and demand `ReplayMiss`; check no real network is used. | `feat(replay): run from verified checkpoint` |

## Days 16–20: explain what happened, not merely when

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 16 · S16 | Compare structural and effect signatures; show first divergence. | Change only an effect receipt; distinguish structure from effect. | `feat(divergence): classify replay differences` |
| 17 · S17 | Add predicate-validated bisection with measured restores. | Use a non-monotone predicate; refuse a false binary-search claim. | `feat(bisect): localize validated incident boundaries` |
| 18 · S18 | Harden the declared-carrier preview with a production keyed-fingerprint contract and coverage report. | Place a secret in a carrier; prove public output does not leak it and unsupported carrier claims are rejected. | `feat(provenance): extract safe dependency carriers` |
| 19 · S19 | Promote the bounded preview into typed, source-linked evidence edges and blast-radius traversal. | Add a merely chronological edge; prove it cannot contaminate downstream reachability or overstate causality. | `feat(graph): show evidence-backed blast radius` |
| 20 · S20 | Build an investigation workspace linking phases, events, evidence, and graph. | Follow one edge from UI to source evidence; test an empty graph. | `feat(ui): connect incident timeline and provenance` |

## Days 21–25: test the smallest intervention

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 21 · S21 | Harden the existing single-tool Codex/MCP/OPA gateway into a covered tool family; preserve decision/effect evidence and add confirm semantics. | Shut OPA down and prove no effect; then attempt a native-shell bypass and mark it uncovered rather than claiming prevention. | `feat(policy): enforce covered agent tool decisions` |
| 22 · S22 | Extend the existing finite, versioned Rego compiler to the remaining charter atoms and test each against real OPA. | Reject an unsupported atom instead of silently ignoring it. | `feat(policy): complete typed policy atoms` |
| 23 · S23 | Evaluate incident plus benign recorded traces; publish confusion counts. | Add a benign request resembling the incident; observe disruption. | `feat(policy): measure prevention and benign interference` |
| 24 · S24 | Enumerate bounded candidates and show the nondominated Pareto frontier. | Change selection weights; show frontier stays stable while recommendation may change. | `feat(search): expose measured policy frontier` |
| 25 · S25 | Fork a versioned deterministic environment after a policy block. | Change a seed or stub; prove its identity is visible and replay mode changes explicitly. | `feat(futures): branch deterministic alternate outcomes` |

## Days 26–30: connect the whole story

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 26 · S26 | Show a causal world diff across structure, effects, and outcome. | Compare equal outcomes with different effects; do not collapse them. | `feat(world-diff): compare supported branch effects` |
| 27 · S27 | Extend the current unsigned mini-agent capsule into a typed, complete incident capsule with snapshots, policies, graphs, replays, coverage, and reports; demonstrate a clean import and supported replay. | Corrupt one blob and add an unlisted path; require import rejection. Explain why SHA-256 alone is not a signature. | `feat(capsule): round-trip complete incident evidence` |
| 28 · S28 | Harden the existing development root/capsule signers behind an isolated controller, require authenticated import, publish to an independent local anchor, encrypt sensitive payloads, and test key failure. | Rotate or remove a key; distinguish unreadable payload, invalid signature, and stale-but-valid signed root. Prove the recorded agent cannot rewrite its anchor. | `feat(evidence): isolate signer and authenticate capsule import` |
| 29 · S29 | Advance the existing Codex observer and single-tool gateway into a real agent run with declared adapter coverage, reconciled effect receipts, and explicit gaps. | Trigger an unsupported action; label its gap rather than claiming exact replay. | `feat(adapter): record covered coding-agent boundaries` |
| 30 · S30 | Make the integrated alpha demo one-command and generate its gate report. | Run from a clean directory; fail if any required artifact is absent. | `feat(demo): prove integrated alpha end to end` |

## Days 31–35: try to break it

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 31 · S31 | Implement corpus pack A with ground truth and replay coverage. | Add a near miss that must remain benign. | `test(corpus): add first incident scenarios` |
| 32 · S32 | Implement corpus pack B, including propagation and handoff paths. | Hide a dependency; verify the expected recall impact. | `test(corpus): add propagation and handoff scenarios` |
| 33 · S33 | Finish twelve scenarios and bounded database restore adapter. | Test an inconsistent DB snapshot and report unsupported recovery. | `test(corpus): complete twelve-scenario benchmark` |
| 34 · S34 | Run hostile restore/capsule tests: traversal, symlink, archive bomb, malformed schema. | Handcraft one malicious import; inspect the rejection reason. | `test(security): reject hostile restore and capsule inputs` |
| 35 · S35 | Add authorization, privacy, and crash-recovery checks. | Crash during a write and retry; prove no silent double effect. | `feat(security): enforce access and recovery boundaries` |

## Days 36–40: feature-complete beta evidence

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 36 · S36 | Build benchmark runner and retention lifecycle reports. | Vary run length; publish raw configuration and units. | `feat(bench): automate performance and retention reports` |
| 37 · S37 | Make timeline, graph, and journal usable at 50k events. | Profile the slowest query; improve it with a measured before/after. | `perf(scale): meet documented 50k-event budgets` |
| 38 · S38 | Reproduce the complete self-hosted installation with Compose, PostgreSQL, API/worker, telemetry, signer/anchor, and backups. | Remove a required dependency and ensure diagnostics name it; destroy disposable state and restore from backup. | `test(install): prove self-hosted clean-room recovery` |
| 39 · S39 | Connect public product route and record a proof video from actual output. | Check every public claim against a passing artifact. | `docs(showcase): publish executable product walkthrough` |
| 40 · S40 | Run automated beta audit; list every unmet release proof by name. | Delete one artifact and confirm the audit fails. | `feat(audit): generate feature-complete beta evidence gaps` |

## Days 41–45: attack replay claims

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 41 · S41 | Build snapshot-adapter conformance matrix and publish coverage. | Test a path the adapter does not cover; label it unsupported. | `test(snapshot): publish adapter conformance matrix` |
| 42 · S42 | Extend the existing descriptor-relative restore test to hostile destination-parent races and post-restore mutation; prove the whole declared boundary, not just nested-file containment. | Race a path replacement; require containment or an explicit unsupported result. | `fix(restore): prove path-swap containment` |
| 43 · S43 | Conformance-test effect receipts and reconciliation. | Inject missing, duplicate, and contradictory receipts. | `test(effects): enforce reconciliation contract` |
| 44 · S44 | Stress repeated identical calls, missing data, and coverage reports. | Mutate one middle boundary; verify earliest miss. | `test(replay): stress fail-closed matching` |
| 45 · S45 | Prove divergence and bisection on monotone and non-monotone cases. | Compare restore counts against linear inspection honestly. | `test(bisect): validate localization claims` |

## Days 46–50: calibrate the forensic claims

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 46 · S46 | Use the existing root-bound scoring protocol on the independently labeled twelve-scenario corpus; publish per-scenario TP/FP/FN and ambiguous cases. | Calculate precision/recall/F1 by hand for one tiny graph and prove chronology is excluded. | `test(provenance): score independently labeled evidence edges` |
| 47 · S47 | Quantify blast-radius overreach and uncertainty. | Add a low-confidence edge; inspect changed reachability. | `feat(blast): expose calibration and uncertainty` |
| 48 · S48 | Conformance-test DSL → Rego → enforcement with default-deny cases. | Try policy ambiguity and unavailable OPA. | `test(policy): verify enforcement semantics` |
| 49 · S49 | Re-run bounded search deterministically; save candidates and partial frontiers. | Interrupt search mid-run and resume without changing prior scores. | `test(search): reproduce bounded Pareto results` |
| 50 · S50 | Verify future mode transitions and world-diff evidence. | Force divergence and show the exact transition boundary. | `test(futures): enforce honest branch labels` |

## Days 51–55: defend the evidence path

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 51 · S51 | Test roles and authorization across API, UI, CLI, export. | Attempt cross-run access as another user. | `test(auth): close cross-run access paths` |
| 52 · S52 | Prove redaction, retention, deletion, and audit behavior. | Put a canary secret in all outputs and scan them. | `test(privacy): verify redaction and lifecycle` |
| 53 · S53 | Exercise signing/encryption trust-boundary failure, rotation, local anchor permission denial, and audit. | Compromise agent-write storage, not signer storage; report what survives and what freshness still cannot prove. | `test(keys): validate independent evidence boundaries` |
| 54 · S54 | Crash/retry every ingest, effect, and capsule transition. | Kill a process at one durability boundary; inspect recovery. | `test(recovery): make operations idempotent` |
| 55 · S55 | Audit hostile import and dependency boundary. | Use an oversized archive and malformed manifest; require bounded failure. | `test(import): contain untrusted capsule inputs` |

## Days 56–60: release only what was proven

| Day | Build and inspect | Learn and break it | Suggested commit |
| --- | --- | --- | --- |
| 56 · S56 | Reproduce benchmark and storage lifecycle from scripts. | Re-run on another machine and explain environment differences. | `test(bench): make performance evidence reproducible` |
| 57 · S57 | Run 50k-event release budgets and preserve raw outputs. | Measure p50/p95 and memory, not a single best run. | `perf(release): verify 50k-event budgets` |
| 58 · S58 | Perform a self-hosted clean-room install plus disaster rehearsal. | Remove one service/data set and restore from documented backups without bypassing the independent anchor. | `test(release): prove self-hosted disaster recovery` |
| 59 · S59 | Test homepage → investigation → capsule path and 75-second real demo. | Follow every claim to evidence; scan video/public assets for secrets. | `docs(proof): publish verified product story` |
| 60 · S60 | Run `sentinel release-check --stage release`; tag V1 only if all clauses pass. | Remove one required report; prove the gate returns nonzero and names the gap. | `release: gate Complete Flagship V1 on evidence` |

If a day needs another day, write `test(...)`, `fix(...)`, or `feat(...)` describing *actual* passing progress on the same branch. Do not write `complete Sxx` until the acceptance gate passes. At each stage gate, update `docs/STATUS.md` and your measured forecast; never change a threshold just to hit a calendar date.

## Reading path — only when the code needs it

The fastest way to learn here is not to finish a textbook first. Read the named section, implement a toy version, break it, then return to the official reference when a test fails.

| While building | Read | Practice before returning to Sentinel |
| --- | --- | --- |
| Days 1–5: Python, packaging, schemas, tests | [Python 3.12 tutorial](https://docs.python.org/3.12/tutorial/), [uv projects](https://docs.astral.sh/uv/guides/projects/), [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/), [Hypothesis quickstart](https://hypothesis.readthedocs.io/en/latest/quickstart.html), [GitHub Actions for Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python) | Write a ten-line JSON journal, mutate byte 1, and predict which hash check fails. Generate dictionaries in two insertion orders. |
| Days 6–10: persistence and telemetry | [PostgreSQL tutorial](https://www.postgresql.org/docs/current/tutorial.html), [SQLAlchemy 2 tutorial](https://docs.sqlalchemy.org/en/20/tutorial/), [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html), [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/), [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) | Store one run twice and design an idempotency key. Draw one span tree and one *different* evidence dependency graph. |
| Days 11–15: isolation and restore | [Docker storage driver overview](https://docs.docker.com/engine/storage/drivers/), [Python `pathlib`](https://docs.python.org/3.12/library/pathlib.html), [Git internals](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) | Snapshot a three-file directory, mutate it, restore into a throwaway root, and attack the restore with a symlink. |
| Days 16–20: graph reasoning and UI | [NetworkX tutorial](https://networkx.org/documentation/stable/tutorial.html), [Next.js App Router docs](https://nextjs.org/docs/app), [Playwright writing tests](https://playwright.dev/docs/writing-tests) | Draw a five-node graph with one chronological-only edge and verify that blast-radius reachability excludes it. |
| Days 21–30: policies, futures, capsules | [OPA Rego policy language](https://www.openpolicyagent.org/docs/policy-language), [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/), [Python `zipfile` security notes](https://docs.python.org/3.12/library/zipfile.html) | Compare two policies on one incident and three benign requests; hand-compute nondominated candidates. |
| Days 31–60: proof, operations, release | Revisit the official references above for the exact failing subsystem; read [Playwright best practices](https://playwright.dev/docs/best-practices) and [GitHub Actions security](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions) | Reproduce a reported metric from raw events on a clean checkout. Try to make the release gate falsely pass, then fix the missing check. |
| Optional AWS study after V1 | [ADR-0002](adr/0002-aws-evidence-profile.md), [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html), and [KMS key types](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-kms-key.html) | Only if you later choose a cloud track, compare the optional adapter against the proven local trust boundary. No AWS work is required for V1. |

Read official docs at the time of the slice; commands and version-specific behavior can change. Pin tools in the repository and record the tested environment. Do not copy a code snippet into the product until you can explain its failure boundary.

## Evidence that makes the project interview-worthy

The target is not to collect framework names. As of 2026-10-07, OpenAI's [Agent Infrastructure](https://openai.com/careers/software-engineer-agent-infrastructure-san-francisco/) role emphasizes execution environments, production interfaces, and performance; [Agent Security](https://openai.com/careers/security-engineer-agent-security-san-francisco/) emphasizes isolation, policy controls, telemetry, and threat models; [Frontier Evals and Environments](https://openai.com/careers/research-engineer-frontier-evals-and-environments-san-francisco/) emphasizes measurement reliability and variance. Google DeepMind describes research engineers as experimentalists who build and scale systems to test ideas in its [careers overview](https://deepmind.google/careers/). A personal repository cannot claim that operating scale, but it can show the underlying judgment.

At the release gate, be able to show these artifacts and answer the corresponding question without a script:

| Evidence to publish | Question you should be able to answer |
| --- | --- |
| One real coding-agent run with a declared coverage map and a fail-closed replay transcript | Where could an unrecorded effect still invalidate replay? |
| Twelve versioned scenarios, benign near misses, raw confusion counts, provenance precision/recall/F1, and repeated policy trials | What is the ground truth, and how sensitive is the result to the corpus? |
| Threat model, isolated agent/controller boundary, signed external root, hostile-input tests, and a recovery rehearsal | What can an attacker rewrite, and which failures remain detectable? |
| 3k/10k/50k raw benchmark reports with environment, repeated trials, p50/p95, memory, and a measured before/after optimization | Which bottleneck did you find, and why is the improvement credible? |
| A working API, professional investigation UI, clean-room install, and short continuous demo using the same evidence | Can a new engineer reproduce the story from a clean checkout? |

Keep one honest limitations page and one concise architecture diagram. In an interview, the strongest moment is often explaining a guarantee you deliberately *did not* make. After V1, practice a system-design interview using Sentinel's ingest, isolation, storage, and replay boundaries; practice an evaluation-design interview by defending the corpus and variance; and practice a security review by attacking the signer and archive path. No amount of generated code replaces that fluency.

## What you must actually understand

Keep this section beside the code. For each area, the proof of learning is a change you can make *without asking an assistant to explain every line first*.

### 1. Contracts and canonical evidence

A Python object is not evidence merely because it can be JSON-encoded. Insertion order, integer versus boolean, unsupported floats, Unicode, timestamps, and schema versions can all change interpretation. Be able to point to the exact bytes being hashed; explain the domain prefix, why SHA-256 gives change detection but not authenticity, and why the schema version belongs in persistent data. Practice: write two semantically equal maps in opposite key order and one almost-equal list in opposite item order; predict their digests before running the test.

### 2. Journaling and durability

The journal links each record to the previous digest. You should know what `flush`, `fsync`, and a writer lock each do, and what they do *not* do. A local attacker who can rewrite the entire file can also recompute its hashes; an external signer or anchor changes the trust story. Practice: mutate, delete, insert, reorder, and truncate records; identify the earliest verifier failure. Later, simulate a crash between write and durable completion and document recovery behavior.

### 3. Recording versus replay

Recording captures a nondeterministic boundary once. Replay must match sequence position, stable call identity, adapter kind, and canonical request digest before returning the stored response. A missing record must never call the live provider. Know why two identical HTTP requests can still be distinct calls. Practice: write a test whose live callback raises an exception, then prove replay never invokes it; remove the second of two repeated calls and inspect the miss.

### 4. State coverage and restoration

Boundary matches alone cannot restore a filesystem, Git index, database, process, or remote service. Define the covered root and consistency point first. Capture a manifest, restore only inside isolation, and verify post-restore bytes and metadata before saying `VERIFIED_REPLAY`. Know the difference between a copied directory and a snapshot adapter's guarantee. Practice: restore a staged Git change and a deleted file; then attack with `../` and a symlink swap. Write down unsupported state rather than hiding it.

### 5. Effects and divergence

An agent saying “write file” is an action request; a file actually changed is an effect. Receipts connect the decision to observed effect. Structural divergence means the sequence/request shape changed; effect divergence means the world changed despite an apparently similar sequence. Practice: keep the requests identical while changing the effect receipt and explain why the comparison must still flag a difference.

### 6. Incident compression and provenance

Classification is a declared set of rules, not mind-reading. Compression groups events into phases without discarding the source trail. Provenance edges must cite a typed carrier: dataflow, filesystem, effect, trace parent, control, or merely chronological. Only declared evidence-bearing edges count toward contamination reachability. Practice: make a graph with a chronological shortcut; show that the blast radius does not traverse it. Hand-score a tiny ground-truth graph: precision = true positive edges / predicted edges; recall = true positive edges / true edges; F1 = `2 × precision × recall / (precision + recall)` when the denominator is nonzero.

### 7. Policies and least disruption

Separate the recorded action, the policy's decision about it, and what an agent *might* do next. Testing a policy against a trace answers the first two; it does not predict adaptation. A policy candidate is “least disruptive” only relative to a declared benign corpus and explicit cost vector. A Pareto frontier contains candidates for which no tested candidate is at least as good in every dimension and strictly better in one. Practice: evaluate three policies by hand on one malicious and three benign actions, then compare your frontier with the code. A single recommended policy needs disclosed weights.

### 8. Alternate futures and world diff

After a block changes the action sequence, the old recording no longer contains the exact future. You must stop, move into a declared deterministic environment, or start an exploratory branch with uncertainty. Keep model/stub version, seed, scheduler, environment digest, and policy digest attached to the branch. Practice: force one policy-induced divergence and point to the exact transition event. Compare both *effects* and outcome, not only an end-state label.

### 9. Capsules, trust, and privacy

A portable investigation needs bounded manifest parsing, verified blob digests, a trusted signature, explicit compatibility rules, and safe import paths. Encryption protects confidentiality; signatures/anchors protect authenticity; redaction protects what a viewer sees. They solve different problems. Practice: corrupt one blob, remove one key, substitute a signer, and attempt an oversized archive. For each, say whether verification, decryption, import, or authorization should fail.

### 10. Persistence, API, and UI

PostgreSQL stores queryable metadata; content-addressed storage holds evidence; the API enforces authorization and serves stable pagination/streaming; the UI shows *links to evidence*, not confident-looking decorations. Know transaction boundaries, migration rollback limitations, cursor stability, and empty/loading/error states. Practice: ingest the same run twice, request an unauthorized run, paginate while new events arrive, and click from a graph edge to its source record.

### 11. Testing and measurement

Unit tests check a local rule; property tests explore an invariant; integration tests check component contracts; E2E tests check a user's path; adversarial tests ask whether a false claim can slip through. Benchmarks require recorded hardware, dataset, command, runs, and raw results. Report p50/p95 and memory, not a handpicked best run. Practice: deliberately break one release artifact and verify the gate names it. Never adjust a threshold after seeing a result without an ADR and an explanation.

### 12. Explaining the system

Be ready to give a two-minute story: “An agent run caused an incident; here is the first evidence, how it propagated, what state we could actually restore, what replay reproduced, and which tested policy prevented it with what benign cost.” Then be ready for the hard follow-up: “What could Sentinel *not* know?” A good answer includes remote rollback, true concurrency, uninstrumented boundaries, and the uncertainty of adaptive behavior after intervention.

## Deeper study after the V1 gate

1. **Systems reliability:** study write-ahead logs, crash consistency, idempotency, and distributed transactions. Apply one lesson to an actual failure-injection test.
2. **Security engineering:** study threat modeling, key management, least privilege, and secure archive processing. Revisit the signer trust boundary and authorization tests.
3. **Causal inference:** study why observed sequence is not necessarily causation. Keep Sentinel's typed dependency claims narrower than universal counterfactual claims.
4. **Performance engineering:** learn profiling, p50/p95 latency, memory budgets, streaming algorithms, and query plans. Re-run the 50k benchmark on a different machine with configuration recorded.
5. **Agent evaluation:** compare deterministic simulator results with repeated live exploratory branches. Report uncertainty and sampling settings rather than a single success story.

The future reading plan is a *study direction*, not permission to expand V1 scope. Finish the frozen guarantees first.

## Current hands-on lab: trace one incident and inspect one trust boundary

The code is deliberately more than a blank scaffold, so use it as material to interrogate. This lab is not a claim that later slices are accepted.

1. Run `make check`, `make benchmark-journal`, and `make benchmark-journal-stream`. Explain which results are local one-run probes and why they do not establish full-agent overhead or API/UI latency.
2. Choose a fresh empty temporary directory and run `sentinel demo-mini DIRECTORY`. Observe two distinct journal roots. Run `sentinel mini inspect DIRECTORY/incident.jsonl` and locate the five boundary calls.
3. Run `sentinel mini investigate DIRECTORY/incident.jsonl DIRECTORY/benign.jsonl --output REPORT.json` and `sentinel provenance DIRECTORY/incident.jsonl 2 --output GRAPH.json`. Inspect both edge sets and blast radii. Find the chronological edges and explain why they are excluded from contamination traversal; explain why a declared keyed carrier is still not independent causal proof.
4. Predict what happens if the recorded network host changes from `demo.invalid` to `internal.demo.invalid`, then change the synthetic scenario or add a test and compare your prediction with the report. Describe why this is trace evaluation rather than actual OPA enforcement or a new future.
5. Export, verify, import, and replay an unsigned capsule. Read `docs/CAPSULE_CONTRACT.md` and `docs/THREAT_MODEL.md`; explain why rewriting both a local journal and its manifest can evade an unanchored digest. In a separate throwaway directory, use `sentinel local-anchor keygen CONTROLLER_DIR AGENT_DIR`, `sentinel capsule sign-local CAPSULE CONTROLLER_DIR/signing.ed25519.key ANCHOR_DIR AGENT_DIR`, `sentinel capsule verify-signed CAPSULE ATTESTATION CONTROLLER_DIR/signing.ed25519.pub`, and `sentinel capsule import-signed CAPSULE ATTESTATION CONTROLLER_DIR/signing.ed25519.pub NEW_EMPTY_DESTINATION`. Change an artifact and export a new self-consistent capsule: the unsigned check should pass but signed import against the old statement should fail before creating its destination. Explain why same-user file placement and a valid signature still do not prove isolation or freshness; that is the later S28/S53 work.
6. In a throwaway directory, capture `sentinel workspace snapshot`, alter the source file, restore into a new destination, and run `sentinel workspace verify`. Try adding a symlink to the source. Explain why this local regular-file proof is still not `VERIFIED_REPLAY` and why the future hostile-race tests matter.

Write your answers in a lab note. Your personal modification—not merely rerunning the assistant's tests—is the contribution that makes this learning yours.

## What to do next, today

Run `make check`, then `UV_CACHE_DIR=.uv-cache .venv/bin/uv run --frozen sentinel demo-mini /tmp/sentinel-mini-<unique-name>` (choose a fresh empty path). Inspect both JSONL files. Explain why the chain can detect a changed row and why `BOUNDARY_REPLAY_MATCHED` is a deliberately narrower claim than `VERIFIED_REPLAY`. Then take Day 1's GitHub steps yourself and record the CI link and your teach-back in `docs/STATUS.md`.
