"use client";
/**
 * AI Hedge-Fund Committee — convene role agents on a symbol; watch them post real-data findings
 * to a live group chat, ending in the CEO's decision (SWING/LONG/AVOID/WATCH). Research only.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

const ROLE_COLOR = {
  technical: "#4fb0c6", structure: "#c99bff", volume: "#ffab3d", research: "#2ee27a",
  news: "#b7a8ad", setup: "#ff5757", portfolio: "#8fb3ff", risk: "#ff4d4d",
  ceo: "#ff2a2a", data: "#8f8288",
};
const DECISION_COLOR = { SWING_TRADE: "#2ee27a", LONG_HOLD: "#2ee27a", ADD: "#2ee27a", WATCH: "#ffab3d", TRIM: "#ffab3d", AVOID: "#ff4d4d", NO_DATA: "#8f8288" };

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}

export default function FundCommittee() {
  const [market, setMarket] = useState("NEPSE");
  const [symbol, setSymbol] = useState("NABIL");
  const [result, setResult] = useState(null);
  const [visible, setVisible] = useState(0);      // staggered reveal count
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState([]);
  const timer = useRef(null);
  const scrollRef = useRef(null);

  const loadRecent = useCallback(async () => { const r = await api("/api/v1/fund/meetings?limit=8"); if (r.ok) setRecent(r.body.meetings || []); }, []);
  useEffect(() => { loadRecent(); }, [loadRecent]);
  useEffect(() => () => timer.current && clearInterval(timer.current), []);

  const reveal = (msgs) => {
    setVisible(0);
    if (timer.current) clearInterval(timer.current);
    let i = 0;
    timer.current = setInterval(() => {
      i += 1; setVisible(i);
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      if (i >= msgs.length) clearInterval(timer.current);
    }, 650);
  };

  const convene = async () => {
    if (!symbol.trim()) return;
    setBusy(true); setResult(null); setVisible(0);
    const r = await api("/api/v1/fund/meeting", { method: "POST", body: JSON.stringify({ market, symbol: symbol.trim() }) });
    if (r.ok && r.body?.ok) { setResult(r.body); reveal(r.body.messages || []); loadRecent(); }
    else setResult({ error: r.body?.error || "Meeting failed" });
    setBusy(false);
  };

  const openMeeting = async (sid) => {
    setBusy(true); setResult(null);
    const r = await api(`/api/v1/fund/meeting/${sid}`);
    if (r.ok && r.body?.ok) {
      const s = r.body.session;
      const body = { ok: true, symbol: s.symbol, market: s.market, messages: r.body.messages, decision: { decision: s.decision, horizon: s.horizon, reason: s.reason } };
      setResult(body); reveal(r.body.messages);
    }
    setBusy(false);
  };

  const msgs = result?.messages || [];
  const dec = result?.decision;

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["NEPSE", "CRYPTO"].map((m) => (
            <button key={m} onClick={() => { setMarket(m); setSymbol(m === "NEPSE" ? "NABIL" : "BTC"); }}
              style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: 700 }}>{m}</button>
          ))}
        </div>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter") convene(); }}
          placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH…"}
          style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 150, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <Button size="sm" onClick={convene} disabled={busy}>{busy ? "Committee meeting…" : "Convene committee"}</Button>
      </div>

      {busy && !result && <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Spinner size={14} /><Text tone="muted" size="sm">Agents reading live data + meeting…</Text></div>}
      {result?.error && <Text tone="muted" size="sm">{result.error}</Text>}
      {!result && !busy && <EmptyState title="Convene the committee" description="The Research, Technical, Volume, Structure, Setup, Portfolio and Risk agents meet on live data; the CEO issues a decision. Research only." />}

      {result?.ok && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 260px", gap: 16, alignItems: "start" }}>
          {/* Group chat */}
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>COMMITTEE · {result.market} {result.symbol}</div>
            <div ref={scrollRef} style={{ maxHeight: 460, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, paddingRight: 4 }}>
              {msgs.slice(0, visible).map((m, i) => {
                const col = ROLE_COLOR[m.role] || "#b7a8ad";
                const ceo = m.role === "ceo";
                return (
                  <div key={i} style={{ background: ceo ? "rgba(255,42,42,.07)" : "#0b0709", border: `1px solid ${ceo ? "rgba(255,42,42,.3)" : "rgba(255,64,64,.12)"}`, borderRadius: 10, padding: "9px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      <span style={{ width: 7, height: 7, borderRadius: 4, background: col, display: "inline-block" }} />
                      <span style={{ fontSize: 12, fontWeight: 700, color: col }}>{m.agent}</span>
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", fontSize: 12.5, lineHeight: 1.5, color: "#dccfd3" }}>{m.text}</div>
                  </div>
                );
              })}
              {visible < msgs.length && <div style={{ display: "flex", gap: 6, alignItems: "center", color: "#8f8288", fontSize: 12 }}><Spinner size={12} /> next analyst…</div>}
            </div>
          </div>

          {/* Decision + recent */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {dec && (
              <div style={{ background: "#0b0709", border: `1px solid ${DECISION_COLOR[dec.decision] || "#8f8288"}55`, borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>CEO DECISION</div>
                <div style={{ fontSize: 18, fontWeight: 700, marginTop: 3, color: DECISION_COLOR[dec.decision] || "#f2e8ea" }}>{dec.decision.replace(/_/g, " ")}</div>
                <Text tone="muted" size="xs" style={{ display: "block", marginTop: 2 }}>horizon: {dec.horizon}</Text>
                <Text tone="muted" size="xs" style={{ display: "block", marginTop: 6, lineHeight: 1.5 }}>{dec.reason}</Text>
                <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Research verdict · not advice, not an order.</Text>
              </div>
            )}
            {recent.length > 0 && (
              <div>
                <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>RECENT MEETINGS</div>
                {recent.map((s) => (
                  <button key={s.id} onClick={() => openMeeting(s.id)} style={{ display: "flex", justifyContent: "space-between", width: "100%", fontFamily: "inherit", fontSize: 12, padding: "6px 8px", borderRadius: 6, cursor: "pointer", border: "1px solid rgba(255,64,64,.1)", background: "transparent", color: "#dccfd3", marginBottom: 4 }}>
                    <span>{s.symbol}</span><span style={{ color: DECISION_COLOR[s.decision] || "#8f8288" }}>{(s.decision || "").replace(/_/g, " ")}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
