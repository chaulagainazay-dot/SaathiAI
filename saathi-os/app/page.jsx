"use client";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { DEPARTMENTS, color } from "@/lib/departments";
import { Panel, Eyebrow, Pill, Dot, Bar, Ring, Counter } from "@/components/ui";
import MobileHome from "@/components/mobile/MobileHome";
import { useCeoHome } from "@/lib/useCeoHome";

const usd = (n) => "$" + n.toLocaleString("en-US");

export default function CeoHome() {
  const router = useRouter();
  const { data: home, live, loading } = useCeoHome();
  if (!home) {
    return (
      <div className="only-desktop" style={{ maxWidth: 1620, margin: "0 auto", padding: 40 }}>
        <Panel style={{ padding: 60, textAlign: "center" }}>
          <Eyebrow>Loading Executive Intelligence...</Eyebrow>
          <div style={{ marginTop: 20, color: "var(--color-ink-400)", fontSize: 14 }}>
            {loading ? "Connecting to SaathiOS..." : "Unable to load data. The platform may be offline."}
          </div>
        </Panel>
      </div>
    );
  }
  const dreamFrac = (home.dreamCurrent || 0) / (home.dreamTarget || 1);

  return (
    <>
    <div className="only-mobile"><MobileHome /></div>
    <div className="only-desktop" style={{ display: "grid", gridTemplateColumns: "440px 1fr 466px", gap: 28, maxWidth: 1620, margin: "0 auto" }}>
      {/* LEFT — priority + stats */}
      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <Panel className="p-8" style={{ padding: 32, display: "flex", flexDirection: "column", alignItems: "center" }}>
          <Ring value={(home.priorityScore || 0) / 100} color={color("FINANCE")} size={220}
            label={home.priorityScore} sub="Priority Score" />
          {home.priorityReasons?.length > 0 && (
            <div style={{ marginTop: 18, display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
              {home.priorityReasons.map((r) => (
                <span key={r.label} className="mono" style={{ fontSize: 10, padding: "5px 10px", borderRadius: 999,
                  color: r.tone === "down" ? "#FF9B9B" : "#8FE0A8",
                  background: r.tone === "down" ? "rgba(255,90,90,0.12)" : "rgba(79,208,122,0.12)",
                  border: `1px solid ${r.tone === "down" ? "rgba(255,90,90,0.3)" : "rgba(79,208,122,0.3)"}` }}>
                  {r.label}
                </span>
              ))}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 16 }}>
            <span className="pulse" style={{ width: 7, height: 7, borderRadius: "50%",
              background: live ? "#4FD07A" : "#8B98B4", boxShadow: live ? "0 0 8px #4FD07A" : "none" }} />
            <span className="eyebrow">{live ? "Live · Executive Intelligence" : "Offline · cached"}</span>
          </div>
        </Panel>

        <Panel delay={0.05} style={{ padding: 28 }}>
          <div style={{ display: "flex", gap: 40 }}>
            <div>
              <Eyebrow>Execution · Yesterday</Eyebrow>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 8 }}>
                <Counter to={home.executionScore} className="display" style={{ fontSize: 36 }} />
                <span className="mono" style={{ color: "#4FD07A", fontSize: 11 }}>▲ {home.executionDelta}%</span>
              </div>
            </div>
            <div>
              <Eyebrow>Revenue Today</Eyebrow>
              <div className="display" style={{ fontSize: 36, marginTop: 8, color: "#4FD07A" }}>
                <Counter to={home.revenueToday} format={(v) => usd(Math.round(v))} />
              </div>
            </div>
          </div>
          <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-500)", marginTop: 14 }}>{home.revenueSplit}</div>
          <div style={{ height: 1, background: "var(--color-line)", margin: "18px 0" }} />
          <Eyebrow>Dream Progress</Eyebrow>
          <div style={{ marginTop: 12 }}>
            <Bar frac={dreamFrac} color={color("FINANCE")} label={`${usd(home.dreamCurrent || 0)} / ${usd(Math.round(home.dreamTarget || 0))}`}
              value={`${(dreamFrac * 100).toFixed(2)}%`} />
          </div>
          <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-500)" }}>{home.revenueSplit || "Revenue data unavailable"}</div>
        </Panel>
      </div>

      {/* CENTER — actions + approvals/notifications */}
      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <div>
          <Eyebrow style={{ marginBottom: 14 }}>What should I do next</Eyebrow>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {home.actions.map((a, i) => (
              <Panel key={a.title} delay={0.06 * i}
                onClick={() => a.route && router.push(a.route)}
                style={{ padding: "18px 22px", display: "flex", alignItems: "center", gap: 16,
                  cursor: a.route ? "pointer" : "default" }}>
                <Dot color={color(a.dept)} size={9} />
                <div style={{ flex: 1 }}>
                  <div className="eyebrow" style={{ color: color(a.dept), fontSize: 9 }}>{DEPARTMENTS[a.dept]?.name || a.dept}</div>
                  <div style={{ fontWeight: 600, fontSize: 15.5, marginTop: 3, color: "var(--color-ink-100)" }}>{a.title}</div>
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-400)", marginTop: 5 }}>{a.meta}</div>
                </div>
                <Pill color={color(a.dept)} filled={0.16}>{a.tag} →</Pill>
              </Panel>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <Panel delay={0.15} style={{ padding: 24 }}>
            <Eyebrow>Critical Approvals</Eyebrow>
            <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 10 }}>
              <div className="display" style={{ fontSize: 60, color: color("FINANCE") }}>{home.approvals.count}</div>
              <div>
                {home.approvals.items.map((t) => (
                  <div key={t} style={{ fontSize: 13, color: "var(--color-ink-200)" }}>{t}</div>
                ))}
                <div style={{ marginTop: 10 }}><Pill color={color("FINANCE")} onClick={() => router.push("/finance")}>Review all</Pill></div>
              </div>
            </div>
            <div className="mono" style={{ fontSize: 9.5, color: "var(--color-ink-500)", marginTop: 16 }}>nothing executes without you</div>
          </Panel>
          <Panel delay={0.2} style={{ padding: 24 }}>
            <Eyebrow>Notifications</Eyebrow>
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
              {home.notifications.map((n) => (
                <div key={n.text} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <Dot color={color(n.dept)} size={7} ring={false} />
                  <span style={{ fontSize: 12.5, color: "var(--color-ink-200)" }}>{n.text}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      {/* RIGHT — Saathi briefing */}
      <Panel delay={0.1} style={{ padding: 32, display: "flex", flexDirection: "column" }}>
        <Eyebrow>Saathi · Executive Briefing</Eyebrow>
        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0 4px" }}>
          <span className="pulse" style={{ width: 9, height: 9, borderRadius: "50%", background: "#8FB4FF", boxShadow: "0 0 12px #8FB4FF" }} />
          <span style={{ color: "var(--color-ink-400)", fontSize: 13 }}>{home.greeting || "Welcome back, Ajay."}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 14 }}>
          {home.briefing.map((b, i) => (
            <motion.div key={b} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + i * 0.08 }} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <span style={{ marginTop: 7, width: 4, height: 4, borderRadius: "50%", background: "#3E4A66" }} />
              <span style={{ fontSize: 13.5, color: "var(--color-ink-200)", lineHeight: 1.4 }}>{b}</span>
            </motion.div>
          ))}
        </div>
        <div style={{ height: 1, background: "var(--color-line)", margin: "24px 0" }} />
        <Eyebrow>Quick Actions</Eyebrow>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
          {home.quickActions.map((qa) => (
            <button key={qa.label} onClick={() => router.push(qa.route)}
              style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderRadius: 14,
                background: `${color(qa.dept)}17`, border: `1px solid ${color(qa.dept)}44`, cursor: "pointer", textAlign: "left" }}>
              <Dot color={color(qa.dept)} size={8} />
              <span style={{ fontSize: 13, color: "var(--color-ink-100)" }}>{qa.label}</span>
              <span style={{ marginLeft: "auto", color: "var(--color-ink-400)", fontSize: 15 }}>→</span>
            </button>
          ))}
        </div>
        <div style={{ height: 1, background: "var(--color-line)", margin: "24px 0" }} />
        <Eyebrow>Today</Eyebrow>
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12 }}>
          {home.calendar.map((c) => (
            <div key={c.time} style={{ display: "flex", gap: 18 }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)" }}>{c.time}</span>
              <span style={{ fontSize: 12.5, color: "var(--color-ink-200)" }}>{c.event}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
    </>
  );
}
