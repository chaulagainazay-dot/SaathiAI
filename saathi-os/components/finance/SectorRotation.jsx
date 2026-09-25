"use client";
/**
 * Portfolio Sector Rotation — your sector mix vs live market sector momentum, flagging where
 * capital may be misallocated (overweight in fading sectors) or missing (absent from leaders).
 * Research/observation only, not advice.
 */
import { useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const SIG = { "WELL-POSITIONED": "#2ee27a", MISALLOCATED: "#ff4d4d", WATCH: "#ffab3d", NEUTRAL: "#8f8288" };
const TIER = { LEADING: "#2ee27a", LAGGING: "#ff4d4d", NEUTRAL: "#8f8288" };
const mom = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`);

export default function SectorRotation() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { (async () => { const r = await api("/api/v1/finance/portfolio/sector-rotation"); setData(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` }); setLoading(false); })(); }, []);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>;
  if (!data?.available) return <div style={{ padding: 14 }}><EmptyState title="Sector rotation unavailable" description={data?.error || "no data"} /></div>;
  if (data.empty) return <div style={{ padding: 14 }}><EmptyState title="No holdings" description={data.note} /></div>;

  const maxW = Math.max(...data.sectors.map((s) => s.weight), 1);
  return (
    <div style={{ padding: 14 }}>
      {/* momentum vs market */}
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <Stat k="Your capital momentum" v={mom(data.portfolio_momentum)} c={data.portfolio_momentum >= data.market_momentum ? "#2ee27a" : "#ffab3d"} big />
        <Stat k="Market momentum" v={mom(data.market_momentum)} />
        <Badge variant="soft" color={data.portfolio_momentum >= data.market_momentum ? "#2ee27a" : "#ffab3d"}
          label={data.portfolio_momentum >= data.market_momentum ? "AHEAD OF MARKET" : "BEHIND MARKET"} />
      </div>

      <Text tone="muted" size="sm" style={{ display: "block", marginBottom: 12, lineHeight: 1.6 }}>{data.summary}</Text>

      {/* sector allocation vs momentum */}
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>YOUR SECTORS · weight vs momentum</div>
      {data.sectors.map((s) => (
        <div key={s.sector} style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#f2e8ea" }}>{s.sector}</span>
            <span style={{ fontSize: 11, color: "#8f8288", fontVariantNumeric: "tabular-nums" }}>{s.weight}%</span>
            <Badge variant="soft" color={TIER[s.tier]} label={`${s.tier} · ${mom(s.momentum)}${s.rank ? ` · #${s.rank}` : ""}`} />
            <div style={{ flexGrow: 1 }} />
            <Badge variant="soft" color={SIG[s.signal]} label={s.signal} />
          </div>
          <div style={{ height: 8, background: "#140e15", borderRadius: 100, overflow: "hidden" }}>
            <div style={{ width: `${(s.weight / maxW) * 100}%`, height: "100%", background: SIG[s.signal] }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
            <Text tone="disabled" size="xs">{(s.symbols || []).join(", ")}</Text>
            <Text tone="disabled" size="xs">{s.note}</Text>
          </div>
        </div>
      ))}

      {/* opportunities */}
      {data.opportunities?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>LEADING SECTORS YOU'RE ABSENT FROM</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {data.opportunities.map((o) => (
              <div key={o.sector} style={{ background: "#0b0709", border: "1px solid rgba(46,226,122,.35)", borderRadius: 8, padding: "8px 10px" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#2ee27a" }}>{o.sector} <span style={{ color: "#8f8288", fontWeight: 400 }}>{mom(o.momentum)} · #{o.rank}</span></div>
                {o.top?.length > 0 && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 2 }}>e.g. {o.top.join(", ")}</Text>}
              </div>
            ))}
          </div>
        </div>
      )}
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 12 }}>{data.disclaimer}</Text>
    </div>
  );
}

function Stat({ k, v, c, big }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>{k}</div>
      <div style={{ fontSize: big ? 20 : 15, fontWeight: 700, color: c || "#f2e8ea", fontVariantNumeric: "tabular-nums" }}>{v}</div>
    </div>
  );
}
