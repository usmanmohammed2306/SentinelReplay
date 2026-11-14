# Sentinel Replay — project status

Updated **2026-11-13**. Plan **4.2.0**, local-first under ADR-0003.
**Engineering implementation and local validation are substantial; full V1 release is PARTIAL.**

The frozen forty-three-section product charter and the sixty-slice learning plan remain binding. AWS is optional. Neither a passing demonstration nor assistant-produced reference code accepts a student slice.

## Publication and first hosted CI

Source/evidence commit `d52f502` was pushed normally to `origin/main`. The user selected MIT after this publication; the MIT license is being added before the authorized public-visibility change. Public visibility is recorded only after verification. The [first hosted CI run](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43552119885) passed Python, the production UI image and PostgreSQL integration. OPA failed because its default container UID could not read owner-only Linux temporary input directories. The caller-UID/GID mapping fix retains private permissions, read-only mounts and network isolation. Local required checks215 passed, actual OPA checks3 passed, and a fresh integrated demo passed all17 checks after the fix. The [second hosted run](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43552561371) passed all four jobs on `c895b0f`: Python, production UI image, PostgreSQL integration and real OPA. Its [receipt](../benchmarks/results/release-local-2026-11-13/hosted-ci.json) names the exact source commit; browser journeys and broader guarded isolation remain locally validated.

The original release manifest and measurements remain frozen at their recorded source. The current default release audit therefore also reports source mismatches after this runtime change; it must be rebaselined with fresh source-bound validation before release. Old strict finite-pack capsules require their recorded runtime version; use `sentinel demo` for a fresh current-runtime run. This is an engineering/reproducibility gap, not a request for permission or an accepted V1 gate. See the [post-CI proof](../benchmarks/results/release-local-2026-11-13/post-ci-portability-fix.json).

## Current implementation

The local product connects recording, three declared checkpoint adapters, strict covered-effect replay, incident compression, provenance, OpenTelemetry enrichment, bisection, native OPA policy evaluation, alternate futures, policy search, world diff, signed capsules, encrypted storage, scoped authorization, persistent jobs/SSE, trust rotation/revocation, and retention. The Next.js UI exposes the investigation and execution paths. See the [acceptance matrix](V1_ACCEPTANCE.md), [environment contract](ENVIRONMENT_PACK_CONTRACT.md), and [operating runbook](SELF_HOSTED_PREVIEW.md).

The current engineering results are separate from earlier mini-agent and custom live-agent cohorts. Historical source snapshots and failed attempts remain retained. A later source edit does not retroactively change a measured snapshot.

## Executed local validation

| Check | Observed result | Scope |
| --- | --- | --- |
| `make check` | 215 passed, six guarded skips, twelve deselected; format/lint/strict mypy pass | Local required suite; guarded and PostgreSQL checks run separately |
| `make branch-contract` | 224 passed, nine deselected | Real local Docker isolation and OPA; no new model inference |
| Next.js production build | Passed | Locked frontend dependencies; TypeScript checked |
| Chromium journeys | 3 passed | Investigation, nested comparisons, distinct replay labels, local Monaco, auth, mobile layout, background bisection and terminal operation stream |
| Integrated demo | 17 scoped checks passed; 3,184 actions / 3,186 boundaries; six phases | Workspace/Git/SQLite restore, three strict finite-pack replays, policy frontier, bisection, signed progress, capsule export/import/replay |
| PostgreSQL / HTTP | Passed against fresh PostgreSQL 17.12 | Signed import, exact read-back, idempotency, altered archive 422, missing auth 401; run-table SELECT/INSERT allowed, UPDATE/DELETE refused |
| Encrypted Compose recovery | Passed on two fresh uniquely named stacks | Exact capsule and three-adapter replay before/after stopped-writer database/CAS backup; native OPA future, UID10001, public-key write refusal, 413 body limit; own volumes removed |
| Source rebuild | Fresh temporary source tree and noneditable virtual environment passed imported replay | Same host, locked dependencies, no workspace editable import; **not independent-machine reproduction**. Initial offline attempt failed on a missing cached wheel and remains retained |
| Product proof | Continuous 75.24-second recording captured | Actual local UI and 3,186-boundary synthetic investigation; captions explain scope; no invented results |

At the pre-CI measurement revision, the final API image matched all66 package source files; that image receipt is not a claim about later runtime edits. PostgreSQL17.12 is now digest-pinned after the November12 security release; the final HTTP and recovery checks passed on that version. Older17.11 runs remain historical.

The current release audit binds 181 source/config/test files and evidence digests, refuses missing/changed reports, and keeps engineering checks separate from declared external reviews. It never publishes or accepts a learning slice. Its result is [recorded with the release evidence](../benchmarks/results/release-local-2026-11-13/). GitHub workflow configuration exists, including the production UI image build; the four-job hosted run now passes on the CI-fix commit. This does not imply full release conformance.

## Corpus and policy results

The final [corpus report](../benchmarks/results/environment-pack-corpus-final-2026-11-13/results.json) contains **12 known synthetic cases × 3 policies = 36 branches**. Its population is nine supported incident cases, one unsupported native-effect case, and two controls.

| Policy | Supported incidents observed | Unknown cases | Supported legitimate tasks completed | Strict pack replays |
| --- | ---: | ---: | ---: | ---: |
| Allow all | 9 | 1 | 11/11 | 11/11 |
| Targeted | 0 | 1 | 11/11 | 11/11 |
| Deny all | 0 | 1 | 0/11 | 11/11 |

Unknown is not prevention. These observations do not establish unseen attack efficacy or prevention of ten incidents out of twelve. Injected provenance labels contain four positive pairs across two cases, authored by the same implementer; TP4/FP0/FN0 is **not independent provenance accuracy**.

The [final bounded search](../benchmarks/results/policy-search-final-2026-11-13/progress.json) evaluated **41 policies / 492 case branches**, with zero failures and two frontier points. Its task-preserving recommendation used eight rules versus the eleven-rule seed. Resume revalidated the retained policy, receipt, source and outcome bindings without additional candidates. This is a completed greedy deletion neighborhood, not a global minimum.

## Measured scale and costs

[Final scale samples](../benchmarks/results/product-scale-final-2026-11-13/results.json), one macOS arm64 host, 25 warm in-process SQLite/CAS samples per query:

| Boundaries | First page p50 / p95 | Sparse selected graph p50 / p95 |
| --- | --- | --- |
| 3,000 | 0.674 / 0.742 ms | 1.071 / 1.274 ms |
| 10,000 | 0.687 / 0.757 ms | 1.068 / 1.315 ms |
| 50,000 | 0.686 / 0.767 ms | 1.066 / 1.271 ms |

At 50k, recording including OPA/telemetry/snapshots took7.446 seconds in one run; journal verification p50/p95 was0.788/0.822 seconds; the capsule contained52,391,080 bytes. These component figures exclude HTTP/browser time, dense graphs and concurrent load. They are not production SLOs.

The separate final PostgreSQL17.12 encrypted-stack50k HTTP probe measured25 warm samples per query: first-page p50/p95 **8.12/14.26ms**, sparse graph **9.21/9.95ms**. Eight clients issued32 requests:2 returned200 and30 returned deliberate429; no500 occurred. This measures same-host loopback backpressure alongside other local validation activity, not browser latency, dense graphs or production throughput. Raw samples are in the release deployment receipt.

The [paired overhead/localization report](../benchmarks/results/recording-overhead-final-2026-11-13/results.json) measured nine binary restores versus129 linear restores on a 128-step monotone fixture. Ten alternating recording/unrecorded pairs on a 3,000-step near-zero-cost model stub showed approximately5,633% relative overhead. This is a real negative result for that workload, not a live-agent overhead estimate. No claim that the original representative overhead target has passed is justified. Signed progress checkpoints were disabled in that overhead comparison.

## Release gates still open

- Independently reviewed provenance/dependency labels, blast-radius overreach and ambiguity evidence.
- Representative live-agent recording overhead, repeated end-to-end HTTP/UI latency and concurrent-load/resource evidence.
- Independently reproduced clean installation and a separately witnessed signer/freshness recovery review. Local relative-head rollback controls do not establish global latest-state freshness.
- Fresh source-bound release baseline after the CI portability fix, plus verification of the authorized MIT/public publication. Hosted four-job CI passes; it is not the complete release suite.
- Owner review, day-by-day rebuild and teach-back. Full native-agent semantic replay remains outside the declared adapter; the real coding-agent adapter uses boundary matching.

The completed local tests and source rebuild narrow these gaps; they do not erase them. No AWS deployment, new GPU allocation, new model call, Git commit/push, license decision or public visibility change occurred in this continuation.

## Learning and publication state

- Active task: **S01 — Project pulse**; Stage 1 gate **TODO**.
- Accepted student slices: **0/60**. No personal mastery or independent authorship is certified by engineering receipts.
- Existing repository: `usmanmohammed2306/SentinelReplay`; historical initial import and README publication are recorded in the private handoff. Hosted CI passed on `c895b0f`; MIT was selected by the user. Public visibility is recorded after verification.
- The local `BUILD_LEARN_COMMIT_GUIDE.md` maps every working day/slice to a small build, a failure to test, official reading, teach-back and a real user-owned commit. Sixty slices are not sixty guaranteed elapsed days.

The single active plan remains4.2. Scope and evidence thresholds are not reduced to protect a date.

## November13 publication preparation

The user authorized a direct push to `main`. Source, public documentation, product assets, reviewed summary/source evidence and the small test fixtures are prepared for publication. Final raw synthetic outputs are preserved as digest-listed compressed archives; bulky generated working copies, private operator material, career notes and learning records stay local. This is a source/evidence publication, not a V1 tag or acceptance of any release/learner gate. Remote push and hosted CI status are recorded only after verification.

## Remaining production work and ownership

These are substantive engineering/evidence gaps; they are not all requests for human permission.

| Work | Why the current result is insufficient | Owner/action |
| --- | --- | --- |
| Recording performance | The near-zero-work fixture measured about5,633% overhead; the20% target did not pass | Profile/optimize recording, measure a justified representative workload and retain negative controls; do not hide costs with model latency |
| Release enforcement | A report-presence check can pass while the budget fails | Enforce numeric quality thresholds and complete16-clause/43-row traceability; preserve nonzero failure |
| Replay versions and release baseline | Source-bound capsules correctly reject the changed OPA runtime identity | Define supported version compatibility, retain original interpreters/sources and generate a fresh coherent release baseline |
| Provenance and blast radius | Four same-implementer injected pairs do not establish independent accuracy or overreach | Freeze blind labels/ambiguities and obtain independent adjudication, then score exact roots |
| Operational reliability | Eight-client/32-request backpressure and same-host restoration are narrow proofs | Repeat UI/load/failure/recovery tests against explicit capacity/resource targets on a clean environment |
| Signer/freshness trust | Local ledger detects rollback relative to a retained head, not whole-controller rollback | Validate separate signer/witness ownership and recovery under the declared attacker identity |

Most implementation and test work can continue without new credentials, AWS or a GPU. MIT/public publication affects distribution only; it does not accept production-readiness gates. Independent adjudication and owner teach-back cannot be self-certified by the implementation assistant. The source publication is complete; the production/learner release is not.
