"use client";
import { useState, useEffect, useRef } from "react";
import Editor, { loader } from "@monaco-editor/react";
import { Button } from "@/components/ui/button";
import { executeJob } from "@/lib/operations";
loader.config({ paths: { vs: "/monaco/vs" } });
const INITIAL = JSON.stringify(
  {
    schema_version: 2,
    rules: [
      { effect: "allow", operation: "*" },
      { effect: "deny", operation: "http_post" },
    ],
  },
  null,
  2,
);

export default function FutureEditor({ endpoint }: { endpoint: string }) {
  const [policy, setPolicy] = useState(INITIAL),
    [fork, setFork] = useState(0);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [result, setResult] = useState<null | {
    mode: string;
    status: string;
    future_id: string;
    first_policy_decision_divergence: number | null;
    world_diff: { path: string }[];
    incidents: unknown[];
  }>(null);
  const [status, setStatus] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      if (policy.length > 32768)
        throw new Error("Policy exceeds the editor's byte budget");
      const body = {
        kind: "fork",
        policy: JSON.parse(policy),
        fork_step: fork,
      };
      const controller = new AbortController();
      pending.current = controller;
      setResult(
        await executeJob<NonNullable<typeof result>>(
          endpoint,
          body,
          setStatus,
          controller.signal,
        ),
      );
    } catch (failure) {
      if ((failure as Error).name !== "AbortError")
        setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Alternate future policy editor">
      <h3>What would this policy change?</h3>
      <p className="muted">
        Restore the verified checkpoint, match the recorded prefix, then
        re-execute the finite program under OPA. Model, process and network
        actions remain declared simulations. Every returned future was executed.
      </p>
      <label>
        Fork at program step{" "}
        <input
          aria-label="Fork program step"
          type="number"
          min={0}
          max={50000}
          value={fork}
          onChange={(event) => setFork(Number(event.target.value))}
        />
      </label>
      <Editor
        height="300px"
        language="json"
        theme="vs-dark"
        value={policy}
        onChange={(value) => setPolicy(value ?? "")}
        options={{
          readOnly: busy,
          minimap: { enabled: false },
          automaticLayout: true,
          scrollBeyondLastLine: false,
          fontSize: 13,
        }}
      />
      <Button disabled={busy} onClick={() => void run()}>
        {busy ? "Restoring and evaluating…" : "Evaluate alternate future"}
      </Button>
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
      {result && (
        <div className="result-panel" role="status">
          <div>
            <h3>{result.mode}</h3>
            <p>
              Execution: {result.status}. {result.incidents.length} declared
              evidence findings.
            </p>
            <p>
              First changed policy decision:{" "}
              {result.first_policy_decision_divergence ?? "none"}.
            </p>
            <p>
              Changed covered paths:{" "}
              {result.world_diff.map((row) => row.path).join(", ") || "none"}.
            </p>
            <p>Future evidence retained with this operation.</p>
          </div>
        </div>
      )}
    </section>
  );
}
