# Full V1 acceptance matrix

Updated November 14, 2026. **Full release remains blocked.** The integrated reference implementation is public; the frozen 43-section scope and separate learner workflow remain binding.

The executed demo checks the sixteen workflow clauses below plus periodic signed checkpoints. [Current commands, source bindings and measurements](PRODUCTION_EVIDENCE_2026-11-14.md) supersede earlier engineering snapshots. The [machine-readable release report](../benchmarks/results/production-hardening-2026-11-13/release-report.json) determines which current artifacts, budgets and review receipts pass.

| Clause | Implemented and executed | Remaining qualification |
| --- | --- | --- |
| 1. At least 3,000 recorded steps | 3,184 synthetic actions / 3,186 boundaries; local demo and clean-checkout Linux CI | Owner review remains separate from automated execution |
| 2. Detected incident | Versioned catalog; 12 known cases, 9 supported incidents, 2 controls, 1 native unknown | Independent labels; no unseen real-agent efficacy claim |
| 3. Collapsed timeline | Six demo phases; virtualized UI; 25 interactions each on 3k/50k fixtures | Representative end-to-end load review; paginated UI is not all-events rendering |
| 4. Root provenance | Declared carrier links, source-bound graph, CLI/API/UI/capsule | Independent adjudication and nonvacuous F1 evidence |
| 5. Typed blast radius | Typed reachability, chronology excluded, bounded traversal/completeness flag | Independently reviewed ambiguity and overreach |
| 6. Pre-incident restoration | Regular files, quiescent Git worktree/index/HEAD/objects, committed SQLite snapshot | Independent adapter review; no arbitrary process/database rollback guarantee |
| 7. Strict recorded replay | 33 supported corpus replays; original historical capsule compatibility; missing/unknown evidence fails closed | Finite-pack coverage only; live custom-agent replay remains boundary matching |
| 8. Three policies | Actual OPA allow-all, targeted and deny-all; deployed native evaluator | No held-out or general real-agent prevention claim |
| 9. Alternate future | Executed finite-program forks through API/UI with explicit modes | Independent mode/coverage review; unsupported native effects remain unknown |
| 10. Pareto intervention | 41 retained candidates / 492 branches; two frontier points; resume reverified | Bounded greedy neighborhood, not global optimality |
| 11. World diff | Covered file/executable-bit changes and ordered input/effect divergence | Broader effects require explicitly declared adapters |
| 12. Journal and anchor | Durable chain, periodic signatures, retained-head rollback refusal, operator-held per-run witness | Signer-boundary and latest-complete-history recovery review |
| 13. Capsule export | Bounded shards/telemetry, Ed25519 statements, AES-GCM export; exact public-payload private-value scan | Independent privacy/trust review; scanning is not universal secret detection |
| 14. Import and verification | Trusted-key admission before archive parsing; idempotency, encrypted CAS, key epochs/revocation; SQL-reset conflict refusal | Signer/trust-state recovery review |
| 15. Imported replay | Three adapters through deployed HTTP before/after restart and fresh-volume recovery; clean Linux checkout CI | Automated reproduction does not replace human review |
| 16. Metrics | Raw 25-sample scale/browser data, 10-pair overhead and 128-step localization | Recording overhead fails 20% target; independent provenance and representative load/overhead qualification pending |

The current source passed 239 required Python tests, 248 overlapping guarded Docker/OPA tests and six production Chromium journeys. All six hosted jobs passed, including PostgreSQL integration, production UI image and no-dependency-cache clean-checkout encrypted recovery. The final local recovery rehearsal exercised running-job SIGKILL, persisted interruption, read-only/missing witness, bounded resources and stopped-writer backup into fresh volumes. Its 75.32-second continuous UI recording is root-bound in the proof receipt.

`sentinel release-check --stage release` audits exact source, test-fixture and artifact bytes, command receipts, numeric budgets, all 43 evidence rows and declared reviews. It must return nonzero for missing, changed or failing required evidence. Review receipts do not cryptographically authenticate reviewer independence or personal mastery.

The [43-row scope map](SCOPE_TRACEABILITY.md) and charter are unchanged. Owner interview practice is deferred; learner slices remain 0/60 accepted, with S01 active. No V1 tag, full production-readiness claim or AWS deployment is inferred from this engineering checkpoint.
