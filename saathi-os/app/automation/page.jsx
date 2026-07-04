"use client";
import { useState } from "react";
import { Panel, Eyebrow, Ring } from "@/components/ui";
import { color } from "@/lib/departments";
import { useAutomation } from "@/lib/useAutomation";
import { testHumanBrowser } from "@/lib/api";

const ORANGE = color("AUTOMATION");
const fmtMs = (ms) => (ms ? `${(ms / 1000).toFixed(0)}s` : "—");
const ago = (ts) => (ts ? `${Math.round((Date.now() / 1000 - ts) / 60)} min ago` : "never");

function TestJob() {
  const [s, setS] = useState({ k: "idle", m: "" });
  async function run() {
    let token = localStorage.getItem("saathi_token");
    if (!token) { token = window.prompt("SAATHI_TOKEN:") || ""; if (token) localStorage.setItem("saathi_token", token); }
    setS({ k: "run", m: "signing job → waiting for Mac Agent…" });
    try {
      const r = await testHumanBrowser(token);
      setS(r.ok ? { k: "ok", m: `Agent drove Chrome → "${r.result?.title || r.result?.url}"` }
                : { k: "err", m: r.error + (r.hint ? ` — ${r.hint}` : "") });
    } catch (e) { setS({ k: "err", m: String(e) }); }
  }
  const c = { idle: ORANGE, run: "#E8B84B", ok: "#4FD07A", err: "#FF5A5A" }[s.k];
  return (
    <div>
      <button onClick={run} disabled={s.k === "run"}
        style={{ padding: "8px 15px", borderRadius: 18, border: `1px solid ${ORANGE}`,
          background: `${ORANGE}18`, color: ORANGE, cursor: s.k === "run" ? "wait" : "pointer" }}>
        {s.k === "run" ? "Testing…" : "▶ Test a job"}
      </button>
      {s.m && <span style={{ fontSize: 12, marginLeft: 12, color: c }}>{s.m}</span>}
    </div>
  );
}

function Light({ ok }) { return <span>{ok ? "🟢" : "🔴"}</span>; }

export default function Automation() {
  const { data, live } = useAutomation();
  const h = data?.health || {};
  const comp = data?.components || {};
  const runs = data?.recent_runs || [];

  return (
    <div className="only-desktop" style={{ maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <Eyebrow style={{ color: ORANGE }}>Automation Center</Eyebrow>
          <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>Human Browser</div>
          <div style={{ fontSize: 13, opacity: 0.5, marginTop: 4 }}>{live ? "live" : "connecting…"}</div>
        </div>
        {data && <Ring value={(h.overall || 0) / 100} color={ORANGE} size={128} stroke={9}
          label={`${h.overall ?? 0}%`} sub="health" />}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ORANGE }}>Status</Eyebrow>
          <div style={{ marginTop: 10, fontSize: 14, lineHeight: 2 }}>
            <div><Light ok={comp.agent?.online} /> Mac Agent {comp.agent?.online ? "online" : "offline"}</div>
            <div><Light ok={comp.vision?.ready} /> Vision {comp.vision?.ready ? "ready" : "no key"}</div>
            <div><Light ok={comp.queue?.ready} /> Signed queue {comp.queue?.ready ? "ready" : "no secret"}</div>
          </div>
          <div style={{ marginTop: 14 }}><TestJob /></div>
        </Panel>

        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ORANGE }}>Metrics (24h)</Eyebrow>
          <div style={{ marginTop: 10, fontSize: 14, lineHeight: 2 }}>
            <div>Success rate <b style={{ color: ORANGE }}>{h.success_rate ?? 100}%</b></div>
            <div>Runs today <b>{h.runs_today ?? 0}</b> · Failures <b style={{ color: h.failures_today ? "#FF5A5A" : "inherit" }}>{h.failures_today ?? 0}</b></div>
            <div>Avg publish <b>{fmtMs(h.avg_publish_ms)}</b></div>
            <div>Last success <b>{ago(h.last_success)}</b></div>
          </div>
        </Panel>
      </div>

      <Panel style={{ padding: 18, marginTop: 14 }}>
        <Eyebrow style={{ color: ORANGE }}>Recent Runs (flight recorder)</Eyebrow>
        <div style={{ marginTop: 8 }}>
          {runs.length === 0 && <div style={{ opacity: 0.4, fontSize: 13, padding: "10px 0" }}>no runs yet — click “Test a job”</div>}
          {runs.map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "7px 2px",
              borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 13 }}>
              <span>{r.ok ? "🟢" : "🔴"} {r.capability || "run"} {r.title ? `· ${r.title}` : ""}</span>
              <span style={{ opacity: 0.55 }}>{fmtMs(r.duration_ms)}{r.error ? ` · ${r.error.slice(0, 40)}` : ""}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
