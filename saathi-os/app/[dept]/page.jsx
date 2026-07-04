"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import { DEPARTMENTS } from "@/lib/departments";
import { Panel, Eyebrow, Pill } from "@/components/ui";

// Generic department workspace (Studio, Learning, Travel, Cafeteria, Crypto, …)
const SECTIONS = {
  studio: ["Projects", "Pipeline", "Scripts", "Discovery", "Publishing", "Analytics", "Revenue"],
  learning: ["Episodes", "Promotion Queue", "Capability Improvements", "Experiments", "Patterns"],
  cafeteria: ["Production", "Inventory", "Waste", "Forecast", "Revenue", "Staff", "Kitchen"],
  travel: ["Bookings", "Leads", "CRM", "Packages", "Marketing"],
  crypto: ["Signals", "Watchlist", "On-chain", "Sentiment", "Alerts"],
  discovery: ["SEO", "GEO", "Distribution", "Keywords", "Analytics"],
  opportunity: ["Discovery", "Scored Queue", "Memory", "Resurrections"],
  memory: ["Platform Memory", "Promotion", "Contradictions", "Evidence"],
  business: ["Departments", "KPIs", "Execution Score", "Briefings"],
};

const KEY = { studio: "AI STUDIO", learning: "LEARNING", cafeteria: "CAFETERIA", travel: "TRAVEL",
  crypto: "CRYPTO", discovery: "DISCOVERY", opportunity: "OPPORTUNITY", memory: "MEMORY", business: "BUSINESS" };

export default function DeptWorkspace({ params }) {
  const { dept } = use(params);
  const router = useRouter();
  const key = KEY[dept];
  const info = DEPARTMENTS[key];
  const sections = SECTIONS[dept] || ["Overview", "KPIs", "Tasks", "Timeline", "Analytics"];

  if (!info) {
    return (
      <div style={{ maxWidth: 800, margin: "80px auto", textAlign: "center" }}>
        <Panel style={{ padding: 48 }}>
          <Eyebrow>Not found</Eyebrow>
          <h2 className="display" style={{ fontSize: 26, margin: "12px 0 20px" }}>This workspace doesn't exist.</h2>
          <Pill color="#8FB4FF" onClick={() => router.push("/")}>Back to CEO Home</Pill>
        </Panel>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1620, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 26 }}>
        <span style={{ width: 14, height: 14, borderRadius: "50%", background: info.color, boxShadow: `0 0 16px ${info.color}` }} />
        <h1 className="display" style={{ fontSize: 26 }}>{info.name}</h1>
        <span className="eyebrow" style={{ marginLeft: 4 }}>Workspace</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 20 }}>
        {sections.map((s, i) => (
          <Panel key={s} delay={0.04 * i} style={{ padding: 24, minHeight: 150, display: "flex", flexDirection: "column" }}>
            <Eyebrow style={{ color: info.color }}>{s}</Eyebrow>
            <div style={{ flex: 1 }} />
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-500)" }}>ready</span>
              <span style={{ color: "var(--color-ink-400)" }}>→</span>
            </div>
          </Panel>
        ))}
      </div>
      <p className="mono" style={{ fontSize: 11, color: "var(--color-ink-500)", marginTop: 30, textAlign: "center" }}>
        {info.name} consumes the same platform capabilities — wired to the M1–M5 backend in the next milestone.
      </p>
    </div>
  );
}
