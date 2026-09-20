"use client";
/**
 * Market News (from the research surface) and Signals (deterministic setup scan). Both
 * observation-only; signals are ATR trend setups, not advice. Honest empty states.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}

export function MarketNews() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { (async () => { const r = await api("/api/v1/research/events?limit=8"); setData(r.ok ? r.body : { error: r.body?.error || `HTTP ${r.status}` }); setLoading(false); })(); }, []);
  const events = data?.events || [];
  return (
    <div style={{ padding: 14 }}>
      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && events.length === 0 && (
        <EmptyState title="No research events" description={data?.error ? `Feed: ${data.error}` : "No official market research events right now."} />
      )}
      {!loading && events.map((e, i) => {
        const head = e.headline || e.title || e.summary || "(event)";
        const src = e.source || e.source_name || e.provider || "";
        const when = e.published || e.created_at || e.observed_at || e.date || "";
        return (
          <div key={e.event_id || e.id || i} style={{ padding: "9px 0", borderBottom: i < events.length - 1 ? "1px solid rgba(255,64,64,.07)" : "none" }}>
            <div style={{ fontSize: 13, color: "#f2e8ea", lineHeight: 1.4 }}>{head}</div>
            {(src || when) && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 3 }}>{[src, typeof when === "string" ? when.slice(0, 16) : ""].filter(Boolean).join(" · ")}</Text>}
          </div>
        );
      })}
      {!loading && events.length > 0 && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Read-only market research · not advice.</Text>}
    </div>
  );
}

export function TradingSignals() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { setLoading(true); const r = await api("/api/v1/market/signals"); setData(r.ok ? r.body : { error: r.body?.error || `HTTP ${r.status}` }); setLoading(false); }, []);
  useEffect(() => { load(); }, [load]);
  const signals = data?.signals || [];
  return (
    <div style={{ padding: 14 }}>
      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && signals.length === 0 && (
        <EmptyState title="No setups right now" description={data?.error ? `Scan: ${data.error}` : `Scanned ${data?.scanned ?? 0} symbols — no clean ATR trend setup currently.`} />
      )}
      {!loading && signals.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: i < signals.length - 1 ? "1px solid rgba(255,64,64,.07)" : "none" }}>
          <span style={{ fontWeight: 700, fontSize: 13, minWidth: 64 }}>{s.symbol}</span>
          <span style={{ color: "#8f8288", fontSize: 11 }}>{s.market}</span>
          <Badge variant="soft" color={s.side === "LONG" ? "#2ee27a" : "#ff4d4d"} label={s.side} />
          <div style={{ flexGrow: 1 }} />
          <Text tone="muted" size="xs" mono>E {s.entry} · SL {s.stop} · TP {s.target} · {s.rr}R</Text>
        </div>
      ))}
      {!loading && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Deterministic ATR trend setups · observation-only · not advice.</Text>}
    </div>
  );
}
