"use client";
import { api } from "@/lib/types";

export interface JobState {
  job_id: string;
  sequence: number;
  state: string;
  kind: string;
  detail: { stage?: string; reason?: string; error_type?: string };
}

export async function executeJob<T>(
  endpoint: string,
  body: unknown,
  onStatus: (value: string) => void,
  signal: AbortSignal,
): Promise<T> {
  const accepted = await api<{ job_id: string }>(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!/^[0-9a-f]{32}$/.test(accepted.job_id))
    throw new Error("Invalid operation identity");
  const statusPath = endpoint.split("?")[0] + "/" + accepted.job_id;
  onStatus("accepted");
  return new Promise<T>((resolve, reject) => {
    const stream = new EventSource(
      "/api/backend/v1/runs" + statusPath + "/events",
    );
    let ended = false;
    const timeout = setTimeout(
      () =>
        finish(
          new Error(
            "Operation result has not been established. Inspect its retained status before retrying.",
          ),
        ),
      610000,
    );
    const aborted = () =>
      finish(
        new DOMException(
          "View closed; operation status remains retained",
          "AbortError",
        ),
      );
    function cleanup() {
      stream.close();
      clearTimeout(timeout);
      signal.removeEventListener("abort", aborted);
    }
    function finish(error?: Error, value?: T) {
      if (ended) return;
      ended = true;
      cleanup();
      if (error) reject(error);
      else resolve(value as T);
    }
    async function inspect(state: string, stage?: string) {
      if (ended) return;
      onStatus(stage ? `${state}: ${stage}` : state);
      if (state === "completed") {
        stream.close();
        try {
          const value = await api<{ report: T }>(statusPath + "/result", {
            signal,
          });
          finish(undefined, value.report);
        } catch (error) {
          finish(error as Error);
        }
      } else if (["failed", "interrupted"].includes(state))
        finish(
          new Error(`Operation ${state}; no successful result is inferred.`),
        );
    }
    stream.addEventListener("operation", (event) => {
      try {
        const value = JSON.parse((event as MessageEvent).data);
        void inspect(value.state, value.body?.stage);
      } catch {
        finish(new Error("Invalid operation status event"));
      }
    });
    stream.onerror = () => {
      void api<JobState>(statusPath, { signal })
        .then((job) => inspect(job.state, job.detail.stage))
        .catch((error) => finish(error));
    };
    signal.addEventListener("abort", aborted, { once: true });
    if (signal.aborted) aborted();
  });
}
