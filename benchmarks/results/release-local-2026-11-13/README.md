# Local validation evidence — November 13, 2026

The pre-CI frozen [release report](release-report.json) passes **12/12 artifact-based engineering checks**, with **zero source mismatches**, and returns **RELEASE_BLOCKED** for eight pending external/owner review gates. This is the expected fail-closed result. A local artifact audit cannot establish reviewer identity, personal mastery, global latest-root freshness or full production readiness.

The [manifest](manifest.json) binds181 source/config/test files and exact artifact digests. The active CLI defaults to the identical `../current-release-manifest.json`. Source-bound test receipts were captured before/after commands; private logs are hashed, not published with operator environment files.

| Evidence | Result |
| --- | --- |
| [Required checks](local-tests.json) |215 passed; six guarded skips and twelve optional/integration deselections; format/lint/strict mypy pass |
| [Guarded suite](guarded-tests.json) |224 passed; nine deselected; actual local Docker/OPA |
| [Production UI build](ui-build.json) and [Chromium](browser-tests.json) |Build passed; three journeys passed |
| [API image source](api-image-source.json) |All66 installed package source files match current source; image config ID retained |
| [PostgreSQL17.12 HTTP](postgres_http.json) |Signed ingest, idempotency, corruption/auth controls, restricted run-table role |
| [Encrypted deployment/recovery](deployment_recovery.json) |Fresh stacks; native OPA, sealed export, exact original capsule, three-adapter replay, persistent job/result/terminal SSE and stopped-writer restore; owned volumes removed |
| [Video](proof-video.json) |75.24-second continuous real product capture; exact video digest and journal root |
| [Isolated source rebuild](isolated_source_rebuild.json) |Fresh noneditable environment and imported replay, same host; not independent-machine reproduction |
| [Known-secret scan](known_secret_scan.json) |No generated local bearer/database secret matched35,392 candidate files; not a universal secret detector |
| [Snapshot accounting](snapshot-dedup.json) |8,917 logical referenced bytes /8,844 unique snapshot blob bytes on the small combined fixture; no inflated dedup claim |

Core result reports are linked by the manifest:3,184-action integrated demo; twelve-case36-branch corpus;41-policy492-branch greedy search with verified resume;3k/10k/50k scale; ten paired overhead trials and actual9-versus129 prefix restore comparison. Same-implementer injected provenance labels and the native-effect unknown remain explicit.

On PostgreSQL17.12, the50k warm-index loopback HTTP probe recorded25 samples per path: first-page p50/p95 approximately8.12/14.26ms; sparse graph9.21/9.95ms. Eight clients issued32 requests: two returned200, thirty returned deliberate429 backpressure, and none returned500. These are same-host component measurements, taken alongside local validation activity; they exclude browser rendering and dense graphs and do not establish a production SLO.

The approximately5,633% relative recording overhead on the near-zero-work stub **does not pass the original20% engineering target**. Representative overhead, independent provenance/blast-radius review, end-to-end load/browser review, independent clean reproduction, signer/freshness review, hosted CI, license/distribution and owner teach-back remain unaccepted. Do not turn twelve local artifact checks into a full production or student-release claim.

`manifest-attempt01.json` and the initial parser-failure report preserve the first release-audit attempt. It rejected floating-point measurement reports; the corrected parser accepts finite decimal measurements while canonical evidence serialization still rejects floats. The unit regression also rejects duplicate keys, nonfinite values and excessive nesting. Earlier recovery, browser setup, missing-cache and live-agent failures remain in their original result/private-log locations; they are not relabeled as successful.

[Component source compatibility](component-source-compatibility.json) records each measured snapshot. The scale runner archived all then-present modules, including an unused CLI file that later changed; measured recorder/index sources still match. Its original source archive is preserved rather than rewritten.

Re-run the artifact audit from the repository root:

```bash
uv run --frozen sentinel release-check --stage release
```

The command returns nonzero until missing requirements are resolved and reviewed. It performs no publication, deployment, cloud/provider call or student-slice acceptance.

## Hosted CI portability follow-up

The first source push passed hosted Python/UI/PostgreSQL jobs and exposed an OPA Linux bind-mount permission failure. The caller-identity fix and fresh local integrated-demo proof are in `post-ci-portability-fix.json`. Frozen reports/source hashes remain unchanged; the current runtime now differs and the default audit correctly flags that mismatch. Rebaselining current source and defining supported replay-version compatibility remain release work. A report-presence pass is not a performance-budget pass.
