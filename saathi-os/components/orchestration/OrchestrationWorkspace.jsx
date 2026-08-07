"use client";

import { useCallback, useEffect, useState } from "react";
import { orchestrationActions, safeToken, stateTone } from "@/lib/orchestration";

const styles = {
  wrap: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
    padding: 16,
    color: "#e8ecf5",
    maxWidth: 1100,
    margin: "0 auto",
  },
  card: {
    border: "1px solid rgba(255,255,255,.1)",
    borderRadius: 14,
    padding: 14,
    background: "rgba(255,255,255,.03)",
  },
  input: {
    width: "100%",
    background: "rgba(255,255,255,.05)",
    color: "#e8ecf5",
    border: "1px solid rgba(255,255,255,.12)",
    borderRadius: 10,
    padding: "10px 12px",
    fontSize: 14,
  },
  btn: {
    background: "rgba(0,191,165,.16)",
    color: "#4fe3cb",
    border: "1px solid rgba(0,191,165,.4)",
    borderRadius: 10,
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  btnMuted: {
    background: "rgba(255,255,255,.06)",
    color: "#c5cde0",
    border: "1px solid rgba(255,255,255,.12)",
    borderRadius: 10,
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  btnDanger: {
    background: "rgba(255,90,90,.12)",
    color: "#ff8c8c",
    border: "1px solid rgba(255,90,90,.35)",
    borderRadius: 10,
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  row: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" },
  meta: { fontSize: 12, color: "#9aa8c7", lineHeight: 1.5 },
  badge: (tone) => ({
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 999,
    fontSize: 11,
    border: "1px solid rgba(255,255,255,.15)",
    color: tone === "ok" ? "#4fe3cb" : tone === "warn" ? "#ffb04f" : tone === "bad" ? "#ff8c8c" : "#9aa8c7",
  }),
  table: { width: "100%", borderCollapse: "collapse", fontSize: 12 },
  th: { textAlign: "left", padding: "6px 4px", borderBottom: "1px solid rgba(255,255,255,.1)" },
  td: { padding: "6px 4px", borderBottom: "1px solid rgba(255,255,255,.06)", verticalAlign: "top" },
};

/**
 * Operator workspace for Agent Orchestration.
 * Distinguishes planned vs executed. Never implies model tool authority.
 */
export default function OrchestrationWorkspace() {
  const [token, setToken] = useState("");
  const [objective, setObjective] = useState(
    "Audit the HCG POS project and produce an implementation plan"
  );
  const [domain, setDomain] = useState("hcg");
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");
  const [preview, setPreview] = useState(null);
  const [active, setActive] = useState(null);
  const [list, setList] = useState([]);
  const [view, setView] = useState("list"); // list | graph
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState(null);

  const refreshList = useCallback(async (tok) => {
    if (!tok) return;
    try {
      const data = await orchestrationActions.list(tok);
      setList(data.orchestrations || []);
    } catch {
      /* keep */
    }
  }, []);

  useEffect(() => {
    const t = safeToken();
    setToken(t);
    if (!t) return undefined;
    (async () => {
      try {
        const [h, tmpl] = await Promise.all([
          orchestrationActions.health(t),
          orchestrationActions.templates(t),
        ]);
        setHealth(h.health || h);
        setTemplates(tmpl.templates || []);
        await refreshList(t);
      } catch (err) {
        setError(err.message || "Orchestration unavailable");
      }
    })();
    return () => {
      setActive(null);
      setPreview(null);
      setToken("");
    };
  }, [refreshList]);

  async function compilePreview(e) {
    e?.preventDefault?.();
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const data = await orchestrationActions.compile(token, {
        objective,
        domain,
        template_id: templateId,
      });
      setPreview(data);
    } catch (err) {
      setError(err.message || "Compile failed");
    } finally {
      setBusy(false);
    }
  }

  async function createMission(e) {
    e?.preventDefault?.();
    if (!token) return;
    if (!window.confirm("Create a validated orchestration mission?")) return;
    setBusy(true);
    setError("");
    try {
      const data = await orchestrationActions.create(token, {
        objective,
        domain,
        template_id: templateId,
      });
      setActive(data.orchestration);
      setPreview(null);
      await refreshList(token);
    } catch (err) {
      setError(err.message || "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function loadOne(id) {
    if (!token || !id) return;
    setBusy(true);
    try {
      const data = await orchestrationActions.get(token, id);
      setActive(data.orchestration);
    } catch (err) {
      setError(err.message || "Load failed");
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action) {
    if (!token || !active?.orchestration_id) return;
    const highRisk = ["start", "cancel", "certify"].includes(action);
    if (highRisk && !window.confirm(`Confirm ${action} on this orchestration?`)) return;
    setBusy(true);
    setError("");
    try {
      let data;
      const id = active.orchestration_id;
      if (action === "start") data = await orchestrationActions.start(token, id);
      else if (action === "pause") data = await orchestrationActions.pause(token, id);
      else if (action === "cancel") data = await orchestrationActions.cancel(token, id);
      else if (action === "replan") data = await orchestrationActions.replan(token, id, { reason: "operator" });
      else if (action === "checkpoint") data = await orchestrationActions.checkpoint(token, id);
      else if (action === "certify") {
        data = await orchestrationActions.certify(token, id, {
          with_limitations: true,
          summary: "Operator certification with limitations",
          limitations: ["local only", "production not authorized"],
        });
      }
      if (data?.orchestration) setActive(data.orchestration);
      else if (data?.checkpoint) {
        const refreshed = await orchestrationActions.get(token, id);
        setActive(refreshed.orchestration);
      }
      await refreshList(token);
    } catch (err) {
      setError(err.message || `${action} failed`);
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div style={styles.wrap} data-orchestration-panel="signed-out">
        <p role="status">Sign in to use Agent Orchestration.</p>
      </div>
    );
  }

  const tasks = active?.graph?.tasks || [];
  const activity = active?.activity || [];

  return (
    <div style={styles.wrap} data-orchestration-panel="active" aria-label="Agent orchestration">
      <header>
        <h1 style={{ fontSize: 22, margin: "0 0 6px" }}>Agent Orchestration</h1>
        <p style={styles.meta}>
          Plan and supervise multi-step work through Mission Runtime. Models cannot execute tools.
          Production is not authorized. Proposed work is never shown as executed.
        </p>
        {health ? (
          <div style={styles.meta} data-testid="orch-health">
            Active: {health.active_orchestrations} · Roles: {health.roles} · Templates:{" "}
            {health.templates} · Gateway: {health.execution_gateway}
          </div>
        ) : null}
      </header>

      <section style={styles.card} aria-label="Objective intake">
        <form onSubmit={createMission}>
          <label htmlFor="orch-objective" style={{ fontSize: 13 }}>
            Objective
          </label>
          <textarea
            id="orch-objective"
            style={{ ...styles.input, minHeight: 72, resize: "vertical", marginTop: 6 }}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            maxLength={4000}
          />
          <div style={{ ...styles.row, marginTop: 10 }}>
            <label htmlFor="orch-domain" style={styles.meta}>
              Domain
            </label>
            <input
              id="orch-domain"
              style={{ ...styles.input, width: 140 }}
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <label htmlFor="orch-template" style={styles.meta}>
              Template
            </label>
            <select
              id="orch-template"
              style={{ ...styles.input, width: 220 }}
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              aria-label="Plan template"
            >
              <option value="">Auto</option>
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.title}
                </option>
              ))}
            </select>
            <button type="button" style={styles.btnMuted} disabled={busy} onClick={compilePreview}>
              Preview plan
            </button>
            <button type="submit" style={styles.btn} disabled={busy}>
              Create mission
            </button>
          </div>
        </form>
        {preview ? (
          <div style={{ marginTop: 12 }} data-testid="plan-preview">
            <div style={styles.row}>
              <strong>Plan preview</strong>
              <span style={styles.badge(preview.validation?.ok ? "ok" : "bad")}>
                {preview.validation?.ok ? "Valid" : "Invalid"}
              </span>
              <span style={styles.meta}>
                nodes {preview.validation?.node_count} · deps {preview.validation?.dependency_count}
              </span>
            </div>
            {preview.validation?.errors?.length ? (
              <ul style={{ color: "#ff8c8c", fontSize: 12 }}>
                {preview.validation.errors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            ) : (
              <p style={styles.meta}>
                Template {preview.plan?.template_id}. Assignments:{" "}
                {(preview.assignments || []).length}. Not executed.
              </p>
            )}
          </div>
        ) : null}
      </section>

      <section style={styles.card} aria-label="Orchestration list">
        <div style={styles.row}>
          <strong>Missions</strong>
          <button type="button" style={styles.btnMuted} onClick={() => refreshList(token)}>
            Refresh
          </button>
        </div>
        <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0" }}>
          {list.map((item) => (
            <li key={item.orchestration_id} style={{ marginBottom: 6 }}>
              <button
                type="button"
                style={styles.btnMuted}
                onClick={() => loadOne(item.orchestration_id)}
              >
                <span style={styles.badge(stateTone(item.state))}>{item.state}</span>{" "}
                {item.objective}
              </button>
            </li>
          ))}
          {!list.length ? <li style={styles.meta}>No orchestrations yet.</li> : null}
        </ul>
      </section>

      {active ? (
        <section style={styles.card} aria-label="Active orchestration" data-active-orch={active.orchestration_id}>
          <div style={styles.row}>
            <strong>Active</strong>
            <span style={styles.badge(stateTone(active.state))} data-orch-state={active.state}>
              {active.state}
            </span>
            <span style={styles.meta}>v{active.plan_version}</span>
            <span style={styles.meta}>mission {active.mission_id}</span>
          </div>
          <p style={styles.meta}>{active.objective}</p>
          <div style={{ ...styles.row, marginTop: 8 }}>
            <button type="button" style={styles.btn} disabled={busy} onClick={() => runAction("start")}>
              Start
            </button>
            <button type="button" style={styles.btnMuted} disabled={busy} onClick={() => runAction("pause")}>
              Pause
            </button>
            <button type="button" style={styles.btnMuted} disabled={busy} onClick={() => runAction("replan")}>
              Replan
            </button>
            <button type="button" style={styles.btnMuted} disabled={busy} onClick={() => runAction("checkpoint")}>
              Checkpoint
            </button>
            <button type="button" style={styles.btnMuted} disabled={busy} onClick={() => runAction("certify")}>
              Certify (limitations)
            </button>
            <button type="button" style={styles.btnDanger} disabled={busy} onClick={() => runAction("cancel")}>
              Cancel
            </button>
            <button
              type="button"
              style={styles.btnMuted}
              onClick={() => setView(view === "list" ? "graph" : "list")}
            >
              View: {view}
            </button>
          </div>

          <div style={{ marginTop: 12 }}>
            <strong style={{ fontSize: 13 }}>
              {view === "list" ? "Tasks" : "Graph (task list with deps)"}
            </strong>
            <table style={styles.table} data-testid="orch-tasks">
              <thead>
                <tr>
                  <th style={styles.th}>Title</th>
                  <th style={styles.th}>Agent</th>
                  <th style={styles.th}>Status</th>
                  <th style={styles.th}>Notes</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.node_id || t.title}>
                    <td style={styles.td}>{t.title}</td>
                    <td style={styles.td}>{t.agent_type}</td>
                    <td style={styles.td}>
                      <span style={styles.badge(stateTone(t.status))}>{t.status}</span>
                    </td>
                    <td style={styles.td}>
                      {t.status === "PENDING" || t.status === "READY" || t.status === "PLANNED"
                        ? "planned"
                        : t.status === "COMPLETED"
                          ? "executed via gateway"
                          : t.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <strong style={{ fontSize: 13 }}>Activity</strong>
              <ul style={{ fontSize: 12, color: "#9aa8c7" }} data-testid="orch-activity">
                {activity.slice(-12).reverse().map((a, i) => (
                  <li key={`${a.ts}-${i}`}>
                    {a.kind}: {a.message}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Evidence / checkpoints</strong>
              <div style={styles.meta}>
                Evidence: {(active.evidence || []).length} · Checkpoints:{" "}
                {(active.checkpoints || []).length}
              </div>
              <div style={styles.meta}>
                Certification: {active.certification?.verdict || "not certified"}
              </div>
              {(active.limitations || []).length ? (
                <ul style={{ fontSize: 12, color: "#ffb04f" }}>
                  {active.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      {error ? (
        <p role="alert" style={{ color: "#ff8c8c" }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
