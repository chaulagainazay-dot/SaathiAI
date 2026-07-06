"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchProposal, generateProposal, decideProposal } from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A";

export default function ProposalPage() {
  const { id } = useParams();
  const [pkg, setPkg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const load = () => fetchProposal(id).then((d) => setPkg(d.proposal)).catch(() => {});
  useEffect(() => { load(); }, [id]);

  const gen = () => { setBusy(true); setErr(null);
    generateProposal(id).then((d) => setPkg(d.proposal)).catch((e) => setErr(`${e} — login may be required`)).finally(() => setBusy(false)); };
  const decide = (a) => decideProposal(id, a).then(load).catch((e) => setErr(String(e)));

  const money = (n) => `NPR ${Number(n).toLocaleString()}`;
  const s = pkg?.sections;

  return (
    <div className="only-desktop" style={{ maxWidth: 820, margin: "0 auto", paddingBottom: 60 }}>
      <a href={`/missions/${id}`} style={{ fontSize: 12, opacity: 0.5, textDecoration: "none", color: "inherit" }}>← Mission</a>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 8 }}>
        <div>
          <Eyebrow style={{ color: ACCENT }}>Proposal Director</Eyebrow>
          <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>Business Proposal Package</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {pkg && <button onClick={() => window.print()} style={btn("#8FA0C4", true)}>Print / PDF</button>}
          <button onClick={gen} disabled={busy} style={btn(ACCENT)}>{busy ? "Building…" : pkg ? "Regenerate" : "Generate Proposal"}</button>
        </div>
      </div>
      {err && <div style={{ fontSize: 12, color: RED, marginTop: 8 }}>{err}</div>}

      {!pkg && !busy && <Panel style={{ padding: 28, marginTop: 16, textAlign: "center", opacity: 0.6 }}>
        No proposal yet. Generate one from the Mission's digital twin.</Panel>}

      {s && <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        {/* status + client */}
        <Panel style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{pkg.client}</div>
            <span className="mono" style={{ fontSize: 11, padding: "3px 10px", borderRadius: 999,
              background: pkg.status === "accepted" ? `${TEAL}22` : "rgba(255,255,255,0.06)",
              color: pkg.status === "accepted" ? TEAL : "inherit" }}>{pkg.status}</span>
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 12.5 }}>
            <span>Health <b>{Math.round((s.executive_summary.business_health || 0) * 100)}%</b></span>
            <span>Confidence <b>{Math.round((s.executive_summary.mission_confidence || 0) * 100)}%</b></span>
            <span style={{ opacity: 0.6 }}>{s.executive_summary.industry}</span>
          </div>
          {pkg.status === "draft" && (
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button onClick={() => decide(true)} style={btn(TEAL)}>✓ Client Approves → Execute</button>
              <button onClick={() => decide(false)} style={btn(RED, true)}>Reject</button>
            </div>
          )}
        </Panel>

        <Sect title="Current Problems" color={RED}>
          {s.current_problems.map((p, i) => <li key={i}>{p}</li>)}
        </Sect>
        <Sect title="Opportunities" color={AMBER}>
          {s.opportunities.map((o, i) => <li key={i}>{o}</li>)}
        </Sect>
        <Sect title="Recommended Services" color={ACCENT}>
          {s.recommended_services.map((x, i) => <li key={i}>{x}</li>)}
        </Sect>

        {/* pricing */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>Pricing {s.pricing.estimate ? "· estimate" : ""}</Eyebrow>
          <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
            {s.pricing.tiers.map((t) => (
              <div key={t.name} className="glass" style={{ flex: 1, padding: 14, borderRadius: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: ACCENT }}>{t.name}</div>
                <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{money(t.price)}</div>
                <div style={{ fontSize: 10.5, opacity: 0.55, marginTop: 4 }}>{t.note}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, fontSize: 11.5, opacity: 0.6 }}>
            {s.pricing.line_items.map((li) => <div key={li.item}>· {li.item} — {money(li.price)}</div>)}
          </div>
          <div style={{ fontSize: 10.5, opacity: 0.45, marginTop: 6 }}>{s.pricing.note}</div>
        </Panel>

        {/* ROI (honest projection) */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>ROI · projection</Eyebrow>
          <div style={{ fontSize: 12.5, marginTop: 8 }}>
            <div>Expected leads: {s.roi.expected_leads}</div>
            <div>Revenue focus: {s.roi.expected_revenue}</div>
            <div>Payback: {s.roi.payback_period}</div>
          </div>
          <div style={{ fontSize: 11, color: AMBER, marginTop: 8 }}>⚠ {s.roi.caveat}</div>
        </Panel>

        {/* timeline 90-day */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>Deliverables · 90 days</Eyebrow>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 8 }}>
            {Object.entries(s.deliverables || {}).map(([mo, items]) => (
              <div key={mo}>
                <div style={{ fontSize: 12, fontWeight: 600, color: ACCENT }}>{mo}</div>
                {(items || []).map((it, i) => <div key={i} style={{ fontSize: 11, opacity: 0.7 }}>◦ {it}</div>)}
              </div>
            ))}
          </div>
        </Panel>

        <Sect title="KPIs to track" color={TEAL}>{s.kpis.map((x, i) => <li key={i}>{x}</li>)}</Sect>

        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>Contract & Invoice</Eyebrow>
          <ul style={{ fontSize: 12.5, marginTop: 8, paddingLeft: 18 }}>
            {s.contract.terms.map((t, i) => <li key={i} style={{ padding: "2px 0" }}>{t}</li>)}
          </ul>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 6 }}>
            Invoice: {s.invoice.advance_pct}% advance ({s.invoice.currency}) · {s.invoice.note}</div>
          <div style={{ fontSize: 12, marginTop: 8 }}>📅 Next: {s.next_meeting.purpose} — {s.next_meeting.suggested}</div>
        </Panel>
      </div>}
    </div>
  );
}

function Sect({ title, color, children }) {
  return (
    <Panel style={{ padding: 18 }}>
      <Eyebrow style={{ color }}>{title}</Eyebrow>
      <ul style={{ fontSize: 12.5, marginTop: 8, paddingLeft: 18 }}>{children}</ul>
    </Panel>
  );
}

const btn = (color, outline) => ({
  padding: "9px 16px", borderRadius: 11, cursor: "pointer", fontWeight: 600, fontSize: 12.5,
  border: outline ? `1px solid ${color}` : "none", background: outline ? "transparent" : color,
  color: outline ? color : "#fff",
});
