"use client";
import { Panel, Eyebrow } from "@/components/ui";
import MobileFinance from "@/components/mobile/MobileFinance";

export default function Finance() {
  return (
    <>
      <div className="only-mobile"><MobileFinance /></div>
      <div className="only-desktop" style={{ maxWidth: 1620, margin: "0 auto", padding: 40 }}>
        <Panel style={{ padding: 60, textAlign: "center" }}>
          <Eyebrow>Finance Dashboard</Eyebrow>
          <p style={{ color: "var(--color-ink-400)", fontSize: 15, marginTop: 16, lineHeight: 1.6, maxWidth: 560, margin: "16px auto 0" }}>
            Finance data is not yet connected. The backend modules (Portfolio, Trade Journal, Revenue)
            exist but are not wired to a unified dashboard API.
          </p>
          <p style={{ color: "var(--color-ink-500)", fontSize: 13, marginTop: 12 }}>
            Revenue tracking is available in the CEO Home dashboard.
          </p>
        </Panel>
      </div>
    </>
  );
}
