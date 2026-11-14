"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import { useVirtualizer } from "@tanstack/react-virtual";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Boxes,
  Check,
  ChevronRight,
  CircleDot,
  FileCheck2,
  Fingerprint,
  GitBranch,
  Layers3,
  Loader2,
  LockKeyhole,
  LogOut,
  Network,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  SquareTerminal,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  api,
  type Boundary,
  type Comparison,
  type Graph,
  type Incident,
  type Run,
  type Summary,
  type Timeline,
} from "@/lib/types";

const Provenance = dynamic(() => import("@/components/provenance"), {
  ssr: false,
});
const PolicyChart = dynamic(() => import("@/components/policy-chart"), {
  ssr: false,
});
const tabs = [
  { id: "timeline", label: "Timeline", icon: Activity },
  { id: "graph", label: "Provenance", icon: Network },
  { id: "replay", label: "Replay lab", icon: Play },
  { id: "policies", label: "Policies & futures", icon: GitBranch },
  { id: "diff", label: "World diff", icon: Layers3 },
  { id: "evidence", label: "Evidence", icon: Fingerprint },
];
const short = (value: string) => value.replace("sha256:", "").slice(0, 12);
const PolicySource = dynamic(() => import("@/components/policy-source"), {
  ssr: false,
});

const FutureEditor = dynamic(() => import("@/components/future-editor"), {
  ssr: false,
});

const OperationConsole = dynamic(
  () => import("@/components/operation-console"),
  { ssr: false },
);

const words = (value: string) => value.replaceAll("_", " ");

export default function Workspace() {
  const [runs, setRuns] = useState<Run[]>([]),
    [selected, setSelected] = useState<string>("");
  const [branch, setBranch] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [authenticated, setAuthenticated] = useState(false),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState(""),
    [token, setToken] = useState(""),
    [search, setSearch] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null),
    [timeline, setTimeline] = useState<Timeline | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]),
    [graph, setGraph] = useState<Graph | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null),
    [tab, setTab] = useState("timeline");
  const [focused, setFocused] = useState<Boundary | null>(null),
    [root, setRoot] = useState(0);
  const [replay, setReplay] = useState<Record<string, unknown> | null>(null),
    [busy, setBusy] = useState(false);
  const [verification, setVerification] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [phases, setPhases] = useState<
    {
      label: string;
      first_step: number;
      last_step: number;
      actions: number;
      finding_count: number;
    }[]
  >([]);
  const [telemetry, setTelemetry] = useState<Record<string, unknown> | null>(
    null,
  );
  const scroller = useRef<HTMLDivElement>(null);
  const rows = timeline?.events ?? [];
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 59,
    overscan: 8,
  });

  function evidencePath(path: string) {
    return `/${selected}/${path}${branch === null ? "" : (path.includes("?") ? "&" : "?") + `branch=${branch}`}`;
  }
  async function loadRuns() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ runs: Run[]; next_cursor: string | null }>(
        "?limit=100",
      );
      setRuns(data.runs);
      setNextCursor(data.next_cursor);
      setAuthenticated(true);
      setSelected(
        (previous) =>
          previous ||
          data.runs.find((run) => run.run_id.startsWith("branch-"))?.run_id ||
          data.runs[0]?.run_id ||
          "",
      );
    } catch (failure) {
      setError((failure as Error).message);
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  }
  async function loadMoreRuns() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await api<{ runs: Run[]; next_cursor: string | null }>(
        `?limit=100&after=${encodeURIComponent(nextCursor)}`,
      );
      setRuns((previous) => [
        ...new Map(
          [...previous, ...data.runs].map((run) => [run.run_id, run]),
        ).values(),
      ]);
      setNextCursor(data.next_cursor);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }
  useEffect(() => {
    void loadRuns();
  }, []);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    setSummary(null);
    setPhases([]);
    setTelemetry(null);
    setTimeline(null);
    setIncidents([]);
    setGraph(null);
    setComparison(null);
    setReplay(null);
    setVerification(null);
    setFocused(null);
    setRoot(0);
    setError("");
    void (async () => {
      try {
        const data = await api<Summary>(evidencePath("investigation"));
        if (!active) return;
        setSummary(data);
        if (data.record_type === "experiment") {
          const compared = await api<Comparison>(`/${selected}/comparison`);
          if (active) {
            setComparison(compared);
            setTab("policies");
          }
        } else {
          const [events, findings] = await Promise.all([
            api<Timeline>(evidencePath("timeline?limit=500")),
            api<{ incidents: Incident[] }>(evidencePath("incidents")),
          ]);
          if (active) {
            setTimeline(events);
            setIncidents(findings.incidents);
            setFocused(events.events[0] ?? null);
            setRoot(findings.incidents[0]?.root_step ?? 0);
            setTab("timeline");
          }
          const [compressed, compared] = await Promise.all([
            api<{ phases: typeof phases }>(evidencePath("phases")),
            data.record_type === "environment_pack"
              ? api<Comparison>(`/${selected}/comparison`).catch(() => null)
              : Promise.resolve(null),
          ]);
          if (active) {
            setPhases(compressed.phases);
            setComparison(compared);
          }
        }
      } catch (failure) {
        if (active) setError((failure as Error).message);
      }
    })();
    return () => {
      active = false;
    };
  }, [selected, branch]);
  useEffect(() => {
    if (
      tab !== "graph" ||
      !selected ||
      !summary ||
      summary.record_type === "experiment"
    )
      return;
    let active = true;
    void api<Graph>(evidencePath(`provenance?root_step=${root}&depth=3`))
      .then((value) => {
        if (active) setGraph(value);
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      });
    return () => {
      active = false;
    };
  }, [tab, selected, branch, root, summary]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!result.ok) throw new Error((await result.json()).detail);
      setToken("");
      await loadRuns();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function runReplay() {
    setBusy(true);
    setError("");
    try {
      setReplay(
        await api<Record<string, unknown>>(evidencePath("replay"), {
          method: "POST",
        }),
      );
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download(kind: "capsule" | "attestation" = "capsule") {
    const result = await fetch(
      `/api/backend/v1/runs/${selected}/${kind}${kind === "capsule" && summary?.storage_encrypted ? "?sealed=true" : ""}`,
    );
    if (!result.ok) {
      setError("Capsule export denied or unavailable");
      return;
    }
    const url = URL.createObjectURL(await result.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download =
      selected +
      (kind === "attestation"
        ? ".sentinel.sig.json"
        : summary?.storage_encrypted
          ? ".sentinel.enc"
          : ".sentinel");
    link.click();
    URL.revokeObjectURL(url);
  }
  async function nextPage() {
    if (!timeline || timeline.next_offset === null) return;
    try {
      const next = await api<Timeline>(
        evidencePath(
          `timeline?offset=${timeline.next_offset}&limit=500&root=${timeline.journal_root}`,
        ),
      );
      setTimeline((previous) =>
        previous
          ? { ...next, events: [...previous.events, ...next.events] }
          : next,
      );
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  if (!authenticated)
    return (
      <main className="login-shell">
        <div className="login-grid" />
        <motion.section
          className="login-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="brand">
            <span className="brand-mark">
              <Boxes size={22} />
            </span>{" "}
            SENTINEL<span className="brand-light"> / REPLAY</span>
          </div>
          <div className="eyebrow">COUNTERFACTUAL INCIDENT FORENSICS</div>
          <h1>
            The trace ends.
            <br />
            <span>The investigation begins.</span>
          </h1>
          <p>
            Follow the evidence from an agent action to its effect. Restore
            covered state. Compare what the tested alternatives changed.
          </p>
          <form onSubmit={login}>
            <label htmlFor="access-token">
              <LockKeyhole size={14} /> Investigator access token
            </label>
            <input
              id="access-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              required
              minLength={32}
              placeholder="Enter your local access token"
            />
            <Button disabled={busy || loading} type="submit">
              {busy || loading ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}{" "}
              Open investigation
            </Button>
          </form>
          {error && !loading && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          <div className="login-foot">
            <span className="status-dot" /> Local evidence workspace{" "}
            <span>01 / SENTINEL</span>
          </div>
        </motion.section>
      </main>
    );

  const filtered = runs.filter((run) =>
    run.run_id.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Boxes size={19} />
          </span>
          <div>
            SENTINEL<small>REPLAY / INVESTIGATIONS</small>
          </div>
        </div>
        <div className="workspace-chip">
          <span className="status-dot" /> Local workspace{" "}
          <span>V1 · DEVELOPMENT</span>
        </div>
        <div className="sidebar-label">
          EVIDENCE LIBRARY <span>{runs.length}</span>
        </div>
        <label className="search">
          <Search size={14} />
          <input
            aria-label="Filter runs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a run…"
          />
        </label>
        <nav className="run-list" aria-label="Recorded runs">
          {filtered.map((run) => (
            <button
              key={run.run_id}
              data-run-id={run.run_id}
              className={
                selected === run.run_id ? "run-item selected" : "run-item"
              }
              onClick={() => {
                setBranch(null);
                setSelected(run.run_id);
              }}
            >
              <span className="run-icon">
                {run.run_id.startsWith("experiment-") ? (
                  <GitBranch size={16} />
                ) : (
                  <SquareTerminal size={16} />
                )}
              </span>
              <span>
                <strong>
                  {run.run_id.startsWith("experiment-")
                    ? "Policy comparison"
                    : run.run_id.startsWith("pack-")
                      ? "Environment pack"
                      : "Agent branch"}
                </strong>
                <small>
                  {short(run.journal_root)} · {run.records} events
                </small>
              </span>
              <ChevronRight size={13} />
            </button>
          ))}
        </nav>
        {nextCursor && (
          <Button
            variant="ghost"
            disabled={loadingMore}
            onClick={() => void loadMoreRuns()}
          >
            {loadingMore ? "Loading evidence…" : "Load more runs"}
          </Button>
        )}
        <div className="sidebar-bottom">
          <p>
            <ShieldCheck size={16} /> Evidence before conclusions.
          </p>
          <button
            onClick={() => {
              void fetch("/api/session", { method: "DELETE" }).then(() => {
                setAuthenticated(false);
                setRuns([]);
                setSelected("");
              });
            }}
          >
            <LogOut size={14} /> Lock workspace
          </button>
        </div>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <span>
            Investigations <ChevronRight size={13} />{" "}
            {branch !== null && (
              <Button variant="outline" onClick={() => setBranch(null)}>
                Back to comparison
              </Button>
            )}
            {summary?.record_type === "experiment"
              ? "Policy comparison"
              : "Agent execution"}
          </span>
          <div>
            <span className="status-dot" /> LOCAL{" "}
            <button
              aria-label="Refresh evidence"
              onClick={() => {
                void loadRuns();
              }}
            >
              <RefreshCw size={15} />
            </button>
          </div>
        </header>
        <div className="page-body">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="page-heading"
          >
            <div>
              <div className="eyebrow">AGENT INCIDENT FORENSICS</div>
              <h1>
                {summary?.record_type === "experiment"
                  ? "One checkpoint. Three policies."
                  : "Follow the evidence."}
              </h1>
              <p>
                {summary?.record_type === "experiment"
                  ? "Compare executed outcomes, useful work and the cost of intervention."
                  : "Reconstruct the covered path. Keep every unsupported boundary visible."}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                void download();
              }}
              disabled={!summary}
            >
              <ArrowDownToLine size={15} /> Export capsule
            </Button>
          </motion.div>
          {error && (
            <div className="error-banner" role="alert">
              <TriangleAlert size={16} />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                ×
              </button>
            </div>
          )}
          {!runs.length && (
            <section className="empty-state">
              <FileCheck2 size={32} />
              <h2>No evidence imported yet</h2>
              <p>
                Import a signed incident capsule through the API to begin. This
                workspace does not invent demonstration results.
              </p>
            </section>
          )}
          {selected && !summary && !error && (
            <div className="loading-state">
              <Loader2 size={20} className="spin" /> Verifying stored evidence…
            </div>
          )}
          {summary && (
            <>
              <section className="metrics" aria-label="Run evidence summary">
                <Metric
                  label="RECORDED BOUNDARIES"
                  value={String(summary.records)}
                  note="Hash chain checked"
                  icon={<Activity size={16} />}
                />
                <Metric
                  label="EVIDENCE ARTIFACTS"
                  value={String(summary.artifacts)}
                  note="Digest-verified members"
                  icon={<FileCheck2 size={16} />}
                />
                <Metric
                  label="EXECUTION MODE"
                  value={comparison?.mode ?? summary.mode}
                  note="Coverage stays explicit"
                  small
                  icon={<GitBranch size={16} />}
                />
                <Metric
                  label="EVIDENCE ROOT"
                  value={short(summary.journal_root)}
                  note="SHA-256 · content bound"
                  small
                  icon={<Fingerprint size={16} />}
                />
              </section>
              <section className="investigation-card">
                <div className="card-toolbar">
                  <div>
                    <span className="status-dot" />
                    <strong>
                      {summary.record_type === "experiment"
                        ? "Executed policy comparison"
                        : "Recorded agent branch"}
                    </strong>
                    <span className="pill">INTEGRITY CHECKED</span>
                  </div>
                  <code title={summary.run_id}>
                    {summary.run_id.slice(0, 25)}…
                  </code>
                </div>
                <nav className="tabs" aria-label="Investigation views">
                  {tabs.map((item) => (
                    <button
                      key={item.id}
                      className={tab === item.id ? "active" : ""}
                      onClick={() => setTab(item.id)}
                    >
                      <item.icon size={15} />
                      {item.label}
                    </button>
                  ))}
                </nav>
                {tab === "timeline" && (
                  <div className="split-view">
                    <section className="timeline-section">
                      <div className="section-heading">
                        <div>
                          <span className="eyebrow">ACTION SEQUENCE</span>
                          <h2>Every step has a boundary.</h2>
                        </div>
                        <span className="muted">
                          {timeline?.total ?? 0} events
                        </span>
                      </div>
                      {!timeline && (
                        <p className="empty-note">
                          Select an individual branch to inspect its timeline.
                        </p>
                      )}
                      {phases.length > 0 && (
                        <details className="phase-navigator">
                          <summary>
                            {phases.length} compressed phases ·{" "}
                            {summary.records} boundaries
                          </summary>
                          {phases.map((phase) => (
                            <button
                              key={phase.first_step}
                              onClick={() => {
                                void api<Timeline>(
                                  evidencePath(
                                    `timeline?offset=${phase.first_step}&limit=500&root=${summary.journal_root}`,
                                  ),
                                )
                                  .then((value) => {
                                    setTimeline(value);
                                    setFocused(value.events[0] ?? null);
                                  })
                                  .catch((failure) =>
                                    setError(failure.message),
                                  );
                              }}
                            >
                              {words(phase.label)}{" "}
                              <small>
                                {phase.first_step}–{phase.last_step} ·{" "}
                                {phase.actions} actions
                              </small>
                            </button>
                          ))}
                        </details>
                      )}
                      {incidents.map((finding) => (
                        <button
                          key={finding.incident_id}
                          className="incident-note"
                          onClick={() => {
                            setRoot(finding.root_step);
                            setTab("graph");
                          }}
                        >
                          <TriangleAlert size={16} />
                          <span>
                            <strong>
                              {finding.title ?? words(finding.rule_id)}
                            </strong>
                            <small>
                              Declared source {finding.root_step} → effect{" "}
                              {finding.step}
                            </small>
                          </span>
                          <ArrowRight size={15} />
                        </button>
                      ))}
                      <div className="timeline-head">
                        <span>STEP</span>
                        <span>BOUNDARY</span>
                        <span>COVERAGE</span>
                      </div>
                      <div
                        ref={scroller}
                        className="timeline-scroll"
                        aria-label="Boundary timeline"
                      >
                        <div
                          style={{
                            height: virtual.getTotalSize(),
                            width: "100%",
                            position: "relative",
                          }}
                        >
                          {virtual.getVirtualItems().map((item) => {
                            const row = rows[item.index];
                            return (
                              <button
                                key={row.step}
                                className={
                                  focused?.step === row.step
                                    ? "event-row focused"
                                    : "event-row"
                                }
                                style={{
                                  position: "absolute",
                                  top: 0,
                                  transform: `translateY(${item.start}px)`,
                                  width: "100%",
                                  height: item.size,
                                }}
                                onClick={() => setFocused(row)}
                              >
                                <code>{String(row.step).padStart(3, "0")}</code>
                                <span>
                                  <strong>{words(row.operation)}</strong>
                                  <small>{row.call_id}</small>
                                </span>
                                <span
                                  className={
                                    row.sensitivity === "secret"
                                      ? "event-tag sensitive"
                                      : "event-tag"
                                  }
                                >
                                  {row.sensitivity === "secret"
                                    ? "sensitive source"
                                    : row.coverage ===
                                        "workspace_container_only"
                                      ? "contained"
                                      : "declared"}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                      {timeline?.next_offset !== null &&
                        timeline?.next_offset !== undefined && (
                          <Button
                            variant="ghost"
                            onClick={() => {
                              void nextPage();
                            }}
                          >
                            Load next 500 boundaries
                          </Button>
                        )}
                    </section>
                    <aside className="detail-panel">
                      <div className="eyebrow">BOUNDARY INSPECTOR</div>
                      {focused ? (
                        <>
                          <h2>{words(focused.operation)}</h2>
                          <span className="pill">STEP {focused.step}</span>
                          <dl>
                            <dt>Call identity</dt>
                            <dd>{focused.call_id}</dd>
                            <dt>Coverage</dt>
                            <dd>{words(focused.coverage)}</dd>
                            <dt>Request fingerprint</dt>
                            <dd className="digest">
                              {focused.request_digest ?? "Not recorded"}
                            </dd>
                          </dl>
                          <div className="notice">
                            <LockKeyhole size={16} />
                            <p>
                              Payloads stay out of this view. Metadata describes
                              the declared boundary, not complete causal proof.
                            </p>
                          </div>
                          <Button
                            variant="outline"
                            onClick={() => {
                              setRoot(focused.step);
                              setTab("graph");
                            }}
                          >
                            <Network size={15} /> Inspect dependencies
                          </Button>
                        </>
                      ) : (
                        <p className="muted">
                          Choose a boundary to inspect its identity and
                          coverage.
                        </p>
                      )}
                    </aside>
                  </div>
                )}
                {tab === "graph" && (
                  <section className="view-content">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">DECLARED DEPENDENCIES</span>
                        <h2>Sequence is not causation.</h2>
                      </div>
                      <label className="step-input">
                        Root step
                        <input
                          type="number"
                          min={0}
                          max={Math.max(0, summary.records - 1)}
                          value={root}
                          onChange={(event) =>
                            setRoot(Math.max(0, Number(event.target.value)))
                          }
                        />
                      </label>
                    </div>
                    {graph ? (
                      <>
                        <Provenance
                          graph={graph}
                          onSelect={(step) => {
                            const row = rows.find(
                              (value) => value.step === step,
                            );
                            if (row) {
                              setFocused(row);
                              setTab("timeline");
                            }
                          }}
                        />
                        <div className="graph-footer">
                          <span>
                            {graph.nodes.length} visible nodes ·{" "}
                            {graph.edges.length} dependency edges
                          </span>
                          <span>
                            Declared blast radius
                            {graph.blast_radius_complete
                              ? ""
                              : " (partial)"}: {graph.blast_radius.length} steps
                          </span>
                        </div>
                        <p className="muted">{graph.limitation}</p>
                      </>
                    ) : (
                      <p className="empty-note">
                        Select an individual branch with supported boundary
                        metadata.
                      </p>
                    )}
                  </section>
                )}
                {tab === "replay" && (
                  <section className="view-content replay-view">
                    <div className="eyebrow">RESTORE / MATCH / REPORT</div>
                    <h2>Replay only what the evidence supports.</h2>
                    <p>
                      Import the verified capsule into a new temporary
                      directory, restore covered checkpoint bytes, then match
                      recorded requests without live calls.
                    </p>
                    <div className="replay-steps">
                      {[
                        "Verify archive",
                        "Restore checkpoints",
                        "Match boundaries",
                      ].map((step, i) => (
                        <div key={step}>
                          <span>
                            {replay ? <Check size={16} /> : `0${i + 1}`}
                          </span>
                          {step}
                        </div>
                      ))}
                    </div>
                    <Button
                      onClick={() => {
                        void runReplay();
                      }}
                      disabled={busy || summary.record_type === "experiment"}
                    >
                      {busy ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <Play size={16} />
                      )}{" "}
                      Restore and match boundaries
                    </Button>
                    {replay && (
                      <div className="result-panel" role="status">
                        <ShieldCheck size={20} />
                        <div>
                          <h3>{String(replay.mode)}</h3>
                          <p>
                            {String(
                              replay.matched ??
                                replay.matched_records ??
                                replay.records,
                            )}{" "}
                            boundaries matched · {String(replay.live_calls)}{" "}
                            live calls
                          </p>
                          <pre>
                            {JSON.stringify(replay.checkpoints, null, 2)}
                          </pre>
                          <p>{String(replay.limitation)}</p>
                        </div>
                      </div>
                    )}
                    {summary.record_type === "environment_pack" && (
                      <FutureEditor
                        key={selected + String(branch)}
                        endpoint={evidencePath("jobs")}
                      />
                    )}
                    {summary.record_type === "environment_pack" && (
                      <OperationConsole
                        key={selected + "ops" + String(branch)}
                        endpoint={evidencePath("jobs")}
                      />
                    )}
                    <div className="notice">
                      <TriangleAlert size={16} />
                      <p>
                        {summary.record_type === "environment_pack"
                          ? "Strict replay re-executes only the finite environment pack's declared file effects. It makes no native process, remote-state or general agent replay guarantee."
                          : "Boundary matching and checkpoint restoration do not re-execute native effects. This path does not claim VERIFIED_REPLAY."}
                      </p>
                    </div>
                  </section>
                )}
                {tab === "policies" && (
                  <section className="view-content">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">
                          TESTED ALTERNATE FUTURES
                        </span>
                        <h2>The smallest useful intervention.</h2>
                      </div>
                      <SlidersHorizontal size={20} />
                    </div>
                    {comparison ? (
                      <>
                        <p className="muted">
                          {comparison.scenarios} known synthetic scenarios ·{" "}
                          {comparison.branches.length} executed branches ·{" "}
                          {comparison.mode}
                        </p>
                        <table>
                          <thead>
                            <tr>
                              <th>Executed candidate</th>
                              <th>Full tasks</th>
                              <th>Protected exports</th>
                              <th>Unknown</th>
                              <th>Selection</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comparison.scores.map((score) => (
                              <tr key={score.arm}>
                                <td>
                                  <strong>{words(score.arm)}</strong>
                                </td>
                                <td>
                                  {score.task_completions}/
                                  {score.task_denominator}
                                </td>
                                <td>{score.protected_exposures}</td>
                                <td>{score.unknown}</td>
                                <td>
                                  {comparison.frontier.includes(score.arm) ? (
                                    <span className="pill green">
                                      PARETO FRONTIER
                                    </span>
                                  ) : (
                                    <span className="muted">—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <PolicyChart comparison={comparison} />
                        <PolicySource comparison={comparison} />
                        <h3>Open the underlying evidence</h3>
                        <div className="diff-grid">
                          {comparison.branches.map((item) => (
                            <Button
                              key={item.branch_index}
                              variant="outline"
                              onClick={() => setBranch(item.branch_index)}
                            >
                              Inspect {words(item.scenario)} / {words(item.arm)}
                            </Button>
                          ))}
                        </div>
                        <div className="notice">
                          <GitBranch size={16} />
                          <p>{comparison.selection_rule}</p>
                        </div>
                        <p className="muted">{comparison.limitation}</p>
                      </>
                    ) : (
                      <p className="empty-note">
                        Choose a policy comparison in the evidence library.
                        Candidates are shown only when their nested branch
                        capsules verify.
                      </p>
                    )}
                  </section>
                )}
                {tab === "diff" && (
                  <section className="view-content">
                    <div className="eyebrow">ORIGINAL / ALTERNATE</div>
                    <h2>What changed in the covered world?</h2>
                    {comparison ? (
                      <div className="diff-grid">
                        {comparison.world_diffs.map((diff) => (
                          <article
                            className="diff-card"
                            key={diff.scenario + diff.alternate_arm}
                          >
                            <span className="pill">
                              {words(diff.alternate_arm)}
                            </span>
                            <h3>{words(diff.scenario)}</h3>
                            {(["workspace", "fixture"] as const).map(
                              (world) => (
                                <div key={world}>
                                  <div className="sidebar-label">
                                    {world.toUpperCase()}
                                  </div>
                                  {diff.changes[world] === null ? (
                                    <p>Unknown state</p>
                                  ) : diff.changes[world]!.length ? (
                                    diff.changes[world]!.map((path) => (
                                      <code key={path} className="changed-path">
                                        ∆ {path}
                                      </code>
                                    ))
                                  ) : (
                                    <p className="unchanged">
                                      <Check size={13} /> Covered bytes
                                      unchanged
                                    </p>
                                  )}
                                </div>
                              ),
                            )}
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p className="empty-note">
                        Choose a verified comparison to inspect
                        baseline-versus-alternate file and executable-bit
                        differences.
                      </p>
                    )}
                  </section>
                )}
                {tab === "evidence" && (
                  <section className="view-content">
                    <div className="eyebrow">
                      PORTABLE / CHECKABLE / BOUNDED
                    </div>
                    <h2>Trust has more than one layer.</h2>
                    <dl className="evidence-grid">
                      <dt>Journal root</dt>
                      <dd className="digest">{summary.journal_root}</dd>
                      <dt>Archive members</dt>
                      <dd>{summary.artifacts} artifacts, checked by digest</dd>
                      <dt>Signing boundary</dt>
                      <dd>
                        {summary.signer_status} key ·{" "}
                        {summary.detached_statement_retained
                          ? "original detached statement retained"
                          : "original statement unavailable"}
                      </dd>
                      <dt>Freshness</dt>
                      <dd>Not established by archive integrity</dd>
                      <dt>Coverage</dt>
                      <dd>
                        {summary.record_type === "environment_pack"
                          ? "Finite environment pack: restored declared checkpoints and sandboxed file-effect re-execution"
                          : "Bounded regular-file checkpoints and recorded boundaries"}
                      </dd>
                    </dl>
                    {summary.record_type === "environment_pack" && (
                      <Button
                        variant="outline"
                        onClick={() => {
                          void api<Record<string, unknown>>(
                            evidencePath("telemetry"),
                          )
                            .then(setTelemetry)
                            .catch((failure) => setError(failure.message));
                        }}
                      >
                        Inspect journal-bound telemetry
                      </Button>
                    )}
                    {telemetry && (
                      <p role="status">
                        {String(telemetry.matched_spans)} matched SDK spans;{" "}
                        {String(telemetry.unmatched_spans)} unmatched.
                        Structural parentage is excluded from blast radius.
                      </p>
                    )}
                    {summary.storage_encrypted && (
                      <p className="muted">
                        Downloads use authenticated encryption. Keep the
                        operator's decryption key separately; opening an
                        encrypted capsule does not establish its signer.
                      </p>
                    )}
                    <div className="button-row">
                      <Button
                        variant="outline"
                        onClick={() => {
                          void api<Record<string, unknown>>(
                            evidencePath("verification"),
                          )
                            .then(setVerification)
                            .catch((failure) => setError(failure.message));
                        }}
                      >
                        <ShieldCheck size={16} /> Recheck stored evidence
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          void download();
                        }}
                      >
                        <ArrowDownToLine size={16} />{" "}
                        {summary.storage_encrypted
                          ? "Download encrypted capsule"
                          : "Download capsule"}
                      </Button>
                      <Button
                        variant="outline"
                        disabled={!summary.detached_statement_retained}
                        onClick={() => void download("attestation")}
                      >
                        Download detached signature
                      </Button>
                    </div>
                    {verification && (
                      <pre className="verification-result" role="status">
                        {JSON.stringify(verification, null, 2)}
                      </pre>
                    )}
                    <div className="notice">
                      <TriangleAlert size={16} />
                      <p>
                        Integrity is consistency of presented bytes. It does not
                        prove an independent author, latest state, complete
                        action coverage or production readiness.
                      </p>
                    </div>
                  </section>
                )}
              </section>
              <footer className="page-footer">
                <span>
                  <CircleDot size={12} /> Source-linked evidence · explicit
                  replay modes
                </span>
                <span>SENTINEL REPLAY / LOCAL-FIRST</span>
              </footer>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  icon,
  small,
}: {
  label: string;
  value: string;
  note: string;
  icon: React.ReactNode;
  small?: boolean;
}) {
  return (
    <article className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <div className={small ? "metric-value compact" : "metric-value"}>
        {value}
      </div>
      <small>{note}</small>
    </article>
  );
}
