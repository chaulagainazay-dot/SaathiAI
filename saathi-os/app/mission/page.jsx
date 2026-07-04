"use client";
import Universe from "@/components/Universe";
import { Panel, Eyebrow, Bar, Dot } from "@/components/ui";
import { health, flows } from "@/lib/data";
import { color } from "@/lib/departments";

export default function MissionControl() {
  return (
    <>
    {/* mobile: scaled universe + compact health */}
    <div className="only-mobile">
      <div className="m-page">
        <div style={{ height: 400, overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center" }}>
          <div style={{ transform: "scale(0.52)", transformOrigin: "center" }}><Universe /></div>
        </div>
        <div className="m-card">
          <Eyebrow>System Health</Eyebrow>
          <div style={{ marginTop: 14 }}>
            {health.slice(0, 6).map((h) => (
              <Bar key={h.name} frac={h.value} color={color(h.dept)} label={h.name} value={`${Math.round(h.value * 100)}%`} />
            ))}
          </div>
        </div>
      </div>
    </div>

    {/* desktop */}
    <div className="only-desktop" style={{ display: "grid", gridTemplateColumns: "1fr 416px", gap: 28, maxWidth: 1620, margin: "0 auto",
      alignItems: "center" }}>
      <Universe />
      <Panel style={{ padding: 32 }}>
        <Eyebrow>System Health</Eyebrow>
        <div style={{ marginTop: 18 }}>
          {health.map((h) => (
            <div key={h.name} style={{ marginBottom: 4 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                <Dot color={color(h.dept)} size={7} ring={false} />
                <span style={{ fontSize: 12.5, color: "var(--color-ink-200)" }}>{h.name}</span>
              </div>
              <Bar frac={h.value} color={color(h.dept)} label="" value={`${Math.round(h.value * 100)}%`} />
            </div>
          ))}
        </div>
        <div style={{ height: 1, background: "var(--color-line)", margin: "20px 0" }} />
        <Eyebrow>Live Flows</Eyebrow>
        <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          {flows.map((f) => (
            <div key={f.from + f.to} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Dot color={f.color} size={7} ring={false} />
              <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-200)" }}>
                {f.from} → {f.to}
              </span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
    </>
  );
}
