"use client";
import { Panel, Eyebrow } from "@/components/ui";

export default function MobileFinance() {
  return (
    <div className="m-page" style={{ padding: 40, textAlign: "center" }}>
      <Panel style={{ padding: 32 }}>
        <Eyebrow>Finance</Eyebrow>
        <p style={{ color: "var(--color-ink-400)", fontSize: 14, marginTop: 12, lineHeight: 1.5 }}>
          Finance data is not yet connected. Revenue tracking is available in the CEO Home dashboard.
        </p>
      </Panel>
    </div>
  );
}
