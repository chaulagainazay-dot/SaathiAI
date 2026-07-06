"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { applyIntake, extractDocument } from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";
const ACCOUNTS = ["website", "facebook", "instagram", "tiktok", "youtube", "google_business", "telegram", "whatsapp"];

export default function IntakePage() {
  const { id } = useParams();
  const [acc, setAcc] = useState({});
  const [f, setF] = useState({ services: "", customers: "", goals: "", problems: "",
    revenue_amount: "", revenue_source: "", instagram_followers: "", facebook_followers: "" });
  const [doc, setDoc] = useState({ title: "", text: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const payload = {
        accounts: Object.fromEntries(Object.entries(acc).filter(([, v]) => v)),
        social_stats: { instagram_followers: f.instagram_followers || undefined,
                        facebook_followers: f.facebook_followers || undefined },
        revenue: f.revenue_amount ? { amount: Number(f.revenue_amount), source: f.revenue_source } : undefined,
        services: f.services, customers: f.customers, goals: f.goals, problems: f.problems,
      };
      const out = await applyIntake(id, payload);
      let cov = out.coverage;
      if (doc.text.trim()) { const d = await extractDocument(id, doc.title, doc.text); cov = d.coverage; }
      setRes({ ...out, coverage: cov });
    } catch (e) { setErr(`${e} — login may be required`); }
    finally { setBusy(false); }
  };

  const inp = { width: "100%", padding: "9px 11px", borderRadius: 9, fontSize: 13,
    border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };

  return (
    <div className="page" style={{ maxWidth: 720, margin: "0 auto", paddingBottom: 60 }}>
      <a href={`/missions/${id}`} style={{ fontSize: 12, opacity: 0.5, textDecoration: "none", color: "inherit" }}>← Mission</a>
      <Eyebrow style={{ color: ACCENT, marginTop: 8 }}>Mission Intake</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 4px" }}>Fill the business memory</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Every field becomes a Knowledge Graph node and raises coverage immediately — no OAuth. Two minutes here
        beats a week of connectors.
      </div>

      {res && <Panel style={{ padding: 14, marginBottom: 14, borderLeft: `3px solid ${TEAL}` }}>
        <div style={{ fontSize: 14 }}>✓ Added {res.nodes_added} nodes · Knowledge coverage now
          <b style={{ color: TEAL }}> {Math.round((res.coverage || 0) * 100)}%</b></div>
        <a href={`/missions/${id}`} style={{ fontSize: 12, color: ACCENT, textDecoration: "none" }}>← back to mission</a>
      </Panel>}
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      <Panel style={{ padding: 18, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Accounts / channels</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
          {ACCOUNTS.map((a) => (
            <input key={a} placeholder={a.replace("_", " ")} value={acc[a] || ""}
              onChange={(e) => setAcc({ ...acc, [a]: e.target.value })} style={inp} />
          ))}
        </div>
      </Panel>

      <Panel style={{ padding: 18, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Business</Eyebrow>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
          <input placeholder="Services (comma separated)" value={f.services} onChange={set("services")} style={inp} />
          <input placeholder="Customer segments" value={f.customers} onChange={set("customers")} style={inp} />
          <input placeholder="Goals" value={f.goals} onChange={set("goals")} style={inp} />
          <input placeholder="Problems" value={f.problems} onChange={set("problems")} style={inp} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <input placeholder="Revenue amount (NPR)" value={f.revenue_amount} onChange={set("revenue_amount")} style={inp} />
            <input placeholder="Revenue source" value={f.revenue_source} onChange={set("revenue_source")} style={inp} />
            <input placeholder="Instagram followers" value={f.instagram_followers} onChange={set("instagram_followers")} style={inp} />
            <input placeholder="Facebook followers" value={f.facebook_followers} onChange={set("facebook_followers")} style={inp} />
          </div>
        </div>
      </Panel>

      <Panel style={{ padding: 18, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Paste a document (price list, brochure, proposal)</Eyebrow>
        <input placeholder="Title" value={doc.title} onChange={(e) => setDoc({ ...doc, title: e.target.value })} style={{ ...inp, marginTop: 10 }} />
        <textarea placeholder="Paste text — prices, emails, phones get extracted into the graph"
          value={doc.text} onChange={(e) => setDoc({ ...doc, text: e.target.value })}
          style={{ ...inp, marginTop: 8, minHeight: 90, fontFamily: "inherit" }} />
      </Panel>

      <button onClick={submit} disabled={busy}
        style={{ padding: "12px 20px", borderRadius: 12, border: "none", cursor: "pointer",
          fontWeight: 600, color: "#fff", background: ACCENT, opacity: busy ? 0.6 : 1, width: "100%" }}>
        {busy ? "Saving to business memory…" : "Save Intake → raise coverage"}</button>
    </div>
  );
}
