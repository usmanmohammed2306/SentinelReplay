# Current engineering evidence: recording-latency remediation

Validated November 14, 2026 on **6a9ee3c**, with **950 frozen source/configuration/fixture/ADR files**. The source root is `sha256:dafea660efb0614de88a1eae8792b04387cc50715d6e7ce99a5fa61206c8de5d`.

**Full V1 release remains blocked by independent qualification.** The [release report](release-report.json), [43-row manifest](manifest.json), [status](../../../docs/STATUS.md) and [methods](../../../docs/PRODUCTION_EVIDENCE_2026-11-14.md) state the remaining gates.

## Recording qualification

The final formatted and tested source passes both owner-approved ADR-0004 numeric budgets in its 25-pair run: **0.262433 s p95** against ≤0.5 s, and **81.5369 µs median amortized added wall time per boundary** against ≤150 µs. Relative overhead is **3963.8618%**, still failing the original 20% comparison, retained as a nonbinding diagnostic.

The implementation reuses a canonical encoder and writes compact metadata. It preserves typed canonical bytes, metadata publication before effects, per-event flush/fsync, telemetry and persisted journal verification. A new golden pre-change capsule verifies recorded clock/RNG/model inputs and a materialized effect without live fallback. Three literal historical source profiles remain supported; unknown profiles are refused.

The [comparison](recording-comparison.json) retains distinct sequential 25-pair cohorts:

| Cohort | Recording p95 | Median recorded time | Median added/boundary |
| --- | --- | --- | --- |
| [Captured pre-change control](baseline-control/results.json) | 0.277218 s | 0.261629 s | 85.2416 µs |
| [First implementation snapshot](current-overhead/results.json) | 0.320301 s | 0.253785 s | 82.2883 µs |
| [Qualified final source](final-overhead/results.json) | 0.262433 s | 0.251910 s | 81.5369 µs |

The first snapshot passed numeric budgets but needed source formatting before the full test gate; its [failed lint receipt](current-local.json) remains. The control also passes the absolute budgets. The observed final/control median difference is 3.7%, with no cross-version counterbalancing or population/causal claim. This is not a representative-service tail-latency fix. The [previous qualified source's 0.538334 s miss](../recording-qualification-2026-11-14/current-overhead/results.json), original ten-pair 4045.6% failure and all earlier cohorts remain unchanged.

All timed runs use 3,000 actions / 3,001 durable boundaries, fixed model stubs, alternating arms in one interpreter, no timed OPA/model delay and no periodic prefix signing. They do not qualify signed-mode overhead or arbitrary live agents.

## Other current validation

| Evidence | Observed result |
| --- | --- |
| [Required tests](current-local-final.json) / [guarded tests](current-guarded.json) | 260 / 269 passed; overlapping suites |
| [Production UI build](current-ui-build.json) / [Chromium](current-browser.json) | Actual build and six journeys passed |
| [Hosted CI](hosted-ci-complete.json) | All six jobs passed, including clean-checkout encrypted recovery |
| [Demo](current-demo/demo-report.json) | 17 named checks; 3,184 actions / 3,186 boundaries; three adapters |
| [Corpus](current-corpus/results.json) | 36 branches / 33 supported strict replays; nine supported incidents, two controls, one native unknown |
| [Fresh search](current-search/progress.json) / [resume](current-search-resume.json) | 41 executed policies / 492 case branches; two frontier points; exact resume verification |
| [Scale](current-scale/results.json) | 25 samples at 3k/10k/50k; 50k journal verification p95 0.700112 s and sparse graph p95 1.267 ms |
| [Browser timings, 3k](current-timeline-3k.json) / [50k](current-timeline-50k.json) | 25 samples each; 50k after-data p95 0.1616 s, cold navigation 3.0014 s; selected-page virtualization |
| [PostgreSQL HTTP](current-postgres.json) | Fresh signed ingest with restricted application role; owned container removed |
| [Encrypted recovery](current-deployment.json) / [operations](current-operational.json) | Running-job SIGKILL, interruption, witness refusal, backup and fresh-volume restore; owned stacks removed |
| [Installed API](api-image-source.json) | All 69 package modules match; service UID 10001 |
| [Proof](current-proof.json) | Actual uninterrupted 75.28-second product recording, bound to the demo root |

The [raw-data manifest](../../evidence-archives/sentinel-latency-manifest-2026-11-14.json) lists seven archives with hashes and members. Expanded paths restore under this cohort. Included bytes are unchanged; private keys, caches and generated Git hooks are omitted. Source bindings inside each cohort remain authoritative. `source/validation/` retains exact commands, logs, output hashes, source inventories and exit codes. The [publication scan](publication-scan.json) checks known private values and archive structure; it is not a universal secret detector.

Independent provenance/blast-radius labels, representative overhead/load review, signer/freshness review and deferred owner teach-back remain pending. Synthetic fixtures, historical live-agent inference and the separately pending TRL experiment stay distinct. No model-training gain, AWS deployment, customer adoption, accepted learner slice or full production readiness is inferred.
