"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/types";
import { executeJob, type JobState } from "@/lib/operations";

export default function OperationConsole({ endpoint }: { endpoint: string }) {
  const [jobs, setJobs] = useState<JobState[]>([]),
    [status, setStatus] = useState("");
  const [path, setPath] = useState("egress.txt"),
    [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null),
    [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const base = endpoint.split("?")[0];
  function refresh() {
    void api<{ jobs: JobState[] }>(base)
      .then((value) => setJobs(value.jobs))
      .catch((failure) => setError(failure.message));
  }
  useEffect(() => {
    refresh();
    return () => pending.current?.abort();
  }, [base]);
  async function run(kind: "bisect" | "policy_search") {
    setBusy(true);
    setError("");
    setResult(null);
    const controller = new AbortController();
    pending.current = controller;
    try {
      const body =
        kind === "bisect"
          ? {
              kind,
              predicate: { kind: "file_exists", path },
              measure_linear: false,
            }
          : { kind, max_candidates: 128, time_budget_seconds: 600 };
      const report = await executeJob<Record<string, unknown>>(
        endpoint,
        body,
        setStatus,
        controller.signal,
      );
      const view =
        kind === "bisect"
          ? {
              mode: report.mode,
              first_true_prefix: report.first_true_prefix,
              binary_restores: report.binary_restores,
              linear_restores: report.linear_restores,
              monotonicity: report.monotonicity,
            }
          : {
              scope: report.scope,
              evaluated_candidates: (report.scores as unknown[])?.length,
              partial: report.partial,
              frontier_points: (report.frontier as unknown[])?.length,
              recommended: report.recommended,
            };
      setResult(view);
      refresh();
    } catch (failure) {
      if ((failure as Error).name !== "AbortError")
        setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Bounded forensic operations">
      <h3>Localize the first matching state.</h3>
      <p className="muted">
        Bisection restores and verifies each tested prefix. Binary search
        requires a proven monotone file predicate; other cases use the bounded
        linear fallback.
      </p>
      <label>
        File existence predicate{" "}
        <input
          aria-label="Predicate file basename"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          maxLength={64}
        />
      </label>{" "}
      <Button disabled={busy} onClick={() => void run("bisect")}>
        Localize file creation
      </Button>
      <h3>Search the fixed regression corpus.</h3>
      <p className="muted">
        Evaluate the frozen twelve-case synthetic corpus, with a 1,000-candidate
        / ten-minute ceiling. This tests that catalog, rather than inferring a
        predicate for your imported run. Only executed candidates can enter the
        frontier.
      </p>
      <Button disabled={busy} onClick={() => void run("policy_search")}>
        Run bounded corpus search
      </Button>
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
      <h3>Retained operation history</h3>
      <Button variant="ghost" onClick={refresh}>
        Refresh operation status
      </Button>
      {jobs.map((job) => (
        <p key={job.job_id}>
          <code>{job.job_id.slice(0, 10)}</code> · {job.kind} · {job.state}
          {job.state === "completed" && (
            <Button
              variant="ghost"
              onClick={() => {
                void api<{ report: Record<string, unknown> }>(
                  `${base}/${job.job_id}/result`,
                )
                  .then((value) => {
                    setResult(value.report);
                    setError("");
                  })
                  .catch((failure) => setError(failure.message));
              }}
            >
              Inspect retained result
            </Button>
          )}
        </p>
      ))}
    </section>
  );
}
