# Sentinel Replay - Student-First Learning Pyramid

Status: **BINDING WORKING METHOD**  
Effective date: **2026-09-17**

Sentinel Replay is both a flagship engineering product and a structured systems-learning program. The project must grow through small, runnable, tested layers. The user must be able to explain and modify each layer before the next layer depends on it.

The objective is not merely to possess a finished repository. The objective is to understand why the system works, where it fails, how its guarantees are tested, and how to defend its design in an engineering interview.

## 1. The pyramid model

```text
                         RELEASE PROOF
                 demo, metrics, capsule, documentation
                              /\
                             /  \
                    PRODUCT EXPERIENCE
               UI, CLI, API, operations, performance
                           /        \
                          /          \
                COUNTERFACTUAL FORENSICS
          policies, alternate futures, world diff, search
                        /              \
                       /                \
                 INCIDENT UNDERSTANDING
          classification, compression, provenance, blast radius
                     /                    \
                    /                      \
              RESTORE AND REPLAY GUARANTEES
        snapshots, effects, replay misses, divergence, bisection
                  /                          \
                 /                            \
             TRUSTWORTHY EVIDENCE FOUNDATION
       schemas, canonicalization, journal, boundaries, storage
```

Every upper layer depends on tested lower-layer invariants. We do not build a polished upper layer over an unproven base.

Every scheduled slice produces or hardens real behavior. Learning notes, diagrams, security analysis, and benchmarks are attached to executable evidence rather than scheduled as isolated paperwork.

## 2. Student-first execution contract

### 2.1 One brick at a time

A normal implementation session advances one task ID from `EXECUTION_PLAN.md`, or a smaller subtask when the concept is substantial. The assistant must not implement multiple stages or hide a large batch of code behind “scaffolding” unless the user explicitly requests that change.

Each brick must be:

- small enough to understand in one sitting;
- runnable independently or through a minimal harness;
- protected by at least one meaningful test;
- observable through a command, output, or state inspection;
- connected explicitly to the brick below it.

### 2.2 Explain before abstraction

For each new mechanism:

1. start with the concrete problem;
2. state the invariant in plain language;
3. show the smallest failure example;
4. write or inspect the failing test;
5. implement the simplest correct behavior;
6. run the test and inspect the produced evidence;
7. only then introduce a reusable abstraction.

Frameworks may reduce boilerplate, but they must not conceal the mechanism being learned. For example, canonical journal hashing is understood and tested before it is wrapped in storage or API layers.

### 2.3 The assistant's role

The assistant may:

- explain concepts and tradeoffs;
- propose the next small slice;
- create focused scaffolding;
- write or pair-write code and tests;
- diagnose failures;
- review the user's implementation;
- show how evidence supports or contradicts a claim.

The assistant must:

- identify every file it changes and why;
- explain non-obvious code paths and invariants;
- avoid unexplained large code generation;
- stop at the current brick's acceptance point;
- give the user a small exercise, modification, or prediction when it materially improves understanding;
- record the session in a lab note and update `STATUS.md`;
- never claim that passing output was observed unless the relevant command actually ran.

### 2.4 The student's role

For every brick, the student should be able to:

- state the problem it solves;
- explain its primary invariant;
- predict at least one failure mode;
- run its tests and demonstration command;
- locate the main implementation and test files;
- make one small modification or add one test;
- explain how the next layer will depend on it.

The student does not need to type every line manually. Understanding, testing, modifying, and defending the design are the required ownership signals.

## 3. The session build-test-learn loop

Every implementation session follows this sequence, including later sessions on a slice that takes more than one session.

### Step A - Recall the base

- Read the active task in `STATUS.md`.
- Re-run the smallest command proving the previous brick still works.
- Answer or review the previous session's teach-back prompts.

### Step B - Learn the concept

- Define the session's problem without framework jargon.
- Explain one concrete failure the system must prevent.
- State the invariant and the evidence that would prove it.

### Step C - Design the smallest slice

- Identify inputs, outputs, failure states, and persisted evidence.
- Name the files to be created or changed.
- Avoid adding components not needed for the current test.

### Step D - Make the failure visible

- Write a failing unit, property, integration, or security test.
- Run it and confirm that it fails for the intended reason.
- Record the failure command and short result in the lab note.

### Step E - Build the brick

- Implement the minimum behavior that satisfies the invariant.
- Keep the code path readable and traceable.
- Add comments only where they explain why, not obvious syntax.

### Step F - Test and inspect

- Run focused tests first.
- Run the current milestone's required regression checks.
- Inspect actual records, hashes, manifests, database rows, API responses, or UI state rather than trusting a green test alone.

### Step G - Modify it once

The student performs or directs one small variation, such as:

- add a corruption case;
- change a schema field;
- add an unsupported input;
- introduce a replay mismatch;
- add a new incident rule;
- alter a policy atom;
- create a new provenance dependency.

This proves the code is understood rather than merely executed.

### Step H - Teach back and record

- Complete the lab note.
- Answer three teach-back prompts.
- Update `STATUS.md` with evidence and the next brick.
- Commit the coherent slice once the repository has been initialized.
- Push its short-lived branch, open a focused pull request, wait for CI, self-review the diff, and merge it into `main` only when the complete slice gate passes.

## 4. Slice definition of done

A slice is `DONE` only when all applicable items are true:

- [ ] The concept is described in plain language.
- [ ] The central invariant is written down.
- [ ] A failure was reproduced or represented by a failing test.
- [ ] The smallest implementation passes the focused test.
- [ ] Relevant regression tests pass.
- [ ] A real output or artifact was inspected.
- [ ] The user can locate the implementation and tests.
- [ ] One small variation or additional test was completed.
- [ ] Three teach-back prompts were recorded.
- [ ] The lab note and `STATUS.md` were updated.
- [ ] The slice is committed with a meaningful message when Git is available.
- [ ] The branch is pushed and its focused pull request is merged into `main` after tests and self-review.

If the implementation works but these learning conditions are missing, the task remains `ACTIVE`.

## 5. Layer-by-layer learning outcomes

## Layer 1 - Trustworthy evidence foundation

Schedule: Stages 1-2

Builds:

- versioned schemas;
- canonical serialization and domain-separated hashing;
- hash-chained journal;
- boundary recording and replay matching;
- content-addressed blob storage;
- normalized event ingestion;
- deterministic incident rules and first timeline.

The student will learn:

- why ordinary JSON is not automatically canonical;
- how a hash chain detects history modification and what it cannot prove alone;
- why request digest alone is insufficient for repeated-call replay;
- the difference between an event log, trace, recording, and effect receipt;
- how database constraints encode system invariants;
- why OTel enriches but does not replace replay evidence.

Layer gate teach-back:

1. Explain how Sentinel knows which recorded response belongs to a replayed call.
2. Demonstrate three different journal corruptions and how verification detects them.
3. Explain why a valid local hash chain is not yet externally trustworthy.
4. Trace one recorded agent action from adapter to journal, blob, normalized step, API, and timeline.

## Layer 2 - Restore and replay guarantees

Schedule: Stage 3 and Slices 16-17

Builds:

- environment-pack contract;
- content-addressed filesystem checkpoints;
- safe verified restore;
- declared Git-state restoration;
- effect receipts and adapters;
- strict replay;
- structural and effect divergence;
- predicate-aware bisection.

The student will learn:

- overlayfs upper-layer semantics and whiteouts;
- path traversal, symlink races, and descriptor-relative file operations;
- content addressing and deduplication;
- why restoration and replay are separate guarantees;
- why returning a recorded tool response does not reproduce its side effect;
- why binary search requires a monotone predicate.

Layer gate teach-back:

1. Restore a checkpoint and independently verify its covered paths.
2. Explain one state class that is replayed, one that is restored, and one that is unsupported.
3. Inject structural and effect divergence and explain why they are different.
4. Show a predicate where bisection is valid and one where it is not.

## Layer 3 - Incident understanding

Schedule: Slices 18-20

Builds:

- typed carrier extraction;
- redacted and fingerprinted sensitive data lineage;
- typed provenance graph;
- root-evidence queries;
- blast-radius reachability;
- provenance evaluation against ground truth.

The student will learn:

- chronology versus dependency versus causality;
- precision, recall, F1, and graph overreach;
- why sequential fallback edges cannot imply contamination;
- how sensitive carriers can be correlated without exposing their raw values;
- how OTel parentage differs from data lineage.

Layer gate teach-back:

1. Explain every edge type and whether it contributes to blast radius.
2. Add one known dependency and show that the graph recovers it.
3. Add one tempting false dependency and show how filtering prevents it.
4. Interpret the provenance precision and recall report.

## Layer 4 - Counterfactual policy engineering

Schedule: Stage 5

Builds:

- OPA decision boundary;
- finite Sentinel policy grammar;
- trace-level policy evaluation;
- bounded candidate search;
- Pareto frontier;
- deterministic and exploratory alternate futures;
- world-diff engine.

The student will learn:

- policy decision versus policy enforcement;
- finite search spaces and combinatorial growth;
- multi-objective optimization and nondominance;
- why a blocked historical action does not determine adaptive future behavior;
- the boundary between verified replay, deterministic simulation, and exploratory branching;
- how to compare structural, effect, state, and outcome differences.

Layer gate teach-back:

1. Compile one Sentinel policy atom into Rego and explain the decision input.
2. Show why “least disruptive” depends on the corpus and cost vector.
3. Run the same deterministic branch twice and compare the evidence.
4. Identify the exact point where a branch stops being verified replay.

## Layer 5 - Product and portable proof

Schedule: Stage 6

Builds:

- versioned incident capsule;
- export, import, and offline verification;
- complete CLI/API/UI workflow;
- public homepage;
- one-command executable demonstration;
- first full metrics report and video.

The student will learn:

- portable artifact design and schema evolution;
- archive security and offline verification;
- the difference between a convincing UI and a proved system path;
- how to turn backend guarantees into understandable product language;
- how to design a deterministic demonstration without faking behavior.

Layer gate teach-back:

1. Verify a capsule without trusting its source database.
2. Trace the complete demo from recording to imported replay.
3. Point to the evidence supporting every guarantee shown in the UI.
4. Explain the product in 30 seconds and the conformance limits in two minutes.

## Layer 6 - Engineering maturity

Schedule: Stages 7-8

Builds:

- full twelve-scenario corpus;
- real coding-agent adapter;
- evidence signatures and privacy controls;
- authorization and security tests;
- performance benchmarks and operational recovery;
- clean-room installation, final documentation, and release proof.

The student will learn:

- ground-truth corpus design and regression thresholds;
- adapter design across controlled and real agents;
- threat modeling and residual risk;
- performance measurement without misleading benchmarks;
- reliability, idempotency, recovery, and retention;
- how to audit claims against evidence before release.

Layer gate teach-back:

1. Defend the threat model and name the largest residual risk.
2. Reproduce one benchmark from its raw command and artifact.
3. Install and demonstrate Sentinel from a clean environment.
4. Explain what the project deliberately does not guarantee.

## 6. How an implementation session should feel

A healthy session is narrow and concrete. Example for journal chaining:

1. Explain why editable chronological JSONL is insufficient.
2. Create two journal records manually and compute the second record's dependency on the first.
3. Write a test that mutates record one.
4. Observe that the unimplemented verifier misses or cannot process it.
5. Implement append and verification.
6. Run the test and inspect the actual JSONL.
7. Add a deletion or reordering case.
8. Explain why an attacker controlling the whole file could recompute the chain.
9. Record the result and stop.

An unhealthy session would generate the journal, recorder, database, API, UI, and deployment together, report that tests pass, and leave the student unable to trace one record.

## 7. Learning artifacts

Each completed task creates a lab note at:

```text
docs/learning/SNN-short-name.md
```

Use `docs/learning/LAB_NOTE_TEMPLATE.md`.

Diagrams, raw sample outputs, or small experiments belong beside the lab note when useful. Generated benchmark reports remain under `benchmarks/reports/` and are linked from the note rather than copied manually.

## 8. Interview readiness checkpoints

At the end of every layer, the user should be able to answer:

- What problem did this layer solve?
- What invariant makes it trustworthy?
- What is the most important failure mode?
- Which test proves the failure is handled?
- What is outside the guarantee?
- What tradeoff did we choose and what alternative did we reject?

If these answers are unclear, we review or rebuild the weak brick before adding another layer.

## 9. Pace and recovery

The plan has no fixed duration. Learning and evidence are never removed to preserve a date. When a concept takes longer:

1. keep the brick small;
2. continue the same slice rather than replacing it with busywork;
3. reduce incidental polish or boilerplate;
4. never skip the invariant, test, inspection, or teach-back;
5. never replace understanding with a large unexplained code generation pass;
6. continue for as many sessions as the slice and its gate genuinely require.

The pyramid succeeds when both the product and the student's engineering judgment become progressively stronger.
