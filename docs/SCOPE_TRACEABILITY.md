# Sentinel Replay - Complete Scope Traceability

Status: **BINDING SCOPE CROSS-CHECK**  
Source: the complete 43-section flagship specification supplied on 2026-09-17 and reconfirmed on 2026-09-20  
Public scope authority: `FROZEN_PRODUCT_CHARTER.md`. The detailed execution and teaching plan remains local; its stable slice identifiers are retained in this matrix.

This matrix prevents the complete product from gradually turning into a smaller demo. Every source section maps to implementation tasks, acceptance evidence, or an explicit non-goal.

The mapped scope is V1. No mapped source requirement may be deferred by renaming it V2 work.

| Source section | Planned implementation | Primary evidence |
| --- | --- | --- |
| 1. Exact problem | Charter sections 1-2; S10 and S20 | executable incident workflow and README |
| 2. Six signature capabilities | Frozen charter section 3 | all six capability rows in the mandatory acceptance matrix |
| 3. End-to-end workflow | S01 through S30 | `sentinel demo` end-to-end report |
| 4. Recorder architecture | S02 through S05 | recorder unit/property tests and `ReplayMiss` proof |
| 5. Conformance ladder | charter section 5; S11; S33; S40 | versioned coverage report plus bounded SQLite adapter evidence in UI, CLI, API, and capsule |
| 6. OTel ingestion | S09 | authoritative-journal merge tests |
| 7. Snapshot engine | Stage 3 | restore fidelity and adversarial manifest reports |
| 8. Tamper-evident journal | S03 and S28 | corruption tests plus signed/anchored root verification |
| 9. Incident classifier | S09 | deterministic rule corpus results |
| 10. Incident compression | S10 | 3,000-step collapsed timeline and latency report |
| 11. Provenance DAG | S18 through S20 | typed-edge ground truth and precision/recall/F1 |
| 12. Blast-radius engine | S19 through S20 | reachable-set accuracy and overreach report |
| 13. Replay engine | S14 through S15 | checkpoint replay, fail-closed, and effect reconciliation tests |
| 14. Structural/effect divergence | S16 | injected divergence fixtures |
| 15. Incident bisect | S17 | predicate monotonicity and fallback tests |
| 16. Policy engine | S21 | OPA contract and decision-log tests |
| 17. Policy DSL | S22 | grammar, validation, Rego compilation, golden fixtures |
| 18. Alternate Futures | S25 | three supported futures with mode labels |
| 19. Minimal Intervention | S23 through S25 | tested candidates and transparent cost vectors |
| 20. Pareto frontier | S24 | nondominance property tests and UI chart |
| 21. Benign regression suite | S23 and S33 | versioned benign corpus and interference metrics |
| 22. Causal World Diff | S26 | typed timeline/state/effect/outcome diff |
| 23. Incident Capsules | S27 through S28 | deterministic capsule archive |
| 24. Capsule verification | S27 through S28; S40 | clean import, offline verification, supported replay |
| 25. Storage architecture | S06 through S07 | Postgres migrations and CAS tests |
| 26. Main data models | execution plan section 6 | versioned Pydantic schemas and migrations |
| 27. API surface | Stages 2-8, introduced by feature | OpenAPI contract and API integration tests |
| 28. CLI | Stages 1-8, introduced by feature | complete CLI command integration tests |
| 29. Frontend | S10, S20, S24 through S26, S37 through S39 | Next.js application and Playwright tests |
| 30. Product screens | S10, S20, S24 through S26, S39 | Runs, Incidents, Replay Lab, Policies, Capsules, Evidence |
| 31. Exact homepage | S39 | working homepage and demo links |
| 32. Demo corpus | S31 through S33 | twelve executable ground-truth scenarios |
| 33. Metrics | embedded by slice; S30 and S36 through S37 | machine-readable benchmark reports |
| 34. Testing | every stage gate | unit, property, contract, integration, corpus, E2E, security, performance |
| 35. Tech stack | execution plan section 3 | pinned lockfiles and Compose environment |
| 36. Innovation framing | README and S39 through S40 | accurate positioning without first-ever claims |
| 37. Explicit non-goals | frozen charter section 13 | conformance ladder and limitations documentation |
| 38. Job-market rationale | S39 through S40 | public proof package aligned to target roles |
| 39. Relation to AutoSeal | documentation only | separate repository/product identity |
| 40. Resume positioning | S40 | bullets containing only measured results |
| 41. Build schedule | sixty evidence-gated slices with variable duration | `STATUS.md` and stage-gate reports |
| 42. Mandatory definition of done | S30 and S40 | all sixteen charter clauses with direct evidence |
| 43. 75-second video | S39 | continuous product video using the executable demo |

## Complete-project interpretation

“Complete project” means:

- all six signature capabilities exist as integrated, executable product behavior;
- the documented CLI, API, UI, corpus, policy search, capsule, metrics, and deployment path exist;
- one deterministic environment pack supports the full proof path;
- one real coding-agent adapter demonstrates applicability beyond fixtures;
- all claims are bounded by visible coverage and replay-mode contracts;
- the 16-step `sentinel demo` acceptance sequence passes;
- the public proof package is backed by generated measurements.

It does not mean implementing the explicit non-goals: CRIU, kernel-scheduler replay, multi-node deterministic replay, general remote-service rollback, browser-VM replay, universal causal inference, a custom policy VM, custom telemetry, custom containers, or a distributed database.

## Release rule

The product cannot be called complete while any traceability row lacks its primary evidence. A polished UI or video cannot substitute for a missing system guarantee or failed end-to-end path.

## Optional AWS experiment after the local-first decision

The earlier AWS extension was additive to the original forty-three source rows, not part of those original requirements. On 2026-10-07, the user removed AWS from V1 scope. ADR-0003 and charter revision 1.7 make the self-hosted profile the required release path. The S3/KMS adapter, CLI, offline tests, and template remain optional experiments under ADR-0002; no AWS row or live-account check may fail the local V1 release gate. Independent local signing/anchoring, encryption, authorization, privacy, recovery, and clean-room proof are still required by the original evidence and deployment contract.

## November13 implementation reconciliation

The updated [sixteen-clause matrix](V1_ACCEPTANCE.md) and [current status](STATUS.md) now point to the integrated implementation, actual corpus/search/scale results, UI/API/SSE paths, three checkpoint adapters, encryption, trust/retention and recovery. The original43 rows above remain requirements rather than self-certified completion marks. The local release manifest binds exact source/artifact bytes; declared external and owner reviews remain separate. The product proof video is an actual75.24-second recording, not a mock interface.


November 14 performance-contract amendment: [ADR-0004](adr/0004-recording-performance-qualification.md), explicitly accepted by the owner, replaces the initial fixed-stub relative-overhead gate with two absolute qualifications: p95 complete recording <=0.5s and median paired amortized added wall time <=150us per actual boundary, across at least25 alternating pairs. The original20% failure remains a nonbinding diagnostic. No frozen capability, representative-load review, independent provenance requirement or learner gate is removed.
