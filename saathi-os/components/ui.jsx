"use client";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect } from "react";

export function Panel({ className = "", children, delay = 0, soft = false, style, onClick, ...rest }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`${soft ? "glass-soft" : "glass"} ${className}`}
      style={onClick ? { cursor: "pointer", ...style } : style}
      onClick={onClick}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function Eyebrow({ children, style, className = "" }) {
  return <div className={`eyebrow ${className}`} style={style}>{children}</div>;
}

export function Pill({ color = "#8FA0C4", children, filled = 0.14, onClick, className = "" }) {
  return (
    <button
      onClick={onClick}
      className={`mono ${className}`}
      style={{
        padding: "6px 14px", borderRadius: 999, fontSize: 10, letterSpacing: "0.12em",
        color, background: `${color}${toHex(filled)}`, border: `1px solid ${color}66`,
        textTransform: "uppercase", cursor: onClick ? "pointer" : "default",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

export function Dot({ color, size = 8, ring = true }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", width: size, height: size }}>
      <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: color,
        boxShadow: `0 0 10px ${color}88` }} />
      {ring && <span style={{ position: "absolute", inset: -3, borderRadius: "50%",
        border: `1px solid ${color}66` }} />}
    </span>
  );
}

export function Bar({ frac, color, label, value }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-400)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-200)" }}>{value}</span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }} animate={{ width: `${Math.max(2, frac * 100)}%` }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          style={{ height: "100%", borderRadius: 3, background: color, boxShadow: `0 0 12px ${color}66` }}
        />
      </div>
    </div>
  );
}

// animated counting number
export function Counter({ to, format = (v) => Math.round(v).toString(), className = "", style }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    const controls = animate(mv, to, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return controls.stop;
  }, [to, mv]);
  return <motion.span className={className} style={style}>{text}</motion.span>;
}

// SVG progress ring
export function Ring({ value, color, size = 200, stroke = 12, label, sub }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="rgba(255,255,255,0.10)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - value) }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 10px ${color}66)` }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center" }}>
        {label != null && <Counter to={label} className="display"
          style={{ fontSize: size * 0.24, color: "var(--color-ink-100)", lineHeight: 1 }} />}
        {sub && <div className="eyebrow" style={{ marginTop: 8 }}>{sub}</div>}
      </div>
    </div>
  );
}

function toHex(a) {
  const v = Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0");
  return v;
}

/* ============================================================================
   SaathiOS Design-System Primitives — Milestone 1 (Design Token Foundation)
   Additive. All existing exports above are preserved unchanged.
   No new dependencies. No icon library (inline glyphs/SVG only).
   Components reference SEMANTIC tokens from globals.css — not hex.
   ========================================================================= */

// tiny classnames joiner (no clsx/tailwind-merge dependency in repo)
export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

/* ---- Surface: solid by default; glass is an explicit opt-in variant ---- */
export function Surface({ variant = "base", as = "div", className = "", style, children, ...rest }) {
  const Tag = as;
  const map = {
    base:        "surface",
    raised:      "surface-raised",
    subtle:      "surface-subtle",
    interactive: "surface",
    overlay:     "surface-raised",
    "accent-glass": "surface-glass",
  };
  const interactive = variant === "interactive";
  return (
    <Tag
      className={cx(map[variant] || "surface", className)}
      style={interactive ? { transition: "background var(--motion-fast) var(--ease-standard)", ...style } : style}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- Stack: flexible layout primitive ---- */
export function Stack({
  direction = "column", gap = 3, align, justify, wrap = false,
  as = "div", className = "", style, children, ...rest
}) {
  const Tag = as;
  const g = typeof gap === "number" ? `var(--space-${gap})` : gap;
  return (
    <Tag
      className={className}
      style={{
        display: "flex", flexDirection: direction, gap: g,
        alignItems: align, justifyContent: justify,
        flexWrap: wrap ? "wrap" : "nowrap", ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- Divider: accessible separator ---- */
export function Divider({ orientation = "horizontal", className = "", style }) {
  const vertical = orientation === "vertical";
  return (
    <div
      role="separator"
      aria-orientation={orientation}
      className={className}
      style={{
        background: "var(--separator)",
        ...(vertical
          ? { width: 1, alignSelf: "stretch", minHeight: "100%" }
          : { height: 1, width: "100%" }),
        ...style,
      }}
    />
  );
}

/* ---- Text: semantic text primitive ---- */
const TEXT_TONE = {
  primary: "var(--text-primary)", secondary: "var(--text-secondary)",
  muted: "var(--text-muted)", disabled: "var(--text-disabled)",
  danger: "var(--status-danger)", success: "var(--status-success)",
  warning: "var(--status-warning)",
};
const TEXT_SIZE = {
  "2xs": "var(--fs-2xs)", xs: "var(--fs-xs)", sm: "var(--fs-sm)",
  base: "var(--fs-base)", md: "var(--fs-md)", lg: "var(--fs-lg)",
  xl: "var(--fs-xl)", "2xl": "var(--fs-2xl)", "3xl": "var(--fs-3xl)",
};
export function Text({
  tone = "primary", size = "base", weight, mono = false, as = "span",
  className = "", style, children, ...rest
}) {
  const Tag = as;
  return (
    <Tag
      className={cx(mono ? "mono" : "", className)}
      style={{
        color: TEXT_TONE[tone] || TEXT_TONE.primary,
        fontSize: TEXT_SIZE[size] || TEXT_SIZE.base,
        fontWeight: weight, lineHeight: "var(--leading-normal)", ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- Heading: semantic level chosen explicitly (never from visual size) ---- */
export function Heading({ level = 2, size = "lg", display = true, className = "", style, children, ...rest }) {
  const Tag = `h${Math.min(6, Math.max(1, level))}`;
  return (
    <Tag
      className={cx(display ? "display" : "", className)}
      style={{
        color: "var(--text-primary)", fontSize: TEXT_SIZE[size] || TEXT_SIZE.lg,
        lineHeight: "var(--leading-tight)", margin: 0, ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- Badge base: NEVER color-only — always label + shape marker ---- */
export function Badge({ color = "var(--status-neutral)", glyph, label, children, variant = "soft", className = "", style, ...rest }) {
  const content = label ?? children;
  const solid = variant === "solid";
  return (
    <span
      className={cx("mono", className)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "3px 9px", borderRadius: "var(--badge-radius)",
        fontSize: "var(--fs-2xs)", letterSpacing: "0.1em", textTransform: "uppercase",
        whiteSpace: "nowrap",
        color: solid ? "#04060d" : color,
        background: solid ? color : `color-mix(in srgb, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 45%, transparent)`,
        ...style,
      }}
      {...rest}
    >
      {glyph != null && <span aria-hidden="true" style={{ fontSize: "0.95em", lineHeight: 1 }}>{glyph}</span>}
      <span>{content}</span>
    </span>
  );
}

/* ---- StatusBadge ---- */
const STATUS = {
  success: { c: "var(--status-success)", g: "✓", t: "Success" },
  warning: { c: "var(--status-warning)", g: "△", t: "Warning" },
  danger:  { c: "var(--status-danger)",  g: "✕", t: "Danger" },
  info:    { c: "var(--status-info)",    g: "i", t: "Info" },
  pending: { c: "var(--status-pending)", g: "◔", t: "Pending" },
  paused:  { c: "var(--status-paused)",  g: "❙❙", t: "Paused" },
  blocked: { c: "var(--status-blocked)", g: "⊘", t: "Blocked" },
  neutral: { c: "var(--status-neutral)", g: "○", t: "Neutral" },
};
export function StatusBadge({ status = "neutral", label, ...rest }) {
  const s = STATUS[status] || STATUS.neutral;
  const text = label ?? s.t;
  return <Badge color={s.c} glyph={s.g} label={text} aria-label={`Status: ${text}`} {...rest} />;
}

/* ---- AuthorityBadge — default is advisory; NEVER implies autonomy by default ---- */
const AUTHORITY = {
  advisory:             { c: "var(--authority-advisory)",           g: "◎", t: "Advisory" },
  "approval-required":  { c: "var(--authority-approval-required)",  g: "!", t: "Approval required" },
  "limited-autonomous": { c: "var(--authority-limited-autonomous)", g: "◑", t: "Limited autonomous" },
  denied:               { c: "var(--authority-denied)",             g: "⊘", t: "Denied" },
  inactive:             { c: "var(--authority-inactive)",           g: "◌", t: "Inactive" },
  "not-exercised":      { c: "var(--authority-not-exercised)",      g: "◌", t: "Not exercised" },
};
export function AuthorityBadge({ authority = "advisory", label, ...rest }) {
  const a = AUTHORITY[authority] || AUTHORITY.advisory;
  const text = label ?? a.t;
  const dashed = authority === "not-exercised" || authority === "inactive";
  return (
    <Badge
      color={a.c} glyph={a.g} label={text}
      aria-label={`Authority: ${text}`}
      style={dashed ? { borderStyle: "dashed" } : undefined}
      {...rest}
    />
  );
}

/* ---- RiskBadge ---- */
const RISK = {
  low:      { c: "var(--risk-low)",      g: "▁", t: "Low" },
  guarded:  { c: "var(--risk-guarded)",  g: "▃", t: "Guarded" },
  elevated: { c: "var(--risk-elevated)", g: "▅", t: "Elevated" },
  high:     { c: "var(--risk-high)",     g: "▆", t: "High" },
  critical: { c: "var(--risk-critical)", g: "▇", t: "Critical" },
  unknown:  { c: "var(--risk-unknown)",  g: "?", t: "Unknown" },
};
export function RiskBadge({ risk = "unknown", label, ...rest }) {
  const r = RISK[risk] || RISK.unknown;
  const text = label ?? r.t;
  const dashed = risk === "unknown";
  return (
    <Badge
      color={r.c} glyph={r.g} label={`Risk ${text}`}
      aria-label={`Risk: ${text}`}
      style={dashed ? { borderStyle: "dashed" } : undefined}
      {...rest}
    />
  );
}

/* ---- EnvironmentBadge — production is unmistakable ---- */
const ENV = {
  local:      { c: "var(--status-neutral)", g: "◍", t: "Local" },
  vm:         { c: "var(--status-info)",    g: "◍", t: "VM" },
  staging:    { c: "var(--risk-guarded)",   g: "◍", t: "Staging" },
  canary:     { c: "var(--risk-guarded)",   g: "◐", t: "Canary" },
  production: { c: "var(--risk-high)",       g: "⬤", t: "Production" },
};
export function EnvironmentBadge({ env = "local", label, ...rest }) {
  const e = ENV[env] || ENV.local;
  const text = label ?? e.t;
  return (
    <Badge
      color={e.c} glyph={e.g} label={text}
      variant={env === "production" ? "solid" : "soft"}
      aria-label={`Environment: ${text}`}
      {...rest}
    />
  );
}

/* ---- EvidenceBadge — links to provenance; muted when absent ---- */
export function EvidenceBadge({ present = false, label, ...rest }) {
  return present
    ? <Badge color="var(--status-info)" glyph="❖" label={label ?? "Evidence"} aria-label="Evidence available" {...rest} />
    : <Badge color="var(--text-disabled)" glyph="◌" label={label ?? "No evidence"} style={{ borderStyle: "dashed" }} aria-label="No evidence" {...rest} />;
}

/* ---- Button foundation ---- */
const BTN_VARIANT = {
  primary:   { bg: "var(--btn-primary-bg)", fg: "var(--btn-primary-fg)", bd: "transparent" },
  secondary: { bg: "var(--btn-secondary-bg)", fg: "var(--btn-secondary-fg)", bd: "var(--border)" },
  ghost:     { bg: "transparent", fg: "var(--btn-ghost-fg)", bd: "transparent" },
  outline:   { bg: "transparent", fg: "var(--text-primary)", bd: "var(--border-strong)" },
  danger:    { bg: "var(--btn-danger-bg)", fg: "var(--btn-danger-fg)", bd: "transparent" },
};
const BTN_SIZE = { sm: { h: 28, px: 12, fs: "var(--fs-xs)" }, md: { h: "var(--btn-h)", px: 16, fs: "var(--fs-sm)" }, lg: { h: 44, px: 22, fs: "var(--fs-base)" } };
export function Button({
  variant = "secondary", size = "md", loading = false, disabled = false,
  type = "button", className = "", style, children, ...rest
}) {
  const v = BTN_VARIANT[variant] || BTN_VARIANT.secondary;
  const s = BTN_SIZE[size] || BTN_SIZE.md;
  const off = disabled || loading;
  return (
    <button
      type={type} disabled={off} aria-busy={loading || undefined}
      className={className}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
        height: s.h, padding: `0 ${s.px}px`, fontSize: s.fs, fontWeight: 500,
        color: v.fg, background: v.bg, border: `1px solid ${v.bd}`,
        borderRadius: "var(--btn-radius)", cursor: off ? "not-allowed" : "pointer",
        opacity: off ? 0.55 : 1, transition: "opacity var(--motion-fast), background var(--motion-fast)",
        fontFamily: "var(--font-ui)", ...style,
      }}
      {...rest}
    >
      {loading && <Spinner size={14} aria-hidden="true" />}
      {children}
    </button>
  );
}

/* ---- IconButton — accessible icon-only button (label required) ---- */
export function IconButton({ label, size = 34, className = "", style, children, ...rest }) {
  if (!label && process?.env?.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn("IconButton: `label` is required for accessibility.");
  }
  return (
    <button
      aria-label={label} title={label} className={className}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: size, height: size, borderRadius: "var(--rad-sm)",
        color: "var(--text-secondary)", background: "transparent",
        border: "1px solid var(--border)", cursor: "pointer",
        transition: "background var(--motion-fast)", ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ---- Input foundation ---- */
export function Input({ invalid = false, disabled = false, className = "", style, ...rest }) {
  return (
    <input
      disabled={disabled} aria-invalid={invalid || undefined}
      className={className}
      style={{
        height: "var(--input-h)", padding: "0 12px", width: "100%",
        fontSize: "var(--fs-sm)", fontFamily: "var(--font-ui)",
        color: "var(--input-fg)", background: "var(--input-bg)",
        border: `1px solid ${invalid ? "var(--input-invalid)" : "var(--input-border)"}`,
        borderRadius: "var(--input-radius)", outline: "none",
        opacity: disabled ? 0.55 : 1, transition: "border-color var(--motion-fast)",
        ...style,
      }}
      {...rest}
    />
  );
}

/* ---- Card / Panel foundation (solid default; glass opt-in) ---- */
export function Card({ variant = "base", interactive = false, className = "", style, children, onClick, ...rest }) {
  const base = variant === "glass" ? "surface-glass" : variant === "raised" ? "surface-raised" : "surface";
  return (
    <div
      className={cx(base, className)}
      onClick={onClick}
      role={interactive || onClick ? "button" : undefined}
      tabIndex={interactive || onClick ? 0 : undefined}
      style={{
        padding: "var(--card-pad)",
        cursor: interactive || onClick ? "pointer" : "default",
        transition: interactive ? "background var(--motion-fast), border-color var(--motion-fast)" : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

/* ---- Spinner (reduced-motion aware via CSS class) ---- */
export function Spinner({ size = 18, className = "", style }) {
  return (
    <span
      className={cx("saathi-spin", className)} aria-hidden="true"
      style={{
        display: "inline-block", width: size, height: size, borderRadius: "50%",
        border: "2px solid var(--border-strong)", borderTopColor: "var(--accent)", ...style,
      }}
    />
  );
}

/* ---- Skeleton (loading placeholder; reduced-motion aware) ---- */
export function Skeleton({ width = "100%", height = 14, radius = "var(--rad-sm)", className = "", style }) {
  return (
    <span
      className={cx("saathi-skeleton", className)} aria-hidden="true"
      style={{ display: "block", width, height, borderRadius: radius, background: "var(--surface-hover)", ...style }}
    />
  );
}

/* ---- State components: LoadingState / EmptyState / ErrorState / BlockedState ---- */
export function LoadingState({ label = "Loading…", className = "", style }) {
  return (
    <div role="status" aria-live="polite" className={className}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "var(--space-7)", color: "var(--text-muted)", ...style }}>
      <Spinner size={22} />
      <Text tone="muted" size="sm">{label}</Text>
    </div>
  );
}

export function EmptyState({ title = "Nothing here yet", description, icon, action, note, className = "", style }) {
  return (
    <div className={className}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 10, padding: "var(--space-7)", ...style }}>
      {icon && <div aria-hidden="true" style={{ fontSize: 28, opacity: 0.6 }}>{icon}</div>}
      <Heading level={3} size="md">{title}</Heading>
      {description && <Text tone="muted" size="sm" style={{ maxWidth: 420 }}>{description}</Text>}
      {note && <Text tone="disabled" size="xs" mono>{note}</Text>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", description, action, detail, className = "", style }) {
  return (
    <div role="alert" className={className}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 10, padding: "var(--space-7)", ...style }}>
      <StatusBadge status="danger" label="Error" />
      <Heading level={3} size="md">{title}</Heading>
      {description && <Text tone="muted" size="sm" style={{ maxWidth: 420 }}>{description}</Text>}
      {detail && <Text tone="disabled" size="xs" mono style={{ maxWidth: 480, wordBreak: "break-word" }}>{detail}</Text>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}

export function BlockedState({ title = "Blocked", reason, description, action, className = "", style }) {
  return (
    <div role="alert" className={className}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 10, padding: "var(--space-7)", ...style }}>
      <StatusBadge status="blocked" label={reason || "Blocked by policy"} />
      <Heading level={3} size="md">{title}</Heading>
      {description && <Text tone="muted" size="sm" style={{ maxWidth: 420 }}>{description}</Text>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}
