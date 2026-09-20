"use client";
import { useState } from "react";
import Link from "next/link";
import ChartAnalysis from "@/components/finance/ChartAnalysis";
import TradeDesk from "@/components/finance/TradeDesk";
import PaperTradingAgent from "@/components/finance/PaperTradingAgent";
import CompanyCard from "@/components/finance/CompanyCard";
import StockScreener from "@/components/finance/StockScreener";
import BrokerDesk from "@/components/finance/BrokerDesk";
import SRScreener from "@/components/finance/SRScreener";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

const TABS = [
  ["setup", "Trade Setup + Volume"],
  ["trades", "Active Trades / Records"],
  ["company", "Company Financials"],
  ["screener", "FinScreener"],
  ["broker", "Broker Analysis"],
  ["sr", "S-R Screener"],
];

export default function ChartWorkspacePage() {
  const [symbol, setSymbol] = useState("NABIL");
  const [tab, setTab] = useState("setup");

  return (
    <div style={{ maxWidth: 1520, margin: "0 auto", padding: "20px 16px 48px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Chart Analysis</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 14px" }}>
        Smart charting workspace — search a stock, auto-drawn ICT/SMC + volume signals, and a side desk with trade setup, volume strength, active trades, company financials, screeners and broker analysis. Research only, not advice.
      </Text>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1fr)", gap: 16, alignItems: "start" }}>
        {/* Chart */}
        <Panel style={{ padding: 16 }}>
          <ChartAnalysis expanded symbol={symbol} onSymbolChange={setSymbol} />
        </Panel>

        {/* Side desk with tabs */}
        <Panel style={{ padding: 0, position: "sticky", top: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid rgba(255,64,64,.12)" }}>
            <span className="retro-live ok" aria-hidden="true" style={{ display: "inline-block" }} />
            <span style={{ fontSize: 12, fontWeight: 700 }}>{symbol}</span>
            <Text tone="disabled" size="xs">smart desk</Text>
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: "10px 12px", borderBottom: "1px solid rgba(255,64,64,.1)" }}>
            {TABS.map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)}
                style={{ fontFamily: "inherit", fontSize: 11, padding: "5px 9px", borderRadius: 100, cursor: "pointer",
                  border: "1px solid rgba(255,64,64,.2)", background: tab === k ? "#ff2a2a" : "transparent",
                  color: tab === k ? "#08060a" : "#b7a8ad", fontWeight: tab === k ? 700 : 400 }}>{label}</button>
            ))}
          </div>
          <div style={{ maxHeight: "72vh", overflowY: "auto" }}>
            {tab === "setup" && <TradeDesk market="NEPSE" symbol={symbol} />}
            {tab === "trades" && <PaperTradingAgent market="NEPSE" symbol={symbol} />}
            {tab === "company" && <CompanyCard symbol={symbol} />}
            {tab === "screener" && <StockScreener />}
            {tab === "broker" && <BrokerDesk />}
            {tab === "sr" && <SRScreener />}
          </div>
        </Panel>
      </div>
    </div>
  );
}
