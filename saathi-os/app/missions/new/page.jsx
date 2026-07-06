"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { createMissionTwin } from "@/lib/api";

const ACCENT = "#9B6BFF";
const TYPES = ["business", "client", "product", "startup", "internal", "education", "personal"];

export default function NewMission() {
  const router = useRouter();
  const [f, setF] = useState({ name: "", type: "client", industry: "", website: "", goals: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.name.trim()) { setErr("Name required"); return; }
    setBusy(true); setErr(null);
    try {
      const res = await createMissionTwin(f);
      if (res.ok) router.push(`/missions/${res.id}`);
      else setErr(res.error || "failed");
    } catch (e) { setErr(`${e} — you may need to be logged in`); }
    finally { setBusy(false); }
  };

  return (
    <div className="page" style={{ maxWidth: 620, margin: "0 auto", paddingBottom: 60 }}>
      <a href="/missions" style={{ fontSize: 12, opacity: 0.5, textDecoration: "none", color: "inherit" }}>← Missions</a>
      <Eyebrow style={{ color: ACCENT, marginTop: 8 }}>SaathiOS · New Mission</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 4px" }}>Onboard a business</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 18 }}>
        Saathi will research the live site, provision departments, and generate an executive briefing +
        30-day roadmap — a Business Digital Twin, not an empty folder.
      </div>

      <Panel style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        {[["Business name", "name", "Grow Surmount Travels"],
          ["Industry", "industry", "Travel agency"],
          ["Website", "website", "https://…"],
          ["12-month goal", "goals", "More bookings from Instagram"]].map(([label, key, ph]) => (
          <label key={key} style={{ fontSize: 12.5 }}>
            <div style={{ opacity: 0.6, marginBottom: 4 }}>{label}</div>
            <input value={f[key]} onChange={set(key)} placeholder={ph}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 10, fontSize: 13,
                border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }} />
          </label>
        ))}
        <label style={{ fontSize: 12.5 }}>
          <div style={{ opacity: 0.6, marginBottom: 4 }}>Type</div>
          <select value={f.type} onChange={set("type")}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, fontSize: 13,
              border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }}>
            {TYPES.map((t) => <option key={t} value={t} style={{ color: "#000" }}>{t}</option>)}
          </select>
        </label>
        {err && <div style={{ fontSize: 12, color: "#FF5A5A" }}>{err}</div>}
        <button onClick={submit} disabled={busy}
          style={{ padding: "12px", borderRadius: 12, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: ACCENT, opacity: busy ? 0.6 : 1 }}>
          {busy ? "Researching + building twin…" : "Create Mission"}</button>
      </Panel>
    </div>
  );
}
