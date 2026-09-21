"use client";
import Link from "next/link";
import AIAnalysis from "@/components/finance/AIAnalysis";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function Page() {
  return (
    <div style={{ maxWidth: 1520, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>AI Analysis</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 4px" }}>
        Agent technical analysis + ICT/SMC strategy, with every desk wired to the same symbol — live chart, trade setup + volume, news, signals, broker accumulation, S-R + stock screeners and price alerts. Research only, not advice.
      </Text>
      <Panel style={{ padding: 0, marginTop: 14 }}><AIAnalysis /></Panel>
    </div>
  );
}
