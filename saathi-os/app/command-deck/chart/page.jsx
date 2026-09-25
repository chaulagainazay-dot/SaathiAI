"use client";
/**
 * Trading Analysis — the single NEPSE (+ crypto) roof. One window: a live chart the agent
 * auto-draws (ICT/SMC + volume signals) on the left, and one tabbed desk on the right holding
 * every tool — AI analysis, strategy playbook, trade setup, signals, screeners, broker,
 * company, alerts, news, paper agent and screen analysis — all wired to one shared symbol.
 * Observation/research only — never advice, never an order.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE, afetch } from "@/lib/api";
import { Panel, Heading, Eyebrow, Text, Pill, StatusBadge } from "@/components/ui";
import ChartAnalysis from "@/components/finance/ChartAnalysis";
import AIAnalysis from "@/components/finance/AIAnalysis";
import StrategyPlaybook from "@/components/finance/StrategyPlaybook";
import TradeDesk from "@/components/finance/TradeDesk";
import BrokerDesk from "@/components/finance/BrokerDesk";
import StockScreener from "@/components/finance/StockScreener";
import SRScreener from "@/components/finance/SRScreener";
import CompanyCard from "@/components/finance/CompanyCard";
import PriceAlerts from "@/components/finance/PriceAlerts";
import PaperTradingAgent from "@/components/finance/PaperTradingAgent";
import SwarmPrediction from "@/components/finance/SwarmPrediction";
import ScreenVision from "@/components/finance/ScreenVision";
import { MarketNews, TradingSignals } from "@/components/finance/NewsSignals";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, body: b }; });
}
const numOr = (v, d = null) => { const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : d; };
const pct = (n) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`);

// tab key → [label, nepseOnly]
const TABS = [
  ["analysis", "AI Analysis", false],
  ["swarm", "Swarm Predict", false],
  ["strategy", "Strategy Playbook", false],
  ["setup", "Trade Setup + Volume", false],
  ["signals", "Signals", false],
  ["news", "News", false],
  ["company", "Company", true],
  ["broker", "Broker Analysis", true],
  ["sr", "S-R Screener", true],
  ["screener", "Stock Screener", true],
  ["alerts", "Price Alerts", true],
  ["paper", "Paper Agent", false],
  ["vision", "Screen Analysis", false],
];

export default function TradingAnalysisRoof() {
  const [market, setMarket] = useState("NEPSE");
  const [symbol, setSymbol] = useState(() => {
    if (typeof window !== "undefined") {
      const u = new URLSearchParams(window.location.search).get("symbol");
      if (u) return u.toUpperCase();
    }
    return "NABIL";
  });
  const [input, setInput] = useState("");
  const [tab, setTab] = useState("analysis");
  const [pulse, setPulse] = useState(null);

  useEffect(() => {
    let alive = true;
    const run = async () => { const r = await api("/api/v1/market/nepse/live/full"); if (alive && r.ok) setPulse(r.body); };
    run(); const id = setInterval(run, 30000); return () => { alive = false; clearInterval(id); };
  }, []);

  const apply = useCallback((s) => { const v = (s ?? input).trim().toUpperCase(); if (v) { setSymbol(v); setInput(""); } }, [input]);

  const tabs = useMemo(() => TABS.filter(([, , nepseOnly]) => market === "NEPSE" || !nepseOnly), [market]);
  const activeTab = tabs.some(([k]) => k === tab) ? tab : "analysis";

  const idx = numOr(pulse?.nepse_index);
  const idxPct = numOr(pulse?.index_change_percent);
  const mstatus = pulse?.market_status;

  return (
    <div style={{ maxWidth: 1600, margin: "0 auto", padding: "18px 16px 48px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · one roof</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Trading Analysis</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>

      {/* Control bar: market + symbol search + NEPSE pulse */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", margin: "12px 0 6px" }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["NEPSE", "CRYPTO"].map((m) => (
            <button key={m} onClick={() => { setMarket(m); apply(m === "NEPSE" ? "NABIL" : "BTC"); }}
              style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
          ))}
        </div>
        <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter") apply(); }}
          placeholder={`Search ${market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH…"} — current: ${symbol}`}
          style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 12px", borderRadius: 8, width: 260, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "#f2e8ea" }}>{market} · {symbol}</span>
        <div style={{ flexGrow: 1 }} />
        {market === "NEPSE" && (
          <span style={{ fontSize: 12, color: "#8f8288", fontVariantNumeric: "tabular-nums" }}>
            NEPSE <b style={{ color: "#f2e8ea" }}>{idx != null ? idx.toLocaleString("en-IN") : "—"}</b>
            <span style={{ color: idxPct >= 0 ? "#2ee27a" : "#ff4d4d", marginLeft: 6 }}>{idxPct != null ? pct(idxPct) : ""}</span>
          </span>
        )}
        <StatusBadge status={mstatus ? "success" : "neutral"} label={mstatus ? `NEPSE · ${mstatus}` : "NEPSE"} />
        <Pill color="#FF5A5A">No BUY · SELL · TRANSFER</Pill>
      </div>

      {/* Two-pane roof: chart + one tabbed desk */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1fr)", gap: 16, alignItems: "start", marginTop: 8 }}>
        <Panel style={{ padding: 16 }}>
          <ChartAnalysis expanded symbol={symbol} onSymbolChange={setSymbol} />
        </Panel>

        <Panel style={{ padding: 0, position: "sticky", top: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid rgba(255,64,64,.12)" }}>
            <span className="retro-live ok" aria-hidden="true" style={{ display: "inline-block" }} />
            <span style={{ fontSize: 12, fontWeight: 700 }}>{symbol}</span>
            <Text tone="disabled" size="xs">unified desk</Text>
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: "10px 12px", borderBottom: "1px solid rgba(255,64,64,.1)" }}>
            {tabs.map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)}
                style={{ fontFamily: "inherit", fontSize: 11, padding: "5px 9px", borderRadius: 100, cursor: "pointer",
                  border: "1px solid rgba(255,64,64,.2)", background: activeTab === k ? "#ff2a2a" : "transparent",
                  color: activeTab === k ? "#08060a" : "#b7a8ad", fontWeight: activeTab === k ? 700 : 400 }}>{label}</button>
            ))}
          </div>
          <div style={{ maxHeight: "78vh", overflowY: "auto" }}>
            {activeTab === "analysis" && <AIAnalysis market={market} symbol={symbol} auto />}
            {activeTab === "swarm" && <SwarmPrediction market={market} symbol={symbol} auto />}
            {activeTab === "strategy" && <StrategyPlaybook market={market} symbol={symbol} />}
            {activeTab === "setup" && <TradeDesk market={market} symbol={symbol} />}
            {activeTab === "signals" && <TradingSignals />}
            {activeTab === "news" && <MarketNews symbol={symbol} />}
            {activeTab === "company" && <CompanyCard symbol={symbol} />}
            {activeTab === "broker" && <BrokerDesk symbol={symbol} />}
            {activeTab === "sr" && <SRScreener />}
            {activeTab === "screener" && <StockScreener />}
            {activeTab === "alerts" && <PriceAlerts symbol={symbol} />}
            {activeTab === "paper" && <PaperTradingAgent market={market} symbol={symbol} />}
            {activeTab === "vision" && <ScreenVision />}
          </div>
        </Panel>
      </div>
    </div>
  );
}
