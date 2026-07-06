"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchMissions } from "@/lib/api";

const ACCENT = "#F4F6FB";
const DEPT_COLOR = {
  ai_studio: "#FF8A3D", pielts: "#6C3FCF", travel: "#5FC8FF", hcg: "#FF5A5A", cafeteria: "#4FD07A",
};
const TYPE_LABEL = {
  business: "Business", client: "Client", product: "Product", startup: "Startup",
  internal: "Internal", education: "Education", personal: "Personal",
};

export default function MissionsPage() {
  const router = useRouter();
  const [missions, setMissions] = useState([]);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchMissions().then((d) => setMissions(d.missions || [])).catch((e) => setErr(String(e))); }, []);

  return (
    <div className="only-desktop" style={{ maxWidth: 1080, margin: "0 auto", paddingBottom: 60 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Eyebrow style={{ color: "#9B6BFF" }}>SaathiOS · Missions</Eyebrow>
        <button onClick={() => router.push("/missions/new")}
          style={{ padding: "9px 18px", borderRadius: 12, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: "#9B6BFF" }}>＋ New Mission</button>
      </div>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>Mission Control</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 20 }}>
        Every business is a Mission — the root object. Directors work inside it · events, evidence and learning
        all share its namespace. One operating system, five instances.
      </div>

      {err && <div style={{ fontSize: 12, color: "#FF5A5A", marginBottom: 10 }}>{err}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {missions.map((m) => {
          const color = DEPT_COLOR[m.department] || "#9B6BFF";
          return (
            <Panel key={m.id} onClick={() => router.push(`/missions/${m.id}`)}
              style={{ padding: 18, cursor: "pointer", borderLeft: `3px solid ${color}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <div style={{ fontSize: 17, fontWeight: 600 }}>{m.name}</div>
                <span className="mono" style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999,
                  background: `${color}22`, color }}>{TYPE_LABEL[m.type] || m.type}</span>
              </div>
              <div className="mono" style={{ fontSize: 11, opacity: 0.5, marginTop: 3 }}>
                {m.key} · {m.department || "—"} · <span style={{ color: m.status === "active" ? "#00BFA5" : "#E8B84B" }}>{m.status}</span>
              </div>
              {m.objectives?.length > 0 && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 3 }}>
                  {m.objectives.slice(0, 3).map((o, i) => (
                    <div key={i} style={{ fontSize: 12, opacity: 0.7 }}>◦ {o}</div>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 10, fontSize: 10.5, opacity: 0.4 }}>
                {(m.directors || []).length} directors · open executive dashboard →
              </div>
            </Panel>
          );
        })}
      </div>
      {missions.length === 0 && !err && <div style={{ opacity: 0.4, fontSize: 13 }}>Seeding missions…</div>}
    </div>
  );
}
