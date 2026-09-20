"use client";
import Link from "next/link";
import ChartAnalysis from "@/components/finance/ChartAnalysis";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function ChartFullPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Chart Analysis</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Search any NEPSE stock, switch timeframe, auto-draw ICT/SMC with numbers, and read the volume desk buy/sell signals. Research only — not advice.
      </Text>
      <Panel style={{ padding: 16 }}><ChartAnalysis expanded /></Panel>
    </div>
  );
}
