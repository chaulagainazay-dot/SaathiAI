"use client";
// M11 — Multi-agent run panel for Saathi Chat. Renders the REAL M10
// orchestration state: task graph, delegations, tool intents (risk-tagged),
// pending approvals (approve/deny), pause/resume/cancel, events, artifacts.
// Polls while the run is non-terminal; never fabricates progress — every
// field here is read straight from /api/v1/agents/*.
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

const TERMINAL = new Set([
  "completed", "cancelled", "timed_out", "failed", "rolled_back",
  "partially_completed",
]);

const STATE_COLOR = {
  completed: "#4fe3cb", running: "#5ea1ff", queued: "#8fa0c4",
  awaiting_approval: "#ffb04f", approved: "#5ea1ff", planning: "#8fa0c4",
  paused: "#ffb04f", blocked: "#ff8c8c", failed: "#ff5a5a",
  cancelled: "#8fa0c4", timed_out: "#ff8c8c",
  partially_completed: "#ffb04f",
};

const TASK_COLOR = {
  done: "#4fe3cb", running: "#5ea1ff", failed: "#ff5a5a",
  blocked: "#ffb04f", pending: "#8fa0c4", ready: "#8fa0c4",
  skipped: "#8fa0c4", cancelled: "#8fa0c4",
};

const RISK_LABEL = ["read-only", "local", "mutation", "external", "high-impact"];

const S = {
  wrap: { display: "flex", flexDirection: "column", gap: 10, fontSize: 12 },
  head: { fontSize: 10, opacity: .5, letterSpacing: ".14em", margin: "10px 0 6px" },
  badge: (color) => ({
    display: "inline-block", padding: "2px 9px", borderRadius: 999,
    fontSize: 10, letterSpacing: ".05em", background: `${color}22`,
    color, border: `1px solid ${color}55`,
  }),
  row: {
    padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,.04)",
    marginBottom: 6, border: "1px solid rgba(255,255,255,.06)",
  },
  btn: (color = "#4fe3cb") => ({
    background: `${color}22`, color, border: `1px solid ${color}55`,
    borderRadius: 8, padding: "5px 10px", fontSize: 11, cursor: "pointer",
    marginRight: 6,
  }),
  approval: {
    padding: 10, borderRadius: 10, background: "rgba(255,176,79,.1)",
    border: "1px solid rgba(255,176,79,.35)", marginBottom: 8,
  },
};

export default function AgentRunPanel({ runId, onClose }) {
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const [rRun, rEv] = await Promise.all([
        afetch(`${API_BASE}/api/v1/agents/runs/${runId}`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/agents/runs/${runId}/events?limit=40`, { cache: "no-store" }),
      ]);
      const j = await rRun.json();
      if (j.error) { setError(j.error); return; }
      setRun(j);
      setEvents((await rEv.json()).events || []);
      setError("");
    } catch {
      setError("Agent runtime unreachable.");
    }
  }, [runId]);

  useEffect(() => {
    load();
    clearInterval(timer.current);
    timer.current = setInterval(() => {
      setRun((r) => {
        if (r && TERMINAL.has(r.run?.state)) { clearInterval(timer.current); return r; }
        load();
        return r;
      });
    }, 2000);
    return () => clearInterval(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  async function act(path, opts = {}) {
    await afetch(`${API_BASE}/api/v1/agents/runs/${runId}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    load();
  }

  if (!runId) return null;
  if (error) return <div style={{ ...S.wrap, color: "#ff8c8c" }}>{error}</div>;
  if (!run) return <div style={S.wrap}>Loading run…</div>;

  const state = run.run.state;
  const color = STATE_COLOR[state] || "#8fa0c4";
  const terminal = TERMINAL.has(state);

  return (
    <div style={S.wrap}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={S.badge(color)}>{state.replace(/_/g, " ")}</span>
        <span style={{ opacity: .5, flex: 1, overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}>{run.run.objective}</span>
        {onClose && <button style={S.btn("#8fa0c4")} onClick={onClose}>×</button>}
      </div>

      {!terminal && (
        <div>
          {state === "paused"
            ? <button style={S.btn()} onClick={() => act("/resume")}>▶ Resume</button>
            : <button style={S.btn("#ffb04f")} onClick={() => act("/pause")}>⏸ Pause</button>}
          <button style={S.btn("#ff5a5a")} onClick={() => act("/cancel")}>✕ Cancel</button>
        </div>
      )}

      {/* pending approvals — real gate, resolved by the user only */}
      {(run.pending_approvals || []).map((a) => (
        <div key={a.id} style={S.approval}>
          <div style={{ marginBottom: 6 }}>
            <strong>@{a.agent}</strong> requests approval
            <span style={{ ...S.badge("#ffb04f"), marginLeft: 8 }}>
              risk {RISK_LABEL[a.risk] || a.risk}
            </span>
          </div>
          <div style={{ opacity: .75, marginBottom: 8, wordBreak: "break-word" }}>{a.action}</div>
          <button style={S.btn("#4fe3cb")}
                  onClick={() => act("/approve", { body: { approval_id: a.id, approved: true } })}>
            ✓ Approve
          </button>
          <button style={S.btn("#ff5a5a")}
                  onClick={() => act("/approve", { body: { approval_id: a.id, approved: false } })}>
            ✕ Deny
          </button>
        </div>
      ))}

      <div style={S.head}>TASK GRAPH</div>
      {(run.tasks || []).map((t) => (
        <div key={t.id} style={S.row}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>@{t.agent}</span>
            <span style={S.badge(TASK_COLOR[t.status] || "#8fa0c4")}>{t.status}</span>
          </div>
          <div style={{ opacity: .55, marginTop: 3, fontSize: 11 }}>
            {t.objective}
            {t.status === "failed" && (
              <button style={{ ...S.btn("#ffb04f"), marginTop: 6 }}
                      onClick={() => act(`/tasks/${t.id}/retry`)}>↻ Retry task</button>
            )}
          </div>
        </div>
      ))}
      {(run.tasks || []).length === 0 && <div style={{ opacity: .5 }}>No tasks yet.</div>}

      {run.delegations?.length > 0 && (
        <>
          <div style={S.head}>DELEGATION</div>
          {run.delegations.map((d) => (
            <div key={d.id} style={{ ...S.row, opacity: .8 }}>
              @{d.parent_agent} → @{d.child_agent} · depth {d.depth}
            </div>
          ))}
        </>
      )}

      <div style={S.head}>METRICS</div>
      <div style={{ opacity: .75 }}>
        {run.metrics?.events ?? 0} events · {run.metrics?.tool_calls ?? 0} tool calls ·
        {" "}{run.metrics?.retries ?? 0} retries · {run.metrics?.delegations ?? 0} delegations
      </div>

      <div style={S.head}>RECENT EVENTS</div>
      {events.slice(-10).reverse().map((e) => (
        <div key={e.id} style={{ opacity: .55, marginBottom: 3 }}>
          {e.name}
        </div>
      ))}
    </div>
  );
}
