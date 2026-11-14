# Production engineering evidence — November 14, 2026

The local-first reference implementation integrates CLI/API/UI, durable evidence, finite-pack replay, policy exploration and encrypted recovery. **Full frozen V1 release remains blocked.** Automated execution does not replace the remaining independent reviews or owner learning.

## Current source and execution

The [current bundle](../benchmarks/results/latency-remediation-2026-11-14/README.md) binds 950 source/configuration/fixture/ADR files to commit `6a9ee3c`. Required checks passed 260 tests (6 guarded skips/12 deselected), format/lint and strict mypy 132 files. Guarded Docker/OPA passed 269 tests/9 deselected; these suites overlap. Six production Chromium journeys passed. [All six actual hosted jobs](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43632258338) passed, including PostgreSQL 17 signed ingest, both images and a fresh Linux checkout with locked install/no dependency cache, demo and encrypted crash/backup/fresh-volume recovery.

```bash
uv sync --frozen
make check
make branch-contract
pnpm --dir ui install --frozen-lockfile
pnpm --dir ui build
pnpm --dir ui test:e2e
uv run --frozen sentinel release-check --stage release
```

Docker/OPA and matching Playwright Chromium are required. The last command deliberately fails while required gates remain open. The [runbook](SELF_HOSTED_PREVIEW.md) documents the local trust/witness/encryption boundary.

## Recording qualification: two budgets, all failures retained

The owner explicitly accepted [ADR-0004](adr/0004-recording-performance-qualification.md). The ADR changes the qualification criterion. The separate serialization revision reduces avoidable encoding work while preserving recorder durability and typed hash semantics:

| Measurement | Adopted criterion | Fresh 25-pair result |
| --- | --- | --- |
| Full 3k-action recording | Nearest-rank p95 <=0.5 s | 0.262433 s — PASS |
| Paired amortized added time | Median <=150 µs per actual boundary | 81.5369 µs — PASS |
| Historical relative overhead | Original <=20%, now nonbinding diagnostic | 3963.8618% — FAIL |

The checker recomputes all three from raw paired durations. The fixture executes 3,000 actions/3,001 durable boundaries, verifies persisted counts, alternates arm order, and excludes model/OPA latency. Prefix signing is disabled in both arms. Twenty-five trials share one interpreter. This is neither individual append tail latency, representative live-agent overhead, nor a service SLO. No fabricated model delay dilutes the percentage.

The original published ten-pair 4045.6% failure, pre-adoption 25-pair 0.292605 s /88.2893 µs repeat, and prior qualified source's 0.538334 s p95 miss remain unchanged in their original cohorts. The new final source has one qualified 25-pair run. A separate captured pre-change control also passes; the first implementation snapshot passed numeric budgets but required source formatting before its full test gate. All three new cohorts, their raw samples and source snapshots are retained in the [comparison](../benchmarks/results/latency-remediation-2026-11-14/recording-comparison.json). No failing measurement is rewritten into a pass.

The implementation avoids pretty-printing large metadata and reuses a stateless canonical encoder. Golden typed-wire bytes, per-event fsync, metadata-before-effect publication, complete telemetry and persisted verification remain checked. The sequential control's recording median is 0.261629 s versus 0.251910 s for final source, an observed 3.7% difference. There is one process per cohort, without cross-version counterbalancing; this is not a causal or population speedup estimate. The historic five-pair 30.3% comparison remains a separate experiment.

## Other measured behavior

The demo passes 17 named checks with 3,184 synthetic actions/ 3,186 boundaries and workspace/Git/SQLite restoration. The fixed 12-case corpus executes 36 branches, including 33 supported strict replays. Nine supported incidents, two controls and one unsupported native-effect case remain explicit. Targeted denial removes 9/9 supported incidents with 11/11 supported tasks; blanket denial preserves 0/11. These are known synthetic fixtures, not unseen real-agent efficacy.

A fresh current-source search executed 41 candidates / 492 case branches, produced two frontier points and completed its declared greedy neighborhood. Resume verified all retained outputs without adding candidates. Historical search data is not relabeled; neither run proves global optimality.

At 50k boundaries, 25 warm in-process samples measure verification p95 0.700112 s and sparse-neighborhood lookup p95 1.267 ms. The separate browser fixture measures interaction p95 0.1616 s after data arrival, cold navigation-to-data 3.0014 s. It virtualizes a selected 500-event page. Historical permission, loaded-scale and CI failures remain in their original bundles.

The local encrypted Compose rehearsal covers running-job SIGKILL, interrupted-state persistence, read-only/missing witness refusal, three-adapter replay before/restart/restore, stopped-writer backup and fresh-volume recovery. Both owned stacks are removed. API peak 549,949,440 bytes stays below 1 GiB with 128 pids and zero OOM kills. A 32-request burst may return 429 and is not a successful-throughput SLO. The uninterrupted product video lasts 75.28 s and binds the actual demo root.

Historical results, including the five-pair 30.3% recorder-time reduction, old loaded misses, failed CI attempts and separate 9-branch Qwen3B inference study, remain in their original source-bound cohorts. No training result, production customer adoption, AWS deployment, independent human adjudication, full V1 acceptance or student mastery follows from this engineering validation.
