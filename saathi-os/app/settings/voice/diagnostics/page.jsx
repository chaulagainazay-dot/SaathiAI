"use client";

/**
 * R2.1 — Real-microphone owner-validation surface.
 *
 * Read-only observation page. The production voice runtime is driven from the
 * shell's Live voice dock; this page only publishes the states needed to prove
 * each stage of the pipeline actually worked with a physical microphone.
 */

import Link from "next/link";
import VoiceDiagnosticsPanel from "@/components/voice/VoiceDiagnosticsPanel";
import MicCalibrationPanel from "@/components/voice/MicCalibrationPanel";

const row = { display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" };
const badge = {
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,.16)",
  background: "rgba(255,255,255,.05)",
  padding: "4px 9px",
  fontSize: 12,
};

export default function VoiceDiagnosticsPage() {
  return (
    <div
      className="page shell-page shell-page--dock-clearance"
      data-testid="voice-diagnostics-page"
      style={{ maxWidth: 1100 }}
    >
      <header className="shell-page-header">
        <nav aria-label="Voice diagnostics breadcrumb" style={row}>
          <Link href="/settings">Settings</Link>
          <span aria-hidden="true">/</span>
          <Link href="/settings/voice">Voice Settings</Link>
          <span aria-hidden="true">/</span>
          <Link href="/settings/voice/diagnostics" aria-current="page">
            Diagnostics
          </Link>
        </nav>
        <h1>Voice Runtime Diagnostics</h1>
        <p style={{ color: "var(--text-muted)" }}>
          Owner validation for the real microphone path. Start and stop voice with the{" "}
          <strong>Live voice</strong> dock; every state below is observed from the same
          canonical voice session the product uses.
        </p>
        <div style={row} aria-label="Diagnostics boundaries">
          <span style={badge}>READ-ONLY OBSERVER</span>
          <span style={badge}>NO SECOND MICROPHONE</span>
          <span style={badge}>NO RAW AUDIO STORED</span>
          <span style={badge}>NO EXECUTION AUTHORITY</span>
        </div>
      </header>

      <VoiceDiagnosticsPanel />
      <MicCalibrationPanel />
    </div>
  );
}
