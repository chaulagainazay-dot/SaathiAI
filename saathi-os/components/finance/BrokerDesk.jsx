"use client";
/**
 * Broker Accumulation / Distribution — from the exchange floorsheet (who traded what).
 * Shows top net buyers (accumulation) and net sellers (distribution). Observation-only.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const cr = (v) => (v == null ? "—" : (v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 2 }));

export default function BrokerDesk({ symbol: symbolProp } = {}) {
  const [symbol, setSymbol] = useState(symbolProp || "");
  const [input, setInput] = useState(symbolProp || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Follow a controlled symbol from the parent (e.g. AI Analysis workspace).
  useEffect(() => {
    if (symbolProp != null) { setSymbol(symbolProp); setInput(symbolProp); }
  }, [symbolProp]);

  const load = useCallback(async (sym) => {
    setLoading(true);
    const r = await api(`/api/nepse/floorsheet${sym ? `?symbol=${encodeURIComponent(sym)}` : ""}`);
    setData(r.ok ? r.body : { available: false, error: r.body?.reason || r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);
  useEffect(() => { load(symbol); }, [symbol, load]);

  const brokers = (data?.brokers || []).map((b) => ({ ...b, net: (b.buyAmount || 0) - (b.sellAmount || 0) }));
  const accumulation = [...brokers].filter((b) => b.net > 0).sort((a, b) => b.net - a.net).slice(0, 8);
  const distribution = [...brokers].filter((b) => b.net < 0).sort((a, b) => a.net - b.net).slice(0, 8);

  const Side = ({ title, rows, color }) => (
    <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "12px 14px" }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color, marginBottom: 8, fontWeight: 700 }}>{title}</div>
      {rows.length === 0 && <Text tone="muted" size="xs">None.</Text>}
      {rows.map((b, i) => (
        <div key={b.code || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, padding: "5px 0", borderBottom: i < rows.length - 1 ? "1px solid rgba(255,64,64,.07)" : "none" }}>
          <span style={{ color: "#dccfd3" }}><b style={{ color: "#f2e8ea" }}>{b.code}</b> {b.name}</span>
          <span style={{ color, fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{b.net > 0 ? "+" : ""}{cr(b.net)} Cr</span>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => { if (e.key === "Enter") setSymbol(input.trim()); }}
          placeholder="Filter by symbol (blank = whole market)"
          style={{ fontFamily: "inherit", fontSize: 12, padding: "7px 10px", borderRadius: 8, width: 240, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <Button size="sm" variant="secondary" onClick={() => setSymbol(input.trim())} disabled={loading}>{loading ? "…" : "Load"}</Button>
        {input && <Button size="sm" variant="ghost" onClick={() => { setInput(""); setSymbol(""); }}>Whole market</Button>}
        <div style={{ flexGrow: 1 }} />
        {data?.asOf && <Badge variant="soft" label={`as of ${data.asOf}`} />}
      </div>

      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && data && !data.available && <EmptyState title="Floorsheet unavailable" description={`${data.error || "no data"}. NEPSE floorsheet is published after market close.`} />}
      {!loading && data?.available && !data.traded && symbol && <EmptyState title={`No trades for ${symbol}`} description="No floorsheet activity on the latest day." />}
      {!loading && data?.available && brokers.length > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 12 }}>
            <Side title="ACCUMULATION · top net buyers" rows={accumulation} color="#2ee27a" />
            <Side title="DISTRIBUTION · top net sellers" rows={distribution} color="#ff4d4d" />
          </div>
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
            Net = buy − sell amount per broker{symbol ? ` for ${symbol}` : ""} · exchange floorsheet · observation-only, not advice.
            {data.directory?.text ? ` · ${data.directory.text}` : ""}
          </Text>
        </>
      )}
    </div>
  );
}
