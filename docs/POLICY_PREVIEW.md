# OPA policy enforcement preview

The first Sentinel policy boundary accepts a small, versioned policy, compiles it to Rego, and asks Open Policy Agent for a boolean decision before a protected effect runs. It is deliberately narrow: exact tool names, exact outbound hosts, and deny precedence. It does not yet intercept a real coding agent or implement the full V1 policy grammar.

`PolicySpec` permits sorted, unique allow and deny lists. An action names one tool; `http_post` also requires a host. A tool must appear in `allow_tools` to run. An outbound post additionally needs a host in `allow_hosts`. A matching deny entry overrides an allow entry. Missing fields, unsupported atoms, an unavailable engine, and non-boolean engine output never authorize the effect.

The compiler is in [`policy.py`](../src/sentinel_replay/policy.py). `compile_rego` emits a `default allow := false` rule; `OpaEvaluator` invokes a configured OPA executable with a three-second default timeout; `enforce` calls the effect only after an explicit allow. The [MCP gateway](MCP_GATEWAY.md) now routes one real-agent tool through this policy before its bounded copy effect. A caller that uses Codex's native shell or another tool bypasses this preview boundary; there is no general agent interception yet.

Run `make check` for schema and fail-closed unit tests. Run `make opa-contract` with Docker available to compare five decisions and a denied/allowed MCP tool pair against a digest-pinned OPA 1.0.0 image with networking disabled. The [CI workflow](../.github/workflows/ci.yml) is configured to repeat that contract; it remains unverified on GitHub until the repository is pushed. These tests prove only the declared gateway path, not that every real agent action is intercepted.

To learn the boundary, add one allowed tool and one denied host. Predict both decisions before running `make opa-contract`. Then make the OPA executable unavailable in a unit test and prove the effect callback was not called. Finally, explain why a trace-scored policy cannot establish what an adaptive agent would do after its first blocked action. The [official Rego language guide](https://www.openpolicyagent.org/docs/policy-language) and [OPA CLI reference](https://www.openpolicyagent.org/docs/cli) are the references for extending this preview.

Do not describe this as complete policy enforcement until a real coding-agent adapter routes every covered action through the gate, produces decision evidence, and passes default-deny, unavailable-engine, benign-regression, and bypass tests.
