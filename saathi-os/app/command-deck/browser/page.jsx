"use client";
import Link from "next/link";
import FinancialBrowserPanel from "@/components/finance/FinancialBrowserPanel";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function BrowserFullPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Financial Browser</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Open a provider inside SaathiOS (no external Chrome), log in yourself, enable Saathi Read, then observe read-only holdings. No trading.
      </Text>
      <Panel style={{ padding: 0 }}><FinancialBrowserPanel /></Panel>
    </div>
  );
}
