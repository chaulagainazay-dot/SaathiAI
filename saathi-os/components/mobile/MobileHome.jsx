"use client";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { notices, DREAM_TARGET } from "@/lib/data";
import { DEPARTMENTS, color } from "@/lib/departments";
import { Eyebrow, Counter } from "@/components/ui";
import { useCeoHome } from "@/lib/useCeoHome";
import { fetchMission, completeMission } from "@/lib/api";

const usd = (n) => "$" + n.toLocaleString("en-US");
const TEAL = "#00BFA5";

export default function MobileHome() {
  const router = useRouter();
  const { data: home, live } = useCeoHome();
  const dreamFrac = home.dreamCurrent / DREAM_TARGET;
  const [mission, setMission] = useState(null);
  useEffect(() => { fetchMission().then(setMission).catch(() => {}); }, []);
  const tick = (key) => completeMission(key).then((r) => r.mission && setMission(r.mission)).catch(() => {});
  return (
    <div className="m-page">
      {/* dream + score + revenue */}
      <div className="m-card">
        <Eyebrow>Dream Progress</Eyebrow>
        <div className="display" style={{ fontSize: 20, margin: "8px 0 10px" }}>{usd(Math.round(DREAM_TARGET))}</div>
        <div style={{ height: 8, borderRadius: 6, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
          <motion.div initial={{ width: 0 }} animate={{ width: "6%" }} transition={{ duration: 1, ease: [0.22,1,0.36,1] }}
            style={{ height: "100%", background: color("FINANCE"), boxShadow: `0 0 12px ${color("FINANCE")}` }} />
        </div>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-500)", marginTop: 8 }}>
          {usd(home.dreamCurrent)} · {(dreamFrac * 100).toFixed(2)}% · on trend
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 18 }}>
          <div style={{ minWidth: 0, textAlign: "center", padding: "14px 6px", borderRadius: 16, background: "rgba(255,255,255,0.04)" }}>
            <Eyebrow>Today's Score</Eyebrow>
            <div className="display" style={{ fontSize: 30, color: color("FINANCE") }}>
              <Counter to={home.priorityScore} />
            </div>
          </div>
          <div style={{ minWidth: 0, textAlign: "center", padding: "14px 6px", borderRadius: 16, background: "rgba(255,255,255,0.04)" }}>
            <Eyebrow>Revenue Today</Eyebrow>
            <div className="display" style={{ fontSize: 30, color: "#4FD07A" }}>
              <Counter to={home.revenueToday} format={(v) => usd(Math.round(v))} />
            </div>
          </div>
        </div>
        {home.priorityReasons?.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 14 }}>
            {home.priorityReasons.map((r) => (
              <span key={r.label} className="mono" style={{ fontSize: 9.5, padding: "4px 9px", borderRadius: 999,
                color: r.tone === "down" ? "#FF9B9B" : "#8FE0A8",
                background: r.tone === "down" ? "rgba(255,90,90,0.12)" : "rgba(79,208,122,0.12)" }}>
                {r.label}
              </span>
            ))}
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: live ? "#4FD07A" : "#8B98B4",
            boxShadow: live ? "0 0 8px #4FD07A" : "none" }} />
          <span className="eyebrow" style={{ fontSize: 9 }}>{live ? "Live from platform" : "Offline · cached"}</span>
        </div>
      </div>

      {/* today's IELTS mission */}
      {mission && mission.topic && (
        <div className="m-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow>🎓 {mission.program} · Day {mission.day}</Eyebrow>
            <span className="mono" style={{ fontSize: 10, color: "var(--color-ink-400)" }}>🔥 {mission.streak}d · ~{mission.estimated_minutes}m</span>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, margin: "8px 0 2px", color: "var(--color-ink-100)" }}>{mission.topic}</div>
          <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-400)", marginBottom: 12 }}>
            {mission.episode} · {mission.phase} · {mission.difficulty}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(mission.checklist || []).map((c) => (
              <button key={c.key} onClick={() => tick(c.key)}
                style={{ display: "flex", alignItems: "center", gap: 10, textAlign: "left", cursor: "pointer",
                  padding: "11px 14px", borderRadius: 14, fontSize: 14,
                  background: c.done ? "rgba(0,191,165,0.12)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${c.done ? "rgba(0,191,165,0.4)" : "rgba(255,255,255,0.08)"}`,
                  color: "var(--color-ink-200)" }}>
                <span style={{ fontSize: 16 }}>{c.done ? "✅" : "⬜"}</span> {c.label}
              </button>
            ))}
          </div>
          <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-500)", marginTop: 10 }}>
            {mission.completed}/{mission.total} done · reward +1 streak · +{mission.reward?.dream_pct}% dream
          </div>
        </div>
      )}

      {/* top priorities */}
      <div>
        <Eyebrow style={{ padding: "0 4px 10px" }}>Top Priorities</Eyebrow>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {home.actions.map((a, i) => (
            <motion.div key={a.title} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i }} className="m-card"
              style={{ display: "flex", alignItems: "center", gap: 14, padding: 16 }}
              onClick={() => router.push(a.dept === "FINANCE" || a.dept === "OPPORTUNITY" ? "/finance" : "/")}>
              <span style={{ width: 34, height: 34, borderRadius: 12, flexShrink: 0, display: "flex",
                alignItems: "center", justifyContent: "center", fontWeight: 700, color: "#0A1120",
                background: color(a.dept) }}>{i + 1}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14.5, color: "var(--color-ink-100)" }}>{a.title}</div>
                <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-400)", marginTop: 3 }}>{a.meta}</div>
              </div>
              <span style={{ fontSize: 9, letterSpacing: "0.1em", color: color(a.dept), fontFamily: "var(--font-mono)" }}>{a.tag}</span>
            </motion.div>
          ))}
        </div>
      </div>

      {/* notifications with actions */}
      <div>
        <Eyebrow style={{ padding: "0 4px 10px" }}>Notifications</Eyebrow>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {notices.map((n) => (
            <div key={n.title} className="m-card" style={{ display: "flex", alignItems: "center", gap: 12, padding: 14 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color(n.dept), boxShadow: `0 0 8px ${color(n.dept)}` }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 9, letterSpacing: "0.1em", color: color(n.dept), fontFamily: "var(--font-mono)" }}>
                  {DEPARTMENTS[n.dept]?.name.toUpperCase()}
                </div>
                <div style={{ fontSize: 13.5, color: "var(--color-ink-200)", marginTop: 2 }}>{n.title}</div>
              </div>
              <button style={{ padding: "7px 14px", borderRadius: 999, fontSize: 11, cursor: "pointer",
                color: color(n.dept), background: `${color(n.dept)}22`, border: `1px solid ${color(n.dept)}55` }}>{n.action}</button>
            </div>
          ))}
        </div>
      </div>

      {/* Saathi briefing + ask */}
      <div className="m-card">
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span className="pulse" style={{ width: 9, height: 9, borderRadius: "50%", background: "#8FB4FF", boxShadow: "0 0 12px #8FB4FF" }} />
          <Eyebrow>Saathi Briefing</Eyebrow>
        </div>
        {home.briefing.slice(0, 3).map((b) => (
          <div key={b} style={{ display: "flex", gap: 10, marginBottom: 10 }}>
            <span style={{ marginTop: 7, width: 4, height: 4, borderRadius: "50%", background: "#3E4A66", flexShrink: 0 }} />
            <span style={{ fontSize: 13.5, color: "var(--color-ink-200)", lineHeight: 1.4 }}>{b}</span>
          </div>
        ))}
        <button onClick={() => router.push("/saathi")}
          style={{ width: "100%", marginTop: 12, padding: "14px", borderRadius: 16, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            background: "rgba(143,180,255,0.14)", border: "1px solid rgba(143,180,255,0.4)", color: "#DCE6FA", fontSize: 14 }}>
          🎤 Ask Saathi
        </button>
      </div>
    </div>
  );
}
