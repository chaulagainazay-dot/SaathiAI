"use client";
import { useState } from "react";
import Link from "next/link";
import PaperTradingAgent from "@/components/finance/PaperTradingAgent";
import StrategyPlaybook from "@/components/finance/StrategyPlaybook";
import { Panel, Heading, Eyebrow, Text, Badge, Button } from "@/components/ui";

export default function GuardianFullPage() {
  const [market, setMarket] = useState("NEPSE");
  const [symbol, setSymbol] = useState("NABIL");
  const [input, setInput] = useState("NABIL");

  const apply = (s) => { const v = (s ?? input).trim().toUpperCase(); if (v) { setSymbol(v); setInput(v); } };

  return (
    <div style={{ maxWidth: 1360, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Trading Guardian</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0 16px" }}>
        {["BUY", "SELL", "TRANSFER", "WITHDRAW"].map((a) => <Badge key={a} variant="soft" color="#ff5757" label={`${a} · BLOCKED`} />)}
        <Badge variant="soft" color="#ffab3d" label="OBSERVATION-ONLY · NO TRADE AUTHORITY" />
      </div>

      {/* Shared symbol control */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["NEPSE", "CRYPTO"].map((m) => (
            <button key={m} onClick={() => { setMarket(m); apply(m === "NEPSE" ? "NABIL" : "BTC"); }}
              style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
          ))}
        </div>
        <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter") apply(); }}
          placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH…"}
          style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 160, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <Button size="sm" onClick={() => apply()}>Load {input || "symbol"}</Button>
        <Text tone="disabled" size="xs">Guardian, playbook and paper agent all read {market} · {symbol}.</Text>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 16, alignItems: "start" }}>
        <Panel style={{ padding: 0 }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,64,64,.12)", fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>Strategy Playbook · live setups</div>
          <StrategyPlaybook market={market} symbol={symbol} />
        </Panel>
        <Panel style={{ padding: 0 }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,64,64,.12)", fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>Paper Trading Agent · simulation</div>
          <PaperTradingAgent market={market} symbol={symbol} />
        </Panel>
      </div>
    </div>
  );
}
