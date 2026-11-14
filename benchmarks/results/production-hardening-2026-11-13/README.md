# Sentinel Replay — historical engineering baseline

Validated November 14, 2026 on source commit **541a09d**, with **944 frozen code/config/test-fixture files**. The directory date identifies this hardening cohort; each receipt records its actual UTC execution time.

Superseded by the [recording-qualification cohort](../recording-qualification-2026-11-14/README.md); measurements below retain their original source and criteria.

**Engineering checks passed; the full V1 release remains blocked.** See the [release report](release-report.json), [43-row manifest](manifest.json), [status](../../../docs/STATUS.md) and [methods](../../../docs/PRODUCTION_EVIDENCE_2026-11-14.md).

## Start with the results

| Evidence | Result / scope |
| --- | --- |
| [Required suite](current-local.json) / [guarded suite](current-guarded.json) | 239 / 248 passed; overlapping suites, not additive |
| [Browser journeys](current-browser.json) / [production build](current-ui-build.json) | Six journeys passed; actual Next.js production build |
| [Hosted CI](hosted-ci-complete.json) | Six current-source Linux jobs passed, including a clean checkout and encrypted recovery |
| [Demo](current-demo/demo-report.json) | 17 named checks, 3,186 boundaries and three snapshot adapters |
| [Corpus](current-corpus/results.json) | 36 branches; 33 supported strict replays; 9 supported incidents, 2 controls, 1 native unknown |
| [Policy search](release-search/progress.json) | 41 retained policies / 492 branches; two frontier points; current-source resume validates old candidates without rerunning them |
| [Scale](current-scale/results.json) | Raw 25-sample query/verification observations at 3k, 10k and 50k |
| [Recorder comparison](recorder-optimization-source-bound.json) | 30.3% lower median recording time in five paired fixed-stub trials; historical before/after sources retained |
| [Overhead and localization](current-overhead/results.json) | 10 paired trials; overhead fails the 20% target; 9 binary versus 129 linear restores on one 128-step fixture |
| [PostgreSQL HTTP](current-postgres.json) | Fresh local signed-ingest path, independent of the encrypted Compose rehearsal |
| [Deployment recovery](current-deployment.json) / [operations](current-operational.json) | Encrypted CAS, external witness, real running-job SIGKILL, fresh-volume restore, bounded memory/pids; owned stacks cleaned up |
| [3k interactions](current-timeline-3k.json) / [50k interactions](current-timeline-50k.json) | 25 browser samples each; data-arrival delay is reported separately from after-data interaction |
| [Proof recording](current-proof.json) / [capture events](current-capture.json) | Actual uninterrupted 75.32-second local UI recording, bound to the current demo root |
| [Provenance gate](provenance-pending.json) | Independent adjudication pending; no accuracy result invented |

## Source and raw evidence

`source/validation/current-*/` contains exact commands, logs, before/after source roots and output digests for the 13 executed validations. `source/current-source.json` lists every frozen input. `api-image-source.json` confirms all 69 installed API module bytes and non-root UID 10001. `source/current-package/` retains the final package.

The recorder optimization is a separate measured snapshot: `source/baseline/`, `source/package/` and `source/measure_pair.py`. Its two changed module hashes remain explicit; later hardening is not retroactively assigned to that experiment. The retained `source/derive_evidence.py` assembles summaries from completed receipts, and `source/build_manifest.py` assembles the release audit without supplying missing reviews. Their original invocation paths under the private controller tree are retained in receipts; use these public copies when reproducing the summary steps.

The [archive manifest](../../evidence-archives/sentinel-hardening-manifest-2026-11-13.json) binds five raw synthetic evidence archives. Verify the SHA-256, then extract a reviewed archive from the repository root:

```bash
tar -xzf benchmarks/evidence-archives/sentinel-hardening-scale-2026-11-13.tar.gz -C benchmarks/results
```

It restores the original `production-hardening-2026-11-13/current-scale/` paths, including the 50k capsule. Other archives hold the demo worlds/checkpoints, per-case corpus branches, paired overhead trials and retained policy-search candidates. Payload bytes are unchanged; tar owner metadata is normalized. Private keys, Git-generated hook templates and caches are omitted. No operator environment or human review labels are included.

## Failures remain evidence

- [Initial expanded CI failure](hosted-ci-first-failure.json): intentional 429 admission refusal encountered during fixture discovery; bounded setup retries fixed discovery without changing performance budgets.
- [Conformance CI failures](hosted-ci-conformance-first-failure.json): cold-data readiness and missing clean-room image preparation; fixes preserve separate after-data interaction timing.
- [Loaded scale miss](negative-loaded-scale.json), [definition](negative-loaded-scale-definition.json), `source/negative-loaded-validation/` and `source/negative-loaded-package/`: earlier source-bound 50k verification p95 exceeded 1 s under co-located work. Copies retain the original bytes and original receipt paths; original raw attempts remain local. A later quiet pass is not a concurrent-service guarantee.
- The current recording-overhead failure is in the primary report, not hidden in an older attempt. No invented model delay is added to improve its percentage.

All cases in this bundle are controlled synthetic fixtures. The earlier real-agent cohort remains separate. Missing independent labels, representative load/overhead review, signer freshness review and owner teach-back prevent full release acceptance; automated clean-room CI does not certify those facts.
