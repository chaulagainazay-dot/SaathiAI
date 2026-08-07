"use client";
/**
 * M58 — Glass Frame primitives. Thin, composable, token-driven. No hard-coded
 * visual values; everything references the semantic tokens defined in globals.css.
 */
import { useEffect, useState } from "react";
import { SIGNAL_TOKENS } from "@/lib/spatial";

/* Map a signal → the glass-frame modifier class + its accent colour var. */
function frameClassFor(signal) {
  if (signal === "active") return "glass-frame--active";
  if (signal === "attention" || signal === "success") return signal === "success" ? "" : "glass-frame--authority";
  if (signal === "danger") return "glass-frame--danger";
  return "";
}

/* ---- useReducedMotion — single source; SSR-safe (defaults to reduced=false). */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/* Provider is a thin pass-through kept for the documented component API; the
   hook is the real mechanism and CSS handles the rest. */
export function ReducedMotionProvider({ children }) {
  return children;
}

/* ---- GlassFrame — base translucent surface with optional signal edge. ---- */
export function GlassFrame({ signal, strong = false, as = "div", className = "", style, children, ...rest }) {
  const Tag = as;
  const accent = signal && SIGNAL_TOKENS[signal] ? SIGNAL_TOKENS[signal].color : undefined;
  return (
    <Tag
      className={["glass-frame", strong ? "glass-frame--strong" : "", frameClassFor(signal), className].filter(Boolean).join(" ")}
      style={{ ...(accent ? { "--node-c": accent } : null), ...style }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- GlassPanel — padded content region inside a frame. ---- */
export function GlassPanel({ className = "", style, children, ...rest }) {
  return (
    <div className={className} style={{ padding: "var(--space-5)", ...style }} {...rest}>
      {children}
    </div>
  );
}

/* ---- StatusPulse — non-colour-only status marker (dot + animated halo). ---- */
export function StatusPulse({ signal = "idle", size = 9, label }) {
  const tok = SIGNAL_TOKENS[signal] || SIGNAL_TOKENS.idle;
  return (
    <span
      className="status-pulse"
      role="img"
      aria-label={label || `Status: ${tok.label}`}
      style={{ width: size, height: size, "--pulse-c": tok.color }}
    >
      <span className="status-pulse__core" />
      {(signal === "active" || signal === "attention" || signal === "danger") && (
        <span className="status-pulse__halo" />
      )}
    </span>
  );
}

/* ---- SafetyBoundaryBadge — always-visible, truthful safety label. ---- */
export function SafetyBoundaryBadge({ label, tone = "idle", style }) {
  const tok = SIGNAL_TOKENS[tone] || SIGNAL_TOKENS.idle;
  return (
    <span
      className="mono"
      style={{
        display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap",
        padding: "4px 10px", borderRadius: 999, fontSize: "var(--fs-2xs)",
        letterSpacing: "0.1em", textTransform: "uppercase",
        color: tok.color,
        background: `color-mix(in srgb, ${tok.color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${tok.color} 40%, transparent)`,
        ...style,
      }}
    >
      <span aria-hidden="true" style={{ width: 5, height: 5, borderRadius: "50%", background: tok.color, boxShadow: `0 0 8px ${tok.color}` }} />
      {label}
    </span>
  );
}

/* ---- LiveMetric — a real value or an explicit "unavailable" state. ---- */
export function LiveMetric({ label, value, unit, signal = "idle", mono = true }) {
  const tok = SIGNAL_TOKENS[signal] || SIGNAL_TOKENS.idle;
  const unknown = value === null || value === undefined;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 64 }}>
      <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span
        className={mono ? "mono" : "display"}
        style={{ fontSize: "var(--fs-lg)", color: unknown ? "var(--text-muted)" : tok.color, lineHeight: 1.1 }}
      >
        {unknown ? "—" : value}
        {!unknown && unit ? <span style={{ fontSize: "var(--fs-xs)", color: "var(--text-muted)", marginLeft: 3 }}>{unit}</span> : null}
      </span>
    </div>
  );
}

/* ---- SystemStatusStrip — top status bar for the spatial home. ---- */
export function SystemStatusStrip({ children, style, className = "" }) {
  return (
    <div className={`status-strip ${className}`} style={style} role="status" aria-live="polite">
      {children}
    </div>
  );
}

/* ---- ContextDrawer — right-side detail panel (desktop) / drawer (mobile). ---- */
export function ContextDrawer({ open = true, title, onClose, children, className = "", style }) {
  if (!open) return null;
  return (
    <aside
      className={`context-drawer ${className}`}
      aria-label={title ? `${title} details` : "Details"}
      style={{ padding: "var(--space-5)", ...style }}
    >
      {(title || onClose) && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
          {title && <span className="eyebrow" style={{ color: "var(--text-secondary)" }}>{title}</span>}
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close details"
              style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-secondary)", borderRadius: 8, width: 28, height: 28, cursor: "pointer" }}
            >
              ✕
            </button>
          )}
        </div>
      )}
      {children}
    </aside>
  );
}
