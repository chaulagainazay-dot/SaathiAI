"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import {
  platformConnectors, platformHealth, platformMetrics, platformExecutions,
  platformPendingApprovals, platformDecideApproval,
} from "@/lib/api";

const ACCENT = "#7CF5E4", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A", GREY = "#8890A0";

// honest colour per integration-status label — never green unless genuinely live
const STATUS_COLOR = {
  "live-tested": TEAL,
  "deterministic-adapter-tested": ACCENT,
  "contract-ready": AMBER,
  "environment-blocked": GREY,
  unavailable: RED,
};

export default function Connectors() {
  const [conns, setConns] = useState(null);
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [execs, setExecs] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [err, setErr] = useState(null);
  const [authed, setAuthed] = useState(true);

  const load = () => {
    platformConnectors().then((d) => setConns(d.items || [])).catch((e) => { setErr(String(e)); setAuthed(false); });
    platformHealth().then(setHealth).catch(() => {});
    platformMetrics().then(setMetrics).catch(() => {});
    platformExecutions().then((d) => setExecs(d.items || [])).catch(() => {});
    platformPendingApprovals().then((d) => setApprovals(d.items || [])).catch(() => {});
  };
  useEffect(load, []);

  const decide = async (aid, ok) => { try { await platformDecideApproval(aid, ok); load(); } catch (e) { setErr(String(e)); } };

  const byCat = {};
  (conns || []).forEach((c) => { (byCat[c.category] = byCat[c.category] || []).push(c); });

  return (
    <div className="page" style={{ maxWidth: 1040, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Connector Platform (M15.1)</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0" }}>Connectors</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        One governed layer. Every action → ExecutionGateway → approval → evidence.
        Secrets are references only, never shown. States below are honest — no mock success.
      </div>

      {!authed && (
        <Panel style={{ padding: 14, marginBottom: 14, border: "1px solid rgba(232,184,75,0.4)" }}>
          <div style={{ fontSize: 13, color: AMBER }}>⚠ Sign in to view the connector platform. Open the app same-origin and unlock.</div>
        </Panel>
      )}
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {/* metrics strip — real sample, honestly labelled */}
      {health && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          {[["Connectors", health.total],
            ["Live", (health.summary || {})["live-tested"] || 0],
            ["Env-blocked", (health.summary || {})["environment-blocked"] || 0],
            ["Executions", metrics?.sample_size ?? 0],
            ["Success rate", metrics?.success_rate == null ? "—" : `${Math.round(metrics.success_rate * 100)}%`]]
            .map(([k, v]) => (
            <div key={k} className="glass" style={{ padding: "10px 18px", borderRadius: 12, minWidth: 110 }}>
              <div style={{ fontSize: 22, fontWeight: 600, color: ACCENT }}>{v}</div>
              <div style={{ fontSize: 11, opacity: 0.55 }}>{k}</div>
            </div>
          ))}
        </div>
      )}

      {/* pending approvals — bound to exact action */}
      <Panel style={{ padding: 16, marginBottom: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Pending approvals · {approvals.length}</Eyebrow>
        {approvals.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>none — no side-effect actions awaiting sign-off</div>}
        {approvals.map((a) => (
          <div key={a.id} style={{ padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ fontSize: 13 }}>
              <b>{a.tool_id}</b> <span className="mono" style={{ opacity: 0.5 }}>risk {a.risk} · {a.environment}{a.target ? ` · ${a.target}` : ""}</span>
            </div>
            <div className="mono" style={{ fontSize: 10.5, opacity: 0.5 }}>binds input {String(a.input_hash).slice(0, 12)}… · single-use</div>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button onClick={() => decide(a.id, true)} style={btn(TEAL)}>Approve exact action</button>
              <button onClick={() => decide(a.id, false)} style={btn(RED)}>Deny</button>
            </div>
          </div>
        ))}
      </Panel>

      {/* connector catalog — honest integration-status */}
      <Panel style={{ padding: 16, marginBottom: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Catalog</Eyebrow>
        {conns == null && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>loading…</div>}
        {conns && conns.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>no connectors registered</div>}
        {Object.entries(byCat).map(([cat, cs]) => (
          <div key={cat} style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, opacity: 0.5, textTransform: "capitalize" }}>{cat}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
              {cs.map((c) => (
                <div key={c.connector_id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[c.integration_status] || GREY }} />
                  <b>{c.display_name}</b>
                  <span className="mono" style={{ fontSize: 10.5, opacity: 0.5 }}>{c.provider} · {(c.capabilities || []).length} caps</span>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: 10, color: STATUS_COLOR[c.integration_status] || GREY }}>{c.integration_status}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Panel>

      {/* execution history — real evidence */}
      <Panel style={{ padding: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Recent executions</Eyebrow>
        {(execs || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>none yet</div>}
        {(execs || []).map((e) => (
          <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 }}>
            <span className="mono" style={{ opacity: 0.6 }}>{e.tool_id}</span>
            <span className="mono" style={{ opacity: 0.4 }}>risk {e.risk}</span>
            <span className="mono" style={{ marginLeft: "auto",
              color: e.status === "success" ? TEAL : e.status === "uncertain" ? AMBER : e.status === "approval_required" ? ACCENT : RED }}>
              {e.status}</span>
          </div>
        ))}
      </Panel>
    </div>
  );
}

const btn = (c) => ({ fontSize: 11, padding: "4px 12px", borderRadius: 8, cursor: "pointer",
  border: `1px solid ${c}`, background: "transparent", color: c, fontWeight: 600 });
