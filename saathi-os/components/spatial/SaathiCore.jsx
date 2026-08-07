"use client";
/**
 * M58 — SaathiCore. The central animated intelligence orb. Represents SaathiOS /
 * PlatformAgentRuntime and communicates operational state through colour + a
 * text status (never colour alone). Deliberately sparse: identity + a few real
 * metrics, nothing more.
 */
import { SIGNAL_TOKENS } from "@/lib/spatial";
import { StatusPulse } from "./frame";

const STATE_COPY = {
  active: { line: "System ready with limitations", tone: "READY" },
  attention: { line: "Attention required", tone: "ATTENTION" },
  danger: { line: "Execution blocked", tone: "BLOCKED" },
  idle: { line: "Idle", tone: "IDLE" },
  unknown: { line: "Awaiting runtime", tone: "UNKNOWN" },
};

export function SaathiCore({ signal = "unknown", size = 260, metrics = {}, subtitle = "Local Private Alpha" }) {
  const tok = SIGNAL_TOKENS[signal] || SIGNAL_TOKENS.unknown;
  const copy = STATE_COPY[signal] || STATE_COPY.unknown;
  const chips = [
    metrics.runningExecutions != null && { k: "Runs", v: metrics.runningExecutions, sig: metrics.runningExecutions > 0 ? "active" : "idle" },
    metrics.pendingApprovals != null && { k: "Approvals", v: metrics.pendingApprovals, sig: metrics.pendingApprovals > 0 ? "attention" : "idle" },
    metrics.attentionCount != null && { k: "Attention", v: metrics.attentionCount, sig: metrics.attentionCount > 0 ? "attention" : "idle" },
  ].filter(Boolean);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-4)" }}>
      <div className="saathi-core" style={{ width: size, height: size, "--core-c": tok.color }}>
        <span className="saathi-core__aura" aria-hidden="true" />
        <span className="saathi-core__ring" aria-hidden="true" />
        <span className="saathi-core__ring saathi-core__ring--2" aria-hidden="true" />
        <div
          className="saathi-core__body"
          style={{ width: "72%", height: "72%" }}
          role="img"
          aria-label={`Saathi core — ${copy.tone}. ${copy.line}.`}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "0 8%" }}>
            <span className="display" style={{ fontSize: size * 0.13, letterSpacing: "0.22em", color: "var(--text-primary)", lineHeight: 1 }}>
              SAATHI
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
              <StatusPulse signal={signal} size={8} label={copy.tone} />
              <span className="mono" style={{ fontSize: size * 0.042, letterSpacing: "0.14em", color: tok.color, textTransform: "uppercase" }}>
                {copy.tone}
              </span>
            </span>
            <span className="mono" style={{ fontSize: size * 0.036, letterSpacing: "0.1em", color: "var(--text-muted)", textTransform: "uppercase" }}>
              {subtitle}
            </span>
          </div>
        </div>
      </div>

      <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--fs-sm)", textAlign: "center" }}>
        {copy.line}
      </p>

      {chips.length > 0 && (
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap", justifyContent: "center" }}>
          {chips.map((c) => {
            const ct = SIGNAL_TOKENS[c.sig] || SIGNAL_TOKENS.idle;
            return (
              <span key={c.k} style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", minWidth: 58 }}>
                <span className="mono" style={{ fontSize: "var(--fs-xl)", color: ct.color, lineHeight: 1 }}>{c.v}</span>
                <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{c.k}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
