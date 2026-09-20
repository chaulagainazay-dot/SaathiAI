"use client";
import Link from "next/link";
import BrokerDesk from "@/components/finance/BrokerDesk";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function BrokersPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Broker Accumulation / Distribution</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Who is net-buying (accumulation) and net-selling (distribution) from the exchange floorsheet. Published after market close. Observation-only.
      </Text>
      <Panel style={{ padding: 0 }}><BrokerDesk /></Panel>
    </div>
  );
}
