"use client";
import Link from "next/link";
import { MarketNews } from "@/components/finance/NewsSignals";
import { Panel, Heading, Eyebrow } from "@/components/ui";

export default function Page() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Market News</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Panel style={{ padding: 0, marginTop: 14 }}><MarketNews /></Panel>
    </div>
  );
}
