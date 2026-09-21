"use client";
import Link from "next/link";
import ScreenVision from "@/components/finance/ScreenVision";
import { Panel, Heading, Eyebrow, Text } from "@/components/ui";

export default function VisionPage() {
  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px 56px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div><Eyebrow>Command Deck · Full screen</Eyebrow><Heading level={1} size="xl" style={{ marginTop: 4 }}>Screen Analysis</Heading></div>
        <Link href="/command-deck" style={{ color: "#ff5757", fontSize: 13 }}>← Back to deck</Link>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", margin: "8px 0 16px" }}>
        Let Saathi look at your screen — capture any window/screen, ask a question, and get an answer from Gemini Vision (same brain as Ask Saathi chat). The image is used once and never stored. Research/observation only.
      </Text>
      <Panel style={{ padding: 0 }}><ScreenVision /></Panel>
    </div>
  );
}
