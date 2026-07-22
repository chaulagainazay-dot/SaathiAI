"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { controlComputer } from "@/lib/api";

const ACCENT = "#7CF5E4", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A", GREY = "#8890A0";

export default function ComputerCenter() {
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    controlComputer().then(setC).catch((e) => setErr(String(e)));
  }, []);

  const v = c?.value;
  return (
    <div className="page" style={{ maxWidth: 1000, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Control Center · Computer</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0" }}>Computer Center</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Desktop + browser agent. Every action routes through ExecutionGateway with a required
        active session, approvals for side effects, sensitive-input protection, and post-action
        verification. Live desktop control is shown honestly.
      </div>
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}
      {c == null && <div style={{ fontSize: 12.5, opacity: 0.4 }}>loading…</div>}

      {v && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            {[["Connectors", (v.connectors || []).length],
              ["Tools", v.tools],
              ["Live desktop control", v.live_desktop_control]].map(([k, val]) => (
              <div key={k} className="glass" style={{ padding: "12px 18px", borderRadius: 12, minWidth: 160 }}>
                <div style={{ fontSize: 16, fontWeight: 600,
                  color: val === "environment_blocked" ? AMBER : ACCENT }}>{String(val)}</div>
                <div style={{ fontSize: 11, opacity: 0.55 }}>{k}</div>
              </div>
            ))}
          </div>

          <Panel style={{ padding: 16, marginBottom: 16 }}>
            <Eyebrow style={{ color: ACCENT }}>Computer connectors</Eyebrow>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              {(v.connectors || []).map((c2) => (
                <span key={c2} className="mono" style={{ fontSize: 11, padding: "3px 10px",
                  borderRadius: 999, background: "rgba(124,245,228,0.08)", color: ACCENT }}>{c2}</span>
              ))}
            </div>
          </Panel>

          <Panel style={{ padding: 16 }}>
            <Eyebrow style={{ color: ACCENT }}>Provider availability (honest)</Eyebrow>
            <div style={{ marginTop: 8 }}>
              {Object.entries(v.providers || {}).map(([name, p]) => (
                <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
                  borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12.5 }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%",
                    background: p.available ? TEAL : GREY }} />
                  <span className="mono">{name}</span>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: 10.5,
                    color: p.status === "available" || p.status === "deterministic" ? TEAL : AMBER }}>
                    {p.status}</span>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 11, color: AMBER, marginTop: 10 }}>
              {v.note}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
