# Recording qualification and current engineering evidence

Validated November 14, 2026 on commit **939de2a**: 948 frozen source, configuration, fixture and ADR files. The [owner-approved decision](../../../docs/adr/0004-recording-performance-qualification.md) changes the recording acceptance criterion. It does not change recorder durability or turn a missed target into a pass.

**Full V1 release remains blocked.** The [release report](release-report.json), [43-row manifest](manifest.json), [status](../../../docs/STATUS.md) and [methods](../../../docs/PRODUCTION_EVIDENCE_2026-11-14.md) retain the unresolved gates.

## Recording results

| Cohort | Recording p95 | Median added time per boundary | Median relative overhead |
| --- | --- | --- | --- |
| Original ten pairs | Historical report; new criterion was not active | New denominator was not recorded | **4045.6% — fails original 20% target** |
| Pre-adoption 25 pairs | 0.292605 s | 88.2893 µs | **4366.2931% — fails 20%** |
| Fresh post-adoption 25 pairs | **0.538334 s — fails ≤0.5 s** | **93.8952 µs — passes ≤150 µs** | **4066.6378% — fails 20%** |

[Fresh raw pairs](current-overhead/results.json), [pre-adoption raw pairs](pre-adoption-repeat/results.json), [original ten-pair failure](../production-hardening-2026-11-13/current-overhead/results.json), [qualification summary](qualification-summary.json).

The old percentage stays in `diagnostic_targets.legacy_recording_overhead_20pct`, with its actual failed result and `binding: false`. It is not counted as a passed budget. The fresh p95 miss remains binding; no repeat replaces it. All three cohorts remain distinct and bound to their own source snapshots.

The fixed workload executes 3,000 actions and 3,001 durable boundaries. Arms alternate within one interpreter, exclude model/OPA latency, and disable periodic prefix signing. The checker recomputes nearest-rank p95 and the median of paired added time divided by actual boundary counts. This is neither representative live-agent overhead nor a service SLO.

## Other current checks

| Evidence | Result / scope |
| --- | --- |
| [Required suite](current-local.json) / [guarded suite](current-guarded.json) | 259 / 268 passed; overlapping, not additive |
| [Browser](current-browser.json) / [production build](current-ui-build.json) | Six production Chromium journeys; actual Next.js build |
| [Hosted CI](hosted-ci-complete.json) | All six jobs passed on this commit, including a clean Linux checkout and encrypted recovery |
| [Demo](current-demo/demo-report.json) | 17 named checks; 3,184 actions / 3,186 boundaries; three snapshot adapters |
| [Corpus](current-corpus/results.json) | 36 branches / 33 supported strict replays; nine supported incidents, two controls, one native unknown |
| [Policy-search revalidation](current-search-revalidation.json) | Existing 41 policies / 492 branches; two frontier points; resume adds no candidates |
| [Scale](scale-with-docker-access/results.json) | Raw 25-sample 3k/10k/50k in-process measurements; [initial Docker-permission failure](current-scale/results.json) retained |
| [PostgreSQL HTTP](current-postgres.json) | Fresh signed-ingest path with restricted application role; owned container removed |
| [Recovery](current-deployment.json) / [operations](current-operational.json) | Encrypted CAS, read-only/missing witness, running-job SIGKILL, fresh-volume restore; owned stacks removed |
| [3k](current-timeline-3k.json) / [50k](current-timeline-50k.json) browser timings | 25 interactions each; after-data and cold-navigation costs separated |
| [Proof](current-proof.json) | Actual uninterrupted local product recording, bound to the demo journal root |
| [Installed API](api-image-source.json) | All 69 installed modules match the checkout; service UID 10001 |

## Reproduce and inspect

[Raw-data archive manifest](../../evidence-archives/sentinel-recording-manifest-2026-11-14.json) lists hashes and members. Extract reviewed archives into `benchmarks/results/` to restore original paths. Included bytes are unchanged; private keys, caches and generated Git hook templates are omitted. Historical policy-search raw data remains in the prior cohort's archive, avoiding a duplicate search or relabeled measurements.

`source/validation/` contains exact commands, source inventories, logs, output hashes and exit codes. The source root is `sha256:76c1c6744a9166cfde434aad3448e3794391a2918d8f9c0d4f4fff8264e77607`. Receipts are local execution records, not authenticated independent reviewer statements. The [publication scan](publication-scan.json) checks retained private values and archive safety; it is not a universal secret detector.

Independent provenance/blast-radius labels, representative overhead/load review, signer/freshness review and owner teach-back remain pending. Synthetic fixtures and prior live-agent inference evidence stay separate. This cohort establishes no model-training improvement, AWS deployment, customer adoption, accepted learner slice or full production readiness.
