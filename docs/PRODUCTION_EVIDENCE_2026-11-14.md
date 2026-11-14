# Production engineering evidence — November 14, 2026

The local-first reference implementation has integrated CLI/API/UI, durable evidence, finite-pack replay, policy exploration and encrypted recovery. **The full frozen V1 release is not accepted.** This note describes measured behavior, including failures; a green CI run does not replace the remaining reviews.

## Reproduce the engineering checks

```bash
uv sync --frozen
make check
make branch-contract
pnpm --dir ui install --frozen-lockfile
pnpm --dir ui build
pnpm --dir ui test:e2e
uv run --frozen sentinel release-check --stage release
```

Docker/OPA and the matching Playwright Chromium installation are required for their respective checks. The final release command deliberately fails while open gates remain. The [runbook](SELF_HOSTED_PREVIEW.md) documents keys, witnesses and bounded local deployment.

All final execution receipts bind the same 944-file inventory, including the original capsules consumed by tests. [Six actual hosted jobs](https://github.com/usmanmohammed2306/SentinelReplay/actions/runs/43562514638) passed on `541a09d`; its fresh-checkout job installs locked dependencies without the dependency cache, builds both images, executes the demo and performs encrypted crash/backup/fresh-volume recovery. That is automated independent-machine execution, not independent human adjudication.

## What was measured

| Workload | Result | Boundary |
| --- | --- | --- |
| Required / guarded Python suites | 239 / 248 passed | Overlapping suites; do not add the counts |
| Finite-program corpus | 36 branches / 33 supported strict replays | 12 known synthetic cases, including one unsupported native case |
| Targeted / blanket policy | 11/11 versus 0/11 useful tasks; both stop 9 supported incidents | No unseen-case efficacy claim |
| Retained greedy search | 41 candidates / 492 branches; two frontier points | Current-source resume rechecks retained results; not a new search or global optimum |
| Recorder optimization | 0.391 → 0.272 s medians; 30.3% reduction | Five alternating fresh-process pairs, 3k fixed stub, historical source snapshots retained |
| 50k verification | 0.718 s p95 | 25 warm in-process samples; no HTTP/browser cost |
| 50k browser interaction | 0.104 s p95 after data | 25 samples, first 500-event page; cold data arrival 3.07 s |
| Localization | 9 binary versus 129 linear restored prefixes | One 128-step monotone fixture |
| Recovery resource envelope | 710,848,512 peak API bytes; zero OOM kills | 1 GiB / 128 pids, single local operator; admission refusals allowed |

The final [bundle](../benchmarks/results/production-hardening-2026-11-13/README.md) retains definitions, every raw sample, source digests, command logs and receipts. Its archive manifest binds the larger synthetic worlds/capsules. The optimization snapshots remain distinct from the final validation code. Earlier failed runs are retained and labeled with their original source; later successes do not erase them.

## What remains unproven

The real durable recorder's near-zero-work test still incurs **4045.6% median relative overhead**, failing the 20% target. A previous co-located 50k verification run missed its 1 s p95 budget; the current quiet run passing does not establish a concurrent-service SLO. No artificial model delay is added to dilute overhead.

Independent provenance labels, reviewed blast-radius ambiguity, representative load/overhead qualification, signer/whole-history freshness recovery and owner teach-back remain open. A retained capsule witness detects conflicting identities for one run; it cannot prove global latest-state completeness. No claimed independent F1, adopted production workload, AWS deployment, new GPU/model experiment, or learner mastery is inferred.

The earlier one-seed live coding-agent cohort is described separately in [BRANCH_EVIDENCE_2026-11-13.md](BRANCH_EVIDENCE_2026-11-13.md). The finite pack's covered state/effect replay and the custom agent's boundary matching remain different guarantees.
