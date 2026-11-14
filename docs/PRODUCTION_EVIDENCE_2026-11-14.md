# Production engineering evidence — November 14, 2026

The local-first reference implementation integrates CLI/API/UI, durable evidence, finite-pack replay, policy exploration and encrypted recovery. **Full frozen V1 release remains blocked.** Automated execution does not replace the remaining independent reviews or owner learning.

## Current source and execution

The [current bundle](../benchmarks/results/recording-qualification-2026-11-14/README.md) binds 948 source/configuration/fixture/ADR files to commit `939de2a`. Required checks passed 259 tests (6 guarded skips/12 deselected), format/lint and strict mypy 132 files. Guarded Docker/OPA passed 268 tests/9 deselected; these suites overlap. Six production Chromium journeys passed. [All six actual hosted jobs](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43625637430) passed, including PostgreSQL 17 signed ingest, both images and a fresh Linux checkout with locked install/no dependency cache, demo and encrypted crash/backup/fresh-volume recovery.

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

The owner explicitly accepted [ADR-0004](adr/0004-recording-performance-qualification.md). The implementation changes the qualification criterion, not the recorder's durability or runtime code:

| Measurement | Adopted criterion | Fresh 25-pair result |
| --- | --- | --- |
| Full 3k-action recording | Nearest-rank p95 <=0.5 s | 0.538334 s — FAIL |
| Paired amortized added time | Median <=150 µs per actual boundary | 93.8952 µs — PASS |
| Historical relative overhead | Original <=20%, now nonbinding diagnostic | 4066.6378% — FAIL |

The checker recomputes all three from raw paired durations. The fixture executes 3,000 actions/3,001 durable boundaries, verifies persisted counts, alternates arm order, and excludes model/OPA latency. Prefix signing is disabled in both arms. Twenty-five trials share one interpreter. This is neither individual append tail latency, representative live-agent overhead, nor a service SLO. No fabricated model delay dilutes the percentage.

The original published ten-pair 4045.6% failure and pre-adoption 25-pair 0.292605 s p95 / 88.2893 µs / 4366.2931% remain distinct. The latter passing repeat is not substituted for the fresh miss. [Summary and raw-data references](../benchmarks/results/recording-qualification-2026-11-14/qualification-summary.json) preserve this variation. A separate 27-byte fsync diagnostic motivated the proposal; it was not a formal lower bound or replacement benchmark.

## Other measured behavior

The demo passes 17 named checks with 3,184 synthetic actions/ 3,186 boundaries and workspace/Git/SQLite restoration. The fixed 12-case corpus executes 36 branches, including 33 supported strict replays. Nine supported incidents, two controls and one unsupported native-effect case remain explicit. Targeted denial removes 9/9 supported incidents with 11/11 supported tasks; blanket denial preserves 0/11. These are known synthetic fixtures, not unseen real-agent efficacy.

The existing 41-candidate / 492-branch search is resumed and revalidated, with two frontier points and no new candidates. Its archive remains the historical original; current-source revalidation is not a second search or global-optimality result.

At 50k boundaries, 25 warm in-process samples measure verification p95 0.819631 s and sparse-neighborhood lookup p95 1.488 ms. The separate browser fixture measures interaction p95 0.1013 s after data arrival, cold navigation-to-data 3.3957 s. It virtualizes a selected 500-event page. An initial scale attempt could not access the Docker socket and retained three PolicyUnavailable failures; explicit local Docker access resolved execution. Neither that retry nor historical loaded verification misses are hidden.

The local encrypted Compose rehearsal covers running-job SIGKILL, interrupted-state persistence, read-only/missing witness refusal, three-adapter replay before/restart/restore, stopped-writer backup and fresh-volume recovery. Both owned stacks are removed. API peak 634,109,952 bytes stays below 1 GiB with 128 pids and zero OOM kills. A 32-request burst may return 429 and is not a successful-throughput SLO. The uninterrupted product video lasts 75.16 s and binds the actual demo root.

Historical results, including the five-pair 30.3% recorder-time reduction, old loaded misses, failed CI attempts and separate 9-branch Qwen3B inference study, remain in their original source-bound cohorts. No training result, production customer adoption, AWS deployment, independent human adjudication, full V1 acceptance or student mastery follows from this engineering validation.
