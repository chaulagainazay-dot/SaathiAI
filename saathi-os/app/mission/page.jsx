"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import Universe from "@/components/Universe";
import { Panel, Eyebrow, Bar, Dot } from "@/components/ui";
import { color } from "@/lib/departments";
import { fetchMissions } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

const HEALTH_LABELS = {
  knowledge: "Knowledge",
  marketing: "Marketing",
  finance: "Finance",
  revenue_tracking: "Revenue Tracking",
  operations: "Operations",
  automation: "Automation",
  evidence: "Evidence",
  learning: "Learning",
};

export default function MissionControl() {
  const [missions, setMissions] = useState([]);
  const [selectedMission, setSelectedMission] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchMissions()
      .then((ms) => {
        setMissions(ms || []);
        if (ms && ms.length > 0) setSelectedMission(ms[0]);
      })
      .catch(() => setError("Unable to load missions"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedMission) return;
    setLoading(true);
    setError("");
    const mid = selectedMission.id || selectedMission.key;
    fetch(`${API_BASE}/api/v1/missions/${mid}/health`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) throw new Error(d.error);
        setHealth(d);
      })
      .catch((e) => setError(e.message || "Failed to load health"))
      .finally(() => setLoading(false));
  }, [selectedMission]);

  const dims = health?.dimensions || {};
  const overall = health?.overall || 0;
  const weakest = health?.weakest || "";

  const healthBars = Object.entries(HEALTH_LABELS).map(([key, label]) => ({
    key,
    label,
    value: dims[key] || 0,
    dept: key === "knowledge" ? "KNOWLEDGE" : key === "marketing" ? "AI STUDIO" : key === "finance" ? "FINANCE" : key === "operations" ? "CAFETERIA" : key === "automation" ? "AI STUDIO" : key === "evidence" ? "LEARNING" : key === "learning" ? "LEARNING" : "MISSION",
  }));

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
            {loading ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--color-ink-500)" }}>Loading...</div>
            ) : error ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--color-ink-500)" }}>{error}</div>
            ) : (
              <div style={{ marginTop: 14 }}>
                {healthBars.slice(0, 6).map((h) => (
                  <Bar key={h.key} frac={h.value} color={color(h.dept)} label={h.label} value={`${Math.round(h.value * 100)}%`} />
                ))}
                {weakest && (
                  <div className="mono" style={{ fontSize: 10, color: "#FF9B9B", marginTop: 12 }}>
                    Weakest: {HEALTH_LABELS[weakest] || weakest} — needs attention
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* desktop */}
      <div className="only-desktop" style={{ display: "grid", gridTemplateColumns: "1fr 416px", gap: 28, maxWidth: 1620, margin: "0 auto", alignItems: "center" }}>
        <Universe />
        <Panel style={{ padding: 32 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
            <Eyebrow>System Health</Eyebrow>
            {missions.length > 1 && (
              <select
                value={selectedMission?.id || ""}
                onChange={(e) => {
                  const m = missions.find((x) => x.id === e.target.value);
                  if (m) setSelectedMission(m);
                }}
                style={{
                  background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 10, padding: "6px 12px", color: "var(--color-ink-200)", fontSize: 12,
                }}
              >
                {missions.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            )}
          </div>

          {loading ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--color-ink-500)" }}>Loading health data...</div>
          ) : error ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--color-ink-500)" }}>{error}</div>
          ) : (
            <>
              <div style={{ marginTop: 18 }}>
                {healthBars.map((h) => (
                  <div key={h.key} style={{ marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                      <Dot color={color(h.dept)} size={7} ring={false} />
                      <span style={{ fontSize: 12.5, color: "var(--color-ink-200)" }}>{h.label}</span>
                      <span className="mono" style={{ fontSize: 10, color: "var(--color-ink-500)", marginLeft: "auto" }}>
                        {Math.round(h.value * 100)}%
                      </span>
                    </div>
                    <Bar frac={h.value} color={color(h.dept)} label="" value="" />
                  </div>
                ))}
              </div>
              {weakest && (
                <div className="mono" style={{ fontSize: 10, color: "#FF9B9B", marginTop: 12, padding: 10, borderRadius: 8, background: "rgba(255,82,82,0.08)" }}>
                  ⚠ Weakest dimension: {HEALTH_LABELS[weakest] || weakest} ({Math.round((dims[weakest] || 0) * 100)}%)
                </div>
              )}
              <div style={{ height: 1, background: "var(--color-line)", margin: "20px 0" }} />
              <Eyebrow>Live Flows</Eyebrow>
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Dot color="#B78CFF" size={7} ring={false} />
                  <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-200)" }}>LEARNING → AI STUDIO</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Dot color="#FFB25A" size={7} ring={false} />
                  <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-200)" }}>AI STUDIO → FINANCE</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Dot color="#6E9BFF" size={7} ring={false} />
                  <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-200)" }}>KNOWLEDGE → EXECUTIVE</span>
                </div>
              </div>
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
