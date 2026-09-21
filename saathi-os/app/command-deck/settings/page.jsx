"use client";
import Link from "next/link";
import SettingsKeys from "@/components/finance/SettingsKeys";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function SettingsPage() {
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Settings</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>API Keys</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Paste an API key and it works immediately — stored locally, set into the running app, no restart. A valid GOOGLE_API_KEY powers the chat brain + screen vision.
      </Text>
      <Panel style={{ padding: 0 }}><SettingsKeys /></Panel>
    </div>
  );
}
