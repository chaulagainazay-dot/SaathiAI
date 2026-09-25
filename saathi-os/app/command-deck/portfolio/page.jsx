"use client";
import Link from "next/link";
import PortfolioDesk from "@/components/finance/PortfolioDesk";
import SectorRotation from "@/components/finance/SectorRotation";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function PortfolioPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Portfolio</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Add holdings, track live value + P/L, analyse concentration and drawdown, and get research-only recommendations (rebalance + per-holding setups). Observation-only, not advice.
      </Text>
      <Panel style={{ padding: 0 }}><PortfolioDesk /></Panel>

      <div style={{ margin: "22px 0 8px" }}>
        <Heading level={2} size="md">Sector Rotation</Heading>
        <Text tone="muted" size="sm" style={{ display: "block", marginTop: 4 }}>
          Your sector mix vs live market sector momentum — where your capital leads, lags, or is missing. Research only, not advice.
        </Text>
      </div>
      <Panel style={{ padding: 0 }}><SectorRotation /></Panel>
    </div>
  );
}
