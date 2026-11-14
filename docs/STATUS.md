# Sentinel Replay — project status

Updated **November 14, 2026**. Frozen scope: 43 sections; plan 4.2.1. Local-first; AWS optional and unused.

**The integrated reference implementation is public and tested. Full V1 release remains blocked.** Owner interview practice is deferred; S01 remains active, 0/60 learner slices accepted.

## Current engineering evidence

Source commit **939de2a**, with 948 frozen source/configuration/test-fixture/ADR files. [Evidence bundle](../benchmarks/results/recording-qualification-2026-11-14/README.md), [methods](PRODUCTION_EVIDENCE_2026-11-14.md), [release report](../benchmarks/results/recording-qualification-2026-11-14/release-report.json).

| Check | Observed result |
| --- | --- |
| Python | 259 passed; 6 guarded skips; 12 deselected; format/lint/strict mypy 132 files pass |
| Docker/OPA | 268 passed; 9 deselected; overlaps the required suite |
| Browser | Six production Chromium journeys passed; 25 interactions each on 3k/50k fixtures |
| Hosted CI | [All six jobs passed](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43625637430), including fresh Linux checkout and encrypted crash/recovery |
| Demo | 17 named checks; 3,184 synthetic actions / 3,186 boundaries; three snapshot adapters |
| Fixed corpus | 36 branches; 33 supported strict replays; 9 supported incidents, 2 controls, 1 native unknown |
| Policy search | 41 retained policies / 492 branches; two frontier points; resume revalidation adds no candidates |
| Recovery | Encrypted Compose, three adapters, running-job SIGKILL/interruption, read-only/missing witness, stopped-writer backup and fresh-volume restore passed; owned stacks removed |

## Recording decision and retained failures

The owner accepted [ADR-0004](adr/0004-recording-performance-qualification.md): p95 complete 3,000-action recording <=0.5 s and median paired amortized added wall time <=150 µs per actual durable boundary, across >=25 alternating pairs.

The fresh 25-pair run measured **0.538334 s p95: FAIL** and **93.8952 µs median added/boundary: PASS**. Its relative overhead remains **4066.6378%: FAIL against the original 20% comparison**, now a nonbinding diagnostic. The original ten-pair 4045.6% failure and pre-adoption 25-pair 0.292605 s / 88.2893 µs repeat are retained separately. No second repeat replaces the fresh miss. This is a revised acceptance criterion, not a runtime optimization.

These measurements use 3,001 boundaries, fixed stubs, no timed OPA/model latency and no periodic prefix signing. They are same-process alternating trials, not fresh-process replications, representative live-agent overhead, or a service SLO. Durability and replay semantics are unchanged.

## Other measurements, with limits

- 50k journal verification p95: **0.820 s**, 25 warm in-process samples. Sparse graph p95: **1.488 ms**; HTTP and dense graphs are separate.
- 50k browser interaction p95 after data arrival: **0.101 s**; cold navigation-to-data: **3.40 s**. The UI virtualizes a selected 500-event page.
- Recovery API peak: **634,109,952 bytes**, under 1 GiB / 128 pids with zero OOM kills. One local operator workflow, not concurrent service qualification.
- Targeted policy stopped 9/9 supported synthetic incidents and preserved 11/11 supported tasks; blanket denial preserved 0/11. Native effects remain unknown. Separate historical live-agent results are not merged into these denominators.
- Historical recorder optimization: 30.3% lower median recording time in five paired 3k trials, retaining per-event fsync. This remains its own before/after comparison, not relative overhead or a new result.

## Remaining gates

The current p95 recording miss, independent dependency/blast-radius labels, representative overhead/load review, signer/freshness review and owner teach-back remain open. A signature or retained per-run witness does not prove the latest complete history. The release command correctly returns nonzero. No full-production/V1 tag, learner acceptance, AWS deployment or new training result is claimed.

See the [README](../README.md), [runbook](SELF_HOSTED_PREVIEW.md), [compatibility contract](REPLAY_COMPATIBILITY.md), [acceptance matrix](V1_ACCEPTANCE.md) and [43-section map](SCOPE_TRACEABILITY.md). Private career, learner and operator records remain excluded from public main.
