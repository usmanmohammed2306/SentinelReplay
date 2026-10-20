# ADR-0001: Replay and Counterfactual Modes

Status: **Accepted**  
Date: **2026-09-17**

## Context

Changing a policy can change an agent action, its resulting observation, the next model request, and every subsequent effect. A request produced after that divergence may not exist in the original recording. Returning live data while continuing to call the result deterministic replay would violate Sentinel's fail-closed guarantee.

Sentinel therefore treats verified history, trace-level policy decisions, deterministic simulations, and newly generated branches as different evidence classes.

## Decision

Every replay or counterfactual result has exactly one mode.

### `VERIFIED_REPLAY`

- Restores a verified covered checkpoint.
- Uses only matched recorded nondeterministic inputs and declared effect adapters.
- Fails closed on the first missing, exhausted, out-of-order, or mismatched recording.
- May claim exactness only within the published conformance ladder.

### `TRACE_POLICY_EVALUATION`

- Applies a candidate policy to action inputs from an existing trace.
- Answers whether the policy would allow, deny, or escalate those recorded actions.
- Does not claim to know how the agent would behave after a blocked action.
- Benign disruption means interference with the declared recorded regression corpus.

### `DETERMINISTIC_SIMULATION`

- Runs from a verified fork point inside a versioned deterministic environment pack.
- May produce a different future after policy intervention.
- Is reproducible under the declared environment, model/stub, scheduler, and adapter contract.
- Must not be generalized to unsupported live agents or external systems.

### `EXPLORATORY_BRANCH`

- Starts from a verified fork point and invokes a live or newly sampled model or unsupported external component after divergence.
- Records the result as a new child run.
- Is useful evidence about one possible future, not the future that would have occurred.
- Must display model identity, sampling parameters, environment digest, policy digest, and uncertainty label.

## Required transition behavior

A branch may begin as `VERIFIED_REPLAY`. At the first policy-induced or unexpected structural divergence it must:

1. stop with a divergence report; or
2. transition explicitly to `DETERMINISTIC_SIMULATION`; or
3. transition explicitly to `EXPLORATORY_BRANCH` and create a new recorded child run.

The UI must display the transition boundary. APIs and exported capsules must preserve it.

## Consequences

- Sentinel can retain a strict fail-closed replay guarantee.
- Alternate Futures remains a headline capability without misrepresenting generated continuations.
- Minimal Intervention Search can combine trace policy evaluation with stronger deterministic simulation where supported.
- Comparisons across exploratory branches require repeated trials or uncertainty reporting and cannot be presented as exact counterfactual truth.
