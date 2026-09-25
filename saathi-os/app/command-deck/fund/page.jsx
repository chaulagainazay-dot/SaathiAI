"use client";
import Link from "next/link";
import FundCommittee from "@/components/finance/FundCommittee";
import SwarmPrediction from "@/components/finance/SwarmPrediction";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function FundPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>AI Hedge Fund</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Convene the committee on any symbol — Research, Technical, Volume, Structure (ICT), Setup, Portfolio and Risk agents meet on live data and the CEO issues a decision (swing / long hold / avoid / watch). Watch the discussion live. Research only, not advice.
      </Text>
      <Panel style={{ padding: 0 }}><FundCommittee /></Panel>

      <div style={{ margin: "22px 0 8px" }}>
        <Heading level={2} size="md">Swarm Prediction</Heading>
        <Text tone="muted" size="sm" style={{ display: "block", marginTop: 4 }}>
          A simulated investor crowd (persona archetypes) reads the same real evidence and herds over rounds into an emergent direction — the committee's decision, stress-tested against a model market crowd. Research only, not advice.
        </Text>
      </div>
      <Panel style={{ padding: 0 }}><SwarmPrediction /></Panel>
    </div>
  );
}
