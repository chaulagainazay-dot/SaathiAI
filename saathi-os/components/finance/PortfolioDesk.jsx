"use client";
/**
 * Portfolio Desk — add, track, analyse, recommend, research the owner's holdings. Live
 * valuation from the free market source; deterministic analysis + recommendations. No orders.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const npr = (v) => (v == null ? "—" : "NPR " + Math.round(v).toLocaleString("en-IN"));

export default function PortfolioDesk() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({ symbol: "", market: "NEPSE", qty: "", avg_cost: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const r = await api("/api/v1/finance/portfolio/analysis");
    setData(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!f.symbol.trim() || !f.qty) { setMsg("Enter a symbol and quantity."); return; }
    setBusy(true); setMsg("Adding & valuing…");
    const r = await api("/api/v1/finance/portfolio/add", { method: "POST", body: JSON.stringify({ symbol: f.symbol.trim(), market: f.market, qty: parseFloat(f.qty), avg_cost: parseFloat(f.avg_cost || 0) }) });
    if (r.ok && r.body?.ok) {
      setMsg(`Added ${f.symbol.trim()}.`);
      setF({ symbol: "", market: f.market, qty: "", avg_cost: "" });
      await load();
    } else {
      setMsg(r.body?.error || "Add failed — check you're signed in.");
    }
    setBusy(false);
  };
  const remove = async (id) => { setBusy(true); setMsg("Removing…"); await api("/api/v1/finance/portfolio/remove", { method: "POST", body: JSON.stringify({ id }) }); await load(); setMsg(""); setBusy(false); };

  const t = data?.totals || {};
  const inp = { fontFamily: "inherit", fontSize: 12, padding: "7px 10px", borderRadius: 8, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" };

  return (
    <div style={{ padding: 14 }}>
      {/* Add */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["NEPSE", "CRYPTO"].map((m) => (
            <button key={m} onClick={() => setF((o) => ({ ...o, market: m }))} style={{ fontFamily: "inherit", fontSize: 11, padding: "6px 10px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: f.market === m ? "#ff2a2a" : "transparent", color: f.market === m ? "#08060a" : "#b7a8ad", fontWeight: 700 }}>{m}</button>
          ))}
        </div>
        <input style={{ ...inp, width: 110 }} placeholder="Symbol" value={f.symbol} onChange={(e) => setF((o) => ({ ...o, symbol: e.target.value.toUpperCase() }))} />
        <input style={{ ...inp, width: 90 }} placeholder="Qty" value={f.qty} onChange={(e) => setF((o) => ({ ...o, qty: e.target.value }))} />
        <input style={{ ...inp, width: 110 }} placeholder="Avg cost" value={f.avg_cost} onChange={(e) => setF((o) => ({ ...o, avg_cost: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />
        <Button size="sm" onClick={add} disabled={busy}>{busy ? "Working…" : "Add holding"}</Button>
        {(busy || msg) && <Text tone="muted" size="xs" style={{ display: "flex", alignItems: "center", gap: 6 }}>{busy && <Spinner size={12} />}{msg}</Text>}
      </div>

      {loading && !data && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && data && !data.available && <EmptyState title="Portfolio unavailable" description={data.error || "sign in"} />}
      {!loading && data?.empty && <EmptyState title="No holdings yet" description="Add a position above to track and analyse your portfolio." />}

      {!loading && data?.available && !data.empty && (
        <>
          {/* Totals */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 10, marginBottom: 14 }}>
            <Tile label="Value" value={npr(t.value)} />
            <Tile label="Unrealized P/L" value={t.pl != null ? `${t.pl >= 0 ? "+" : ""}${npr(t.pl)}` : "—"} tone={(t.pl ?? 0) >= 0 ? "up" : "down"} />
            <Tile label="Return" value={t.pl_pct != null ? `${t.pl_pct >= 0 ? "+" : ""}${t.pl_pct}%` : "—"} tone={(t.pl_pct ?? 0) >= 0 ? "up" : "down"} big />
            <Tile label="Concentration" value={t.concentration != null ? `${t.concentration}% ${t.top_name || ""}` : "—"} tone={t.concentration > 35 ? "warn" : ""} />
            <Tile label="Max drawdown" value={t.max_drawdown_pct != null ? `${t.max_drawdown_pct}%` : `— (${t.nav_points || 0} pts)`} tone="down" />
          </div>

          {/* Risk engine */}
          {data.risk && !data.risk.engine_error && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
              <Badge variant="soft" label={`largest ${data.risk.largest_position_pct ?? "—"}%`} color={data.risk.largest_position_pct > 35 ? "#ffab3d" : "var(--status-neutral)"} />
              <Badge variant="soft" label={`gross exposure ${data.risk.gross_exposure_pct ?? "—"}%`} />
              {data.risk.current_drawdown_pct != null && <Badge variant="soft" color="#ff4d4d" label={`drawdown ${data.risk.current_drawdown_pct}%`} />}
              <Text tone="disabled" size="xs">risk: {data.risk.engine}</Text>
            </div>
          )}

          {/* Holdings */}
          <div style={{ overflowX: "auto", marginBottom: 14 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>{["Symbol", "Qty", "Avg", "LTP", "Value", "P/L %", "Weight", ""].map((h, i) => (
                <th key={h} style={{ textAlign: i === 0 ? "left" : "right", fontSize: 10, letterSpacing: ".05em", textTransform: "uppercase", color: "#8f8288", fontWeight: 600, padding: "8px 10px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
              ))}</tr></thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr key={p.id}>
                    <td style={{ padding: "8px 10px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{p.symbol}<span style={{ color: "#8f8288", fontWeight: 400 }}> · {p.market}</span></td>
                    {[p.qty, p.avg_cost, p.price, p.value != null ? Math.round(p.value).toLocaleString("en-IN") : "—"].map((v, i) => (
                      <td key={i} style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{v ?? "—"}</td>
                    ))}
                    <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: (p.pl_pct ?? 0) >= 0 ? "#2ee27a" : "#ff4d4d", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{p.pl_pct == null ? "—" : `${p.pl_pct >= 0 ? "+" : ""}${p.pl_pct}%`}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#b7a8ad", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{p.weight != null ? `${p.weight}%` : "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", borderBottom: "1px solid rgba(255,64,64,.07)" }}><button onClick={() => remove(p.id)} style={{ background: "transparent", border: "none", color: "#8f8288", cursor: "pointer", fontSize: 13 }}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Rebalance engine */}
          {data.rebalance?.available && (data.rebalance.trades || []).length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>
                REBALANCE PROPOSAL · equal-weight · cash target {data.rebalance.cash_weight_pct}% · {data.rebalance.engine}
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead><tr>{["Symbol", "Action", "Current", "Target", "Δ Weight", "≈ Qty"].map((h, i) => (
                    <th key={h} style={{ textAlign: i < 2 ? "left" : "right", fontSize: 10, letterSpacing: ".05em", textTransform: "uppercase", color: "#8f8288", fontWeight: 600, padding: "7px 10px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
                  ))}</tr></thead>
                  <tbody>
                    {data.rebalance.trades.map((t, i) => (
                      <tr key={i}>
                        <td style={{ padding: "7px 10px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.06)" }}>{t.symbol}</td>
                        <td style={{ padding: "7px 10px", borderBottom: "1px solid rgba(255,64,64,.06)", color: t.action === "BUY" ? "#2ee27a" : t.action === "SELL" ? "#ff4d4d" : "#8f8288", fontWeight: 600 }}>{t.action}</td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#b7a8ad", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{t.current_weight}%</td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{t.target_weight}%</td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: (t.weight_delta ?? 0) >= 0 ? "#2ee27a" : "#ff4d4d", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{t.weight_delta >= 0 ? "+" : ""}{t.weight_delta}%</td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#8f8288", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{t.qty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>
                Target weights from the fund construction policy (per-position + cash-buffer caps){data.rebalance.warnings?.length ? ` · ${data.rebalance.warnings.join(", ")}` : ""} · proposal only, not advice.
              </Text>
            </div>
          )}

          {/* Recommendations */}
          <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>RECOMMENDATIONS · research only, not advice</div>
          {(data.recommendations || []).map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "8px 0", borderBottom: "1px solid rgba(255,64,64,.06)" }}>
              <Badge variant="soft" color={/RISK|drawdown/i.test(r.tag) ? "#ff4d4d" : /REVIEW|OVERWEIGHT/i.test(r.tag) ? "#ffab3d" : /setup|OBSERVATION/i.test(r.tag) ? "#4fb0c6" : "#2ee27a"} label={r.tag} />
              <Text tone="muted" size="xs" style={{ flex: 1, lineHeight: 1.5 }}>{r.text}</Text>
            </div>
          ))}
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>{data.note}</Text>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, tone, big }) {
  const col = tone === "up" ? "#2ee27a" : tone === "down" ? "#ff4d4d" : tone === "warn" ? "#ffab3d" : "#f2e8ea";
  return (
    <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: big ? 22 : 15, fontWeight: 700, marginTop: 3, color: col, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}
