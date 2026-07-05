"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { fetchIntakeForm, submitIntakeForm } from "@/lib/api";

const PURPLE = "#6C3FCF", TEAL = "#00BFA5";
const field = { width: "100%", padding: "12px 14px", borderRadius: 10, fontSize: 15, marginTop: 6,
  border: "1px solid rgba(255,255,255,0.14)", background: "rgba(255,255,255,0.05)", color: "inherit" };

export default function ClientForm() {
  const { token } = useParams();
  const [data, setData] = useState({ company: {} });
  const [state, setState] = useState("loading");   // loading|form|done|invalid
  useEffect(() => {
    fetchIntakeForm(token)
      .then((d) => { setData(d.data && d.data.company ? d.data : { company: {} }); setState(d.status === "submitted" ? "done" : "form"); })
      .catch(() => setState("invalid"));
  }, [token]);

  const set = (k, v, sub) => setData((d) => sub
    ? { ...d, [sub]: { ...(d[sub] || {}), [k]: v } } : { ...d, [k]: v });
  const submit = async () => { await submitIntakeForm(token, data).catch(() => {}); setState("done"); };

  if (state === "loading") return <Center>Loading…</Center>;
  if (state === "invalid") return <Center>This link is not valid.</Center>;
  if (state === "done") return <Center><div style={{ fontSize: 40 }}>✓</div><div style={{ marginTop: 8 }}>Thank you! Your details were submitted.</div><div style={{ opacity: 0.5, fontSize: 13, marginTop: 6 }}>We'll research and prepare your strategy.</div></Center>;

  const co = data.company || {};
  return (
    <div style={{ maxWidth: 560, margin: "0 auto", padding: "32px 20px" }}>
      <div style={{ fontSize: 26, fontWeight: 700, color: PURPLE }}>Tell us about your company</div>
      <div style={{ fontSize: 14, opacity: 0.6, marginBottom: 24 }}>A few details so we can research and build your strategy.</div>
      {[["Company Name", "name"], ["Website", "website"], ["Industry / Niche", "industry"], ["Location", "location"], ["Contact Person", "contact"], ["Email", "email"], ["Phone", "phone"]].map(([label, k]) => (
        <label key={k} style={{ display: "block", fontSize: 12, opacity: 0.6, marginBottom: 14 }}>{label}
          <input style={field} value={co[k] || ""} onChange={(e) => set(k, e.target.value, "company")} /></label>
      ))}
      {[["What does your company do?", "description"], ["Your goals", "goals"], ["Target audience", "audience"], ["Services", "services"], ["Budget & timeline", "budget"]].map(([label, k]) => (
        <label key={k} style={{ display: "block", fontSize: 12, opacity: 0.6, marginBottom: 14 }}>{label}
          <textarea style={{ ...field, minHeight: 56 }} value={data[k] || ""} onChange={(e) => set(k, e.target.value)} /></label>
      ))}
      <button onClick={submit} style={{ width: "100%", marginTop: 10, padding: "14px", borderRadius: 12,
        border: "none", fontWeight: 700, fontSize: 15, color: "#fff", background: PURPLE, cursor: "pointer" }}>Submit</button>
    </div>
  );
}

function Center({ children }) {
  return <div style={{ minHeight: "60vh", display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", textAlign: "center", padding: 20 }}>{children}</div>;
}
