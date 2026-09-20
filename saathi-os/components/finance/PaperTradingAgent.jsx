"use client";
/**
 * Paper Trading Agent — SIMULATION ONLY (no broker, no real orders). Self-contained: loads the
 * journal, shows success rate + stats, and runs / evaluates dummy trades. Reused by the Command
 * Deck and the /command-deck/guardian page.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}

export default function PaperTradingAgent({ market = "NEPSE", symbol = "NABIL" }) {
  const [journal, setJournal] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const r = await api("/api/v1/trading/paper/journal?limit=20");
    if (r.ok) setJournal(r.body);
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setBusy("run"); setMsg("");
    const r = await api("/api/v1/trading/paper/open", { method: "POST", body: JSON.stringify({ market, symbol }) });
    if (r.ok && r.body?.status === "OPEN") setMsg(`Opened dummy ${r.body.side} ${r.body.symbol} @ ${r.body.entry}`);
    else if (r.ok && r.body?.setup === false) setMsg(`No clean setup for ${symbol}: ${r.body.reason}`);
    else setMsg(r.body?.error || "Run failed");
    await load(); setBusy("");
  };
  const evaluate = async () => {
    setBusy("eval"); setMsg("");
    const r = await api("/api/v1/trading/paper/evaluate", { method: "POST", body: "{}" });
    if (r.ok) setMsg(`Evaluated ${r.body.evaluated} open · closed ${r.body.closed?.length || 0}`);
    await load(); setBusy("");
  };

  const s = journal?.stats;
  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 10 }}>
        <Tile label="Success rate" value={s?.win_rate != null ? `${s.win_rate}%` : "—"} big tone={s?.win_rate == null ? "muted" : s.win_rate >= 50 ? "up" : "down"} />
        <Tile label="Wins / Losses" value={`${s?.won ?? 0} / ${s?.lost ?? 0}`} />
        <Tile label="Open" value={String(s?.open ?? 0)} />
        <Tile label="Total R" value={s?.total_r != null ? `${s.total_r > 0 ? "+" : ""}${s.total_r}R` : "—"} tone={(s?.total_r ?? 0) >= 0 ? "up" : "down"} />
        <Tile label="Expectancy" value={s?.expectancy_r != null ? `${s.expectancy_r}R` : "—"} />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
        <Button size="sm" onClick={run} disabled={busy === "run"}>{busy === "run" ? "Running…" : `Run agent on ${market} ${symbol}`}</Button>
        <Button size="sm" variant="secondary" onClick={evaluate} disabled={busy === "eval"}>{busy === "eval" ? "Evaluating…" : "Evaluate open trades"}</Button>
        {msg && <Text tone="muted" size="xs">{msg}</Text>}
      </div>
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
        Opens a dummy trade only on a clean ATR trend setup (else skips), marks it to the live price — win on target, loss on stop. No broker, no real money.
      </Text>
      {(journal?.trades || []).length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>{["Symbol", "Side", "Entry", "Stop", "Target", "Now/Exit", "R", "Status"].map((h, i) => (
              <th key={h} style={{ textAlign: i < 2 ? "left" : "right", fontSize: 10, letterSpacing: ".06em", textTransform: "uppercase", color: "#8f8288", fontWeight: 500, padding: "8px 12px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
            ))}</tr></thead>
            <tbody>
              {journal.trades.map((t) => {
                const sc = t.status === "WON" ? "#2ee27a" : t.status === "LOST" ? "#ff4d4d" : "#ffab3d";
                return (
                  <tr key={t.id}>
                    <td style={{ padding: "8px 12px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{t.symbol}<span style={{ color: "#8f8288", fontWeight: 400 }}> · {t.market}</span></td>
                    <td style={{ padding: "8px 12px", borderBottom: "1px solid rgba(255,64,64,.07)", color: t.side === "LONG" ? "#2ee27a" : "#ff4d4d" }}>{t.side}</td>
                    {[t.entry, t.stop, t.target, t.exit_price ?? t.last_price ?? "—", t.r_multiple != null ? `${t.r_multiple > 0 ? "+" : ""}${t.r_multiple}` : "—"].map((v, i) => (
                      <td key={i} style={{ padding: "8px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{v}</td>
                    ))}
                    <td style={{ padding: "8px 12px", textAlign: "right", borderBottom: "1px solid rgba(255,64,64,.07)" }}><span style={{ color: sc, fontWeight: 600, fontSize: 12 }}>{t.status}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, big, tone }) {
  const col = tone === "up" ? "#2ee27a" : tone === "down" ? "#ff4d4d" : tone === "muted" ? "#8f8288" : "#f2e8ea";
  return (
    <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: big ? 24 : 17, fontWeight: 700, marginTop: 3, color: col, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}
