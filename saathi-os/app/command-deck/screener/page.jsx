"use client";
import Link from "next/link";
import StockScreener from "@/components/finance/StockScreener";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function ScreenerPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Stock Screener</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Filter by sector, price, P/E, P/B, EPS, RSI and market cap. Sort any column. Research only — not advice.
      </Text>
      <Panel style={{ padding: 0 }}><StockScreener /></Panel>
    </div>
  );
}
