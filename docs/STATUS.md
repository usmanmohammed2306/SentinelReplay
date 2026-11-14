# Sentinel Replay — project status

Updated **November 14, 2026**. Frozen scope: 43 sections. Plan 4.2; local-first, AWS optional.

**The integrated reference implementation is public and tested. Full V1 release remains blocked.** Interview practice is deferred; no learner slice is accepted automatically.

## Verified on the current code

| Check | Observed result |
| --- | --- |
| Python | 239 passed; 6 guarded skips; 12 deselected; formatting, lint and strict mypy pass |
| Docker/OPA suite | 248 passed; 9 deselected |
| Browser | Six production Chromium journeys passed; 25 interactions each on 3k/50k fixtures |
| Hosted CI | [All six jobs passed](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43562514638), including fresh Linux checkout and encrypted crash/recovery |
| Integrated demo | 17 named checks; 3,184 synthetic actions / 3,186 recorded boundaries |
| Fixed corpus | 36 branches, 33 supported strict replays; 9 supported incidents, 2 controls, 1 native unknown |
| Policy search | 41 retained policies / 492 case branches; two frontier points; current-source resume verified without new candidates |
| Recovery | Encrypted Compose import, three snapshot adapters, running-job SIGKILL, interrupted job receipt, stopped-writer backup and fresh-volume restore passed; owned stacks removed |

The [source-bound evidence bundle](../benchmarks/results/production-hardening-2026-11-13/README.md) and [methods note](PRODUCTION_EVIDENCE_2026-11-14.md) retain reports, raw samples, execution receipts and archive hashes. Executable source is commit `541a09d`; the inventory includes 944 code/config/test-fixture files.

## Measured, with limits

- Five paired 3k fixed-stub trials showed **30.3% lower median recording time** versus the retained baseline. Per-event fsync remained enabled. This is not relative agent overhead.
- Current 50k journal verification p95: **0.718 s** across 25 warm in-process samples. Sparse graph lookup p95: **1.391 ms**. HTTP/browser and dense graphs are separate workloads.
- 50k timeline interaction p95 after data arrival: **0.104 s**; cold navigation-to-data: **3.07 s**. The UI virtualizes a selected 500-event page, not all 50k events at once.
- Local recovery API peak: **710,848,512 bytes** under a 1 GiB limit, zero OOM kills; 128-pid cap. This qualifies one bounded local operator workflow, not a service throughput SLO.
- Targeted policy stopped all 9 supported synthetic incidents and preserved 11/11 supported tasks; blanket denial preserved 0/11. The native case remains unknown. Earlier real-agent evidence stays separate.

## Release blockers retained

The ten-pair near-zero-work recording test measured **4045.6% median overhead**, above the frozen 20% target. Independent dependency/blast-radius labels, representative overhead/load review, signer/freshness review and owner teach-back also remain pending. A valid signature or retained per-run witness does not prove the latest complete history.

`sentinel release-check --stage release` must return nonzero while these gates remain open. No V1 tag, accepted slice or 100% production-readiness claim is made. S01 remains the active learner slice, 0/60 accepted. Interview preparation can resume separately.

Use the [README](../README.md), [operating runbook](SELF_HOSTED_PREVIEW.md), [compatibility contract](REPLAY_COMPATIBILITY.md), [acceptance matrix](V1_ACCEPTANCE.md) and [43-section map](SCOPE_TRACEABILITY.md). Public MIT main publication is owner-authorized; private learning/operator/career records remain excluded. No AWS, GPU or new model call was used in this final validation.
