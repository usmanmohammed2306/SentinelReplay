# Sentinel Replay - Frozen Product Charter

Status: **FROZEN AND LOCKED**  
Frozen on: **2026-09-17**  
Charter revision: **1.7.0 (2026-10-07 local-first release decision)**  
Release class: **Complete Flagship V1 - not a prototype**  
Delivery duration: **variable; no calendar minimum or maximum**  
Integrated alpha: **after accepted Slice 30 and its gate**  
Feature-complete beta: **after accepted Slice 40 and its gate**  
V1 release: **after accepted Slice 60 and every release gate**

## 1. Product definition

Sentinel Replay is a record/replay and incident-forensics platform for autonomous AI agents, with deterministic guarantees only inside its declared coverage contract. It records replay-relevant nondeterminism and environment mutations, merges them with OpenTelemetry traces, compresses long executions into readable incident phases, reconstructs evidence-backed provenance and blast radius, restores verified pre-incident state, evaluates the agent under alternative policies, explores supported alternate futures, identifies the least disruptive tested intervention that prevents the incident, and packages the investigation into a tamper-evident portable incident capsule.

Public tagline:

> Reconstruct the incident. Rewind the agent. Explore alternate futures. Find the smallest fix.

Recruiter description:

> A black-box flight recorder and time-travel debugger for AI agents.

Engineering description:

> A fail-closed record/replay and incident-forensics system combining boundary recording, verified state restoration, OpenTelemetry ingestion, tamper-evident evidence, provenance analysis, replay bisection, counterfactual policy evaluation, and bounded intervention search.

### Complete Flagship V1 contract

V1 means the complete ambitious product described by the forty-three-section source specification. It is not a recorder-only prototype, a UI mock-up, or a reduced MVP. The following are V1 requirements and may not be deferred to a hypothetical V2:

- all six signature capabilities as integrated behavior;
- first-class CLI, REST/SSE API, and professional investigation UI;
- PostgreSQL metadata, content-addressed evidence, OpenTelemetry enrichment, Docker isolation, and declared snapshot adapters;
- verified restoration, fail-closed replay, structural/effect divergence, and honest bisection;
- deterministic incident compression, typed provenance, and evidence-backed blast radius;
- OPA/Rego enforcement, the finite policy DSL, benign-regression evaluation, bounded search, and the Pareto frontier;
- alternate futures, Causal World Diff, and portable signed incident capsules;
- one real coding-agent adapter plus the deterministic environment pack used for exact claims;
- the twelve-scenario corpus, 3k/10k/50k measurements, clean-room reproduction, homepage, and 75-second proof video;
- the complete sixteen-clause `sentinel demo` and automated release gate.
- a reproducible self-hosted deployment with isolation, independent evidence signing and anchoring, least-privilege access, backup/recovery, and measured local conformance. AWS is optional and is not a release gate under ADR-0003.

V1 is deliberately bounded where the source specification is bounded. Those explicit boundaries protect truthful guarantees; they do not make the result a prototype. No V2 scope is currently defined, and the label V2 must not be used to postpone a requirement listed above.

## 2. The five questions Sentinel must answer

Given a long-running agent incident:

1. What first contributed evidence or state to the incident?
2. Which later actions may depend on the compromised information or state?
3. Can Sentinel restore and verify the covered environment immediately before it?
4. Would a proposed policy have blocked the recorded incident action?
5. Which tested policy prevents the incident with the least measured disruption to the declared benign regression corpus?

## 3. Frozen signature capabilities

| Capability | User outcome | Technical basis |
| --- | --- | --- |
| Forensic Flight Recorder | Preserve replay-sensitive evidence | boundary recorder, journal, OTel, effect receipts |
| Incident Compression | Turn thousands of events into readable phases | deterministic rules, typed clustering, virtualization |
| Evidence-Backed Blast Radius | Show likely upstream dependencies and downstream contamination | typed provenance graph with labeled carriers |
| Time-Travel Replay | Restore covered state and reproduce the recorded path | verified snapshots, recorded boundaries, fail-closed matching |
| Alternate Futures | Compare explicitly classified policy-controlled branches | strict replay, deterministic simulation, or labeled exploratory execution |
| Minimal Intervention Search | Rank preventing policies by measured benign disruption | bounded policy grammar, incident predicates, regression corpus, Pareto analysis |

These six capabilities are frozen. Implementation details may change when tests demonstrate a better design, but none may be silently removed.

## 4. Core workflow

```text
agent execution
    -> journal + boundary recordings + OTel + effect receipts
    -> normalize into a typed step stream
    -> classify and compress incident phases
    -> build typed provenance and blast-radius views
    -> select a fork point
    -> restore and verify covered state
    -> replay recorded history until match or divergence
    -> evaluate candidate policies
    -> run supported alternate branches
    -> compare structural, effect, and outcome differences
    -> rank nondominated interventions
    -> export and verify an incident capsule
```

## 5. Replay and restoration contract

Restoration and replay are separate guarantees.

| State or nondeterminism | Mechanism | Guarantee |
| --- | --- | --- |
| Model completion | exact recorded response addressed by stable call identity and canonical request digest | exact within the recording |
| Read-only HTTP/tool result | exact recorded response | exact within the recording |
| Effectful tool | recorded decision plus explicit effect receipt or sandboxed re-execution | exact only for declared adapters |
| Clock | intercepted values | exact within the recording |
| RNG | intercepted values or declared seed | exact within the adapter contract |
| Workspace filesystem | content-addressed checkpoint plus verified restore | byte-identical for declared covered paths |
| Git state | explicit capture of worktree, index, HEAD/refs, and required objects | exact for the declared repository boundary |
| Database state | adapter-specific snapshot at a declared consistency point | exact only for the declared adapter and snapshot boundary; no general rollback guarantee |
| External remote state | response recording only | no rollback guarantee |
| Process tree | no general restoration | unsupported unless an adapter declares coverage |
| True concurrent interleaving | no general deterministic replay | unsupported |

Fail-closed invariant:

> A missing or mismatched recording raises `ReplayMiss`. Strict replay never falls through to a live model, network, clock, RNG, or undeclared tool.

All branch results must carry the mode defined in ADR-0001.

## 6. Provenance contract

The graph represents evidence-backed dependency candidates, not universal proof of causation.

Permitted edge types:

- `dataflow`
- `filesystem`
- `effect`
- `trace_parent`
- `control`
- `chronological`

Requirements:

- Every edge has a type, source, confidence rationale, and redacted or fingerprinted carrier.
- Chronological fallback edges never contribute to contamination reachability.
- Blast radius defaults to evidence-bearing dependency edges.
- OpenTelemetry parentage is structural evidence, not automatic causal confirmation.
- Precision, recall, and F1 are measured against injected ground-truth dependencies.

## 7. Incident and policy contract

The incident classifier is deterministic and rule-based in v1. A missing rule hit means only that no declared rule matched.

Policy enforcement uses a finite, versioned policy grammar compiled to a policy engine such as OPA/Rego. Initial policy atoms cover:

- tool allow, deny, and confirm
- network allowlist, denylist, and default deny
- filesystem read/write patterns
- secret exposure patterns
- process execution patterns
- Git write restrictions
- artifact export restrictions

Minimal intervention means:

> The least disruptive nondominated policy among the tested candidates, on the declared incident and benign regression corpus, under published outcome predicates and cost components.

Sentinel must show the Pareto frontier. A single winner may be recommended only when the selection rule and weights are visible.

## 8. Evidence contract

The journal is hash chained. Periodic roots must be signed or anchored outside the recorded agent's writable trust boundary.

Sensitive content requirements:

- encrypt recordings and capsules at rest when they contain raw content;
- redact secrets in the UI and exported summaries;
- use keyed fingerprints for sensitive provenance carriers;
- record access and export actions;
- publish retention and deletion behavior;
- never describe an unanchored, rewriteable local chain as immutable.

### Local-first production trust boundary

ADR-0003 makes the self-hosted profile the sole required V1 deployment path. Its signer and evidence-root anchor must be outside the recorded agent's writable sandbox; key ownership, rotation, verification, backup, and recovery must be tested. The already implemented S3/KMS evidence adapter is an optional offline-tested experiment under ADR-0002, not a required or deployed AWS product. No live AWS validation is needed for V1. Neither the local product nor the optional adapter may claim `VERIFIED_REPLAY` without the restoration/effect gates in section 5.

## 9. Frozen product surfaces

### CLI

```text
sentinel record -- <agent-command>
sentinel runs
sentinel inspect RUN_ID
sentinel incident RUN_ID --step STEP
sentinel replay RUN_ID --from STEP
sentinel replay RUN_ID --from STEP --policy POLICY
sentinel bisect RUN_ID --predicate PREDICATE
sentinel futures INCIDENT_ID
sentinel policy-search INCIDENT_ID
sentinel capsule RUN_ID
sentinel verify FILE.sentinel
sentinel demo
```

### UI

- Runs
- Incidents
- Incident Workspace
- Provenance and Blast Radius
- Replay Lab
- Alternate Futures
- Policy Search and Pareto Frontier
- Causal World Diff
- Evidence and Verification
- Incident Capsules

### API

- run ingestion and retrieval
- timeline and incident queries
- provenance and blast-radius queries
- replay and divergence operations
- bisection with predicate validation
- policy test and bounded search
- alternate-future exploration
- world-diff retrieval
- evidence verification
- capsule export/import
- live event streaming

## 10. Incident corpus

The public corpus contains at least twelve deterministic scenarios:

1. Credential read
2. Unauthorized egress
3. Secret propagation
4. Harness tampering
5. Log deletion
6. Persistence write
7. Unauthorized tool
8. Agent handoff
9. Environment contamination
10. Uncaptured side effect
11. Unseeded randomness or declared nondeterminism
12. Long benign run with at least 3,000 steps

Each scenario declares ground truth, expected incident predicates, expected dependencies, replay coverage, and allowed divergence.

## 11. Required measurements

- strict replay fidelity
- verified restoration fidelity
- unexpected structural divergence rate
- effect divergence detection accuracy
- provenance precision, recall, and F1
- incident localization distance
- bisection restores versus linear inspection, only where monotonicity is validated
- recording overhead
- logical versus physical snapshot bytes and deduplication ratio
- policy prevention rate
- benign actions blocked per policy
- candidate policies tested and search time
- timeline latency at 3k, 10k, and 50k events

## 12. Mandatory definition of done

`sentinel demo` must produce, without manual repair:

1. A recorded run containing at least 3,000 steps
2. A detected incident
3. A collapsed incident timeline
4. A root-evidence and provenance view
5. A typed blast-radius view
6. A restored and verified pre-incident checkpoint
7. A strict replay of the recorded path
8. At least three evaluated policy candidates
9. At least one supported alternate branch with an explicit replay mode
10. A Pareto-ranked intervention result
11. An original-versus-alternate world diff
12. Verification of the journal and anchored evidence root
13. Capsule export
14. Capsule import and verification
15. Reproduction of the supported replay from the imported capsule
16. A generated metrics report covering the required measurements

The project is not complete if only the UI animation works. The end-to-end evidence path must be executable and tested.

## 13. Explicit non-goals

- universal replay of arbitrary agents
- deterministic replay of arbitrary concurrency
- remote service rollback
- general or arbitrary database rollback outside declared snapshot adapters
- CRIU-based general process continuation
- browser or whole-VM replay
- universal causal inference
- LLM-generated security verdicts presented as ground truth
- a custom policy virtual machine
- a custom telemetry standard
- a custom container engine
- Kubernetes or a microservice fleet for the v1 demo

## 14. Scope control

This charter is frozen.

A change is permitted only when it:

1. fixes a contradiction or incorrect guarantee;
2. preserves the user-visible capability through a simpler implementation;
3. responds to measured evidence from the corpus; or
4. is explicitly approved as a charter revision.

Stages 9-12 are mandatory conformance, security, reliability, performance, clean-room, and release-proof work. They are ordered scope, not calendar weeks, and may not add new headline scope. If the Stage 12 release gate fails, named remediation work continues for as long as required. A date, elapsed week count, or contribution target may never convert simulated or unsupported behavior into a falsely labeled result.

## 15. Current lock

This repository retains only the current governing plan. Historical calendar drafts are not implementation authority. The locked rules are:

- the complete forty-three-section V1 scope remains frozen;
- the sixty slices are ordered scope units with variable duration;
- only accepted evidence advances a slice or stage gate;
- failed release gates create named remediation slices for as long as required;
- changing a product guarantee requires an explicit charter or ADR revision.
