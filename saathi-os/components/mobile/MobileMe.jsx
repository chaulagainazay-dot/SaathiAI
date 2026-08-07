"use client";
import { useRouter } from "next/navigation";
import { Eyebrow } from "@/components/ui";
import { DEPARTMENTS } from "@/lib/departments";

const LINKS = [
  { label: "Finance", route: "/finance", dept: "FINANCE" },
  { label: "Cafeteria", route: "/cafeteria", dept: "CAFETERIA" },
  { label: "AI Studio", route: "/studio", dept: "AI STUDIO" },
  { label: "Knowledge Graph", route: "/knowledge", dept: "KNOWLEDGE" },
  { label: "Travel", route: "/travel", dept: "TRAVEL" },
  { label: "Learning", route: "/learning", dept: "LEARNING" },
];

export default function MobileMe() {
  const router = useRouter();
  return (
    <div className="m-page">
      <div className="m-card" style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 54, height: 54, borderRadius: "50%", background: "#DCE6FA", color: "#0A1120",
          display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 22,
          boxShadow: "0 0 22px rgba(143,180,255,0.5)" }}>A</div>
        <div>
          <div className="display" style={{ fontSize: 22 }}>Ajay Chaulagain</div>
          <div className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)" }}>CEO · Kathmandu</div>
        </div>
      </div>

      <Eyebrow style={{ padding: "4px 4px 0" }}>Departments</Eyebrow>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {LINKS.map((l) => (
          <button key={l.route} onClick={() => router.push(l.route)} className="m-card"
            style={{ display: "flex", alignItems: "center", gap: 12, padding: 16, cursor: "pointer", textAlign: "left" }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: DEPARTMENTS[l.dept]?.color,
              boxShadow: `0 0 10px ${DEPARTMENTS[l.dept]?.color}` }} />
            <span style={{ flex: 1, fontSize: 15, color: "var(--color-ink-100)" }}>{l.label}</span>
            <span style={{ color: "var(--color-ink-400)" }}>→</span>
          </button>
        ))}
      </div>

      <div className="m-card">
        <Eyebrow>Platform</Eyebrow>
        <div className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)", marginTop: 10, lineHeight: 1.7 }}>
          SaathiAI · v0.4.0-finance<br />
          Mobile = CEO Companion · Desktop = Control Center<br />
          Works offline · installable
        </div>
        <button onClick={() => router.push("/security")}
          style={{ marginTop: 12, background: "none", border: "none", color: "#9B6BFF", fontSize: 13, cursor: "pointer", padding: 0, fontWeight: 600 }}>
          🔐 Account Security →
        </button>
        <button onClick={() => router.push("/settings/voice")}
          style={{ marginTop: 10, display: "block", background: "none", border: "none", color: "#9B6BFF", fontSize: 13, cursor: "pointer", padding: 0, fontWeight: 600 }}>
          🎙 Voice Settings →
        </button>
      </div>
    </div>
  );
}
