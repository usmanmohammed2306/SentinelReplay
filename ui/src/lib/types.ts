export interface Run {
  run_id: string;
  journal_root: string;
  records: number;
  capsule_size: number;
  signer_key_id: string;
}
export interface Summary {
  run_id: string;
  record_type: "branch" | "experiment" | "environment_pack";
  records: number;
  mode: string;
  terminal_status: string;
  journal_root: string;
  artifacts: number;
  storage_encrypted: boolean;
  signer_status: string;
  detached_statement_retained: boolean;
  outcomes: {
    legitimate_task_completed: boolean | null;
    protected_output_count: number | null;
  };
}
export interface Boundary {
  step: number;
  call_id: string;
  kind: string;
  operation: string;
  sensitivity: string;
  coverage: string;
  request_digest: string | null;
}
export interface Timeline {
  journal_root: string;
  total: number;
  offset: number;
  next_offset: number | null;
  events: Boundary[];
}
export interface Incident {
  incident_id: string;
  title: string;
  rule_id: string;
  root_step: number;
  step: number;
  severity: string;
  basis: string;
}
export interface Graph {
  root_step: number;
  total_nodes: number;
  nodes: Boundary[];
  edges: { source: number; target: number; kind: string; rationale: string }[];
  blast_radius: number[];
  blast_radius_complete: boolean;
  limitation: string;
}
export interface Comparison {
  mode: string;
  scenarios: number;
  branches: {
    scenario: string;
    arm: string;
    status: string;
    legitimate_task_completed: boolean | null;
    protected_outputs: string[] | null;
    journal_root: string;
    policy_digest: string;
    branch_index: number;
    policy: Record<string, unknown>;
    rego: string;
  }[];
  scores: {
    arm: string;
    task_completions: number;
    task_denominator: number;
    protected_exposures: number;
    unknown: number;
    task_disruption: number;
    rule_complexity: number;
  }[];
  frontier: string[];
  world_diffs: {
    scenario: string;
    alternate_arm: string;
    changes: { workspace: string[] | null; fixture: string[] | null };
  }[];
  limitation: string;
  selection_rule: string;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let result: Response | undefined;
  for (let attempt = 0; attempt < 5; attempt++) {
    result = await fetch("/api/backend/v1/runs" + path, {
      ...options,
      cache: "no-store",
    });
    if (result.status !== 429 || attempt === 4) break;
    const retryAfter = Number(result.headers.get("Retry-After"));
    const delay =
      Number.isFinite(retryAfter) && retryAfter > 0
        ? Math.max(250, Math.min(2000, retryAfter * 1000))
        : Math.min(2000, 250 * 2 ** attempt);
    await result.body?.cancel();
    await new Promise((resolve) => setTimeout(resolve, delay));
    if (options?.signal?.aborted)
      throw new DOMException("Request aborted", "AbortError");
  }
  if (!result) throw new Error("Evidence request did not start");
  if (!result.ok) {
    const error = await result.json().catch(() => ({}));
    throw new Error(
      error.detail ?? `Evidence request failed (${result.status})`,
    );
  }
  return result.json() as Promise<T>;
}
