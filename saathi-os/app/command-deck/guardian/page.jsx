"use client";
import Link from "next/link";
import PaperTradingAgent from "@/components/finance/PaperTradingAgent";
import { Panel, Heading, Eyebrow, Text, Badge } from "@/components/ui";

export default function GuardianFullPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Trading Guardian</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0 16px" }}>
        {["BUY", "SELL", "TRANSFER", "WITHDRAW"].map((a) => <Badge key={a} variant="soft" color="#ff5757" label={`${a} · BLOCKED`} />)}
        <Badge variant="soft" color="#ffab3d" label="OBSERVATION-ONLY · NO TRADE AUTHORITY" />
      </div>
      <Panel style={{ padding: 0 }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,64,64,.12)", fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>Paper Trading Agent · simulation</div>
        <PaperTradingAgent market="NEPSE" symbol="NABIL" />
      </Panel>
    </div>
  );
}
