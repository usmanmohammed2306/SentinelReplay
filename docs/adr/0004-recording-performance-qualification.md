# ADR-0004: Workload-specific recording-performance qualification

Status: **Accepted by the owner**  
Date: 2026-11-14

## Decision

For the declared 3,000-action fixed-stub benchmark, the release qualification uses both:

- **p95 complete recording time <=0.5 seconds**, across at least 25 alternating recorded/unrecorded pairs.
- **Median amortized additional wall time <=150 microseconds per actual durable boundary**, calculated within each pair as `(recorded_seconds - unrecorded_seconds) / journal_records`, then taking the median.

The fixture has 2,999 fixed model stubs and one file write, producing **3,001 journal boundaries** because the write has a durable intent. Both arms execute the same interpreter, initial/final snapshots and local effect. Neither timed region contains model latency or OPA execution. Periodic prefix signing is disabled in both arms; this does not qualify signed-mode performance.

Per-event flush/fsync, hash chaining, effect-intent ordering, final persisted-journal verification, signatures, external witnesses and replay guarantees are unchanged. All 43 frozen product capabilities and the separate learner gates remain binding.

## Why the budget changed

The original <=20% engineering target divides by a near-zero-work baseline. The published ten-pair benchmark measured approximately 0.00664 seconds unrecorded and 0.26750 seconds recorded medians, with **4,045.6% median paired overhead**. The ratio of medians is not substituted for the median of paired ratios.

A separate 25-trial diagnostic of just 3,000 small writes with per-write flush/fsync measured 0.06500 seconds median. Twenty percent of the unrecorded median permits only 0.00133 seconds additional time. This diagnostic is not a mathematical lower bound or a substitute application benchmark; it motivates an explicit absolute qualification for this workload.

Before the owner accepted this revision, the proposed absolute limits were declared and a 25-pair repeat measured **0.292605 seconds p95** and **88.2893 microseconds median amortized added time per boundary**. The same repeat still had **4,366.2931% median relative overhead**. It used alternating trials in one interpreter, with imports excluded, not 25 independent fresh-process replications.

The owner explicitly chose to adopt the documented absolute budget and retain and publish the failed 20% comparison. This is a revision to the acceptance criterion, **not a speed improvement or a claim that the original target passed**. The execution plan permits measured budget revisions through an ADR.

## Executable evidence rules

`benchmarks/recording_overhead.py` retains every paired duration, trial order, actual verified journal count and unrecorded boundary-call count. The release check verifies at least 25 sequential alternating pairs, exactly 3,000 actions/3,001 boundaries in both arms, finite durations and consistency of every reported summary. It computes the nearest-rank p95 and median of paired amortized costs from raw samples.

The old comparison remains in `diagnostic_targets.legacy_recording_overhead_20pct`, with its actual pass/fail result and `binding: false`. It is excluded from the adopted numeric gate. Historical measurements remain bound to their original source and are not rewritten into the new report schema. The ADR itself is included in the frozen source inventory.

## Limits

This qualifies one controlled workload on the documented machine. It is not a production service SLO, a single-append tail-latency guarantee, a representative live-agent overhead measurement, or evidence of <=20% overhead on arbitrary agents. Model delays must never be fabricated to improve the percentage. Representative non-model workload, end-to-end load, independent provenance and trust reviews remain separate open gates; this approval accepts none of them or the owner's teach-back.
