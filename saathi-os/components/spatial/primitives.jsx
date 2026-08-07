"use client";
// M59 — small presentational primitives shared across the spatial workspaces.
// Truthful by construction: Field renders whatever value it's given (callers
// pass explicit "Unavailable"/"Unknown" sentinels rather than blanks).

/* Map a workspace signal → the glass-frame modifier class. */
export function frameClass(signal) {
  if (signal === "danger") return "glass-frame--danger";
  if (signal === "attention") return "glass-frame--authority";
  if (signal === "active") return "glass-frame--active";
  return "";
}

export function Field({ label, value, mono }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
      <span className="eyebrow" style={{ color: "var(--text-muted)", flex: "none" }}>{label}</span>
      <span className={mono ? "mono" : ""} style={{ fontSize: "var(--fs-sm)", color: "var(--text-secondary)", textAlign: "right", wordBreak: "break-word" }}>
        {value === "" || value === null || value === undefined ? "—" : value}
      </span>
    </div>
  );
}

export function Metric({ label, value, tone = "idle" }) {
  const color =
    tone === "active" ? "var(--signal-active)"
    : tone === "attention" ? "var(--signal-attention)"
    : tone === "danger" ? "var(--signal-danger)"
    : tone === "success" ? "var(--signal-success)"
    : "var(--text-muted)";
  const unknown = value === null || value === undefined;
  return (
    <span style={{ display: "flex", flexDirection: "column" }}>
      <span className="mono" style={{ fontSize: "var(--fs-lg)", color: unknown ? "var(--text-muted)" : color, lineHeight: 1 }}>{unknown ? "—" : value}</span>
      <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{label}</span>
    </span>
  );
}

/* A titled glass section with an optional signal edge. */
export function SectionPanel({ title, signal = "idle", meta, children, id }) {
  return (
    <section id={id} className={`glass-frame ${frameClass(signal)}`} style={{ padding: "var(--space-5)" }} aria-label={title}>
      {(title || meta) && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--space-4)" }}>
          {title && <h2 className="display" style={{ fontSize: "var(--fs-lg)", margin: 0 }}>{title}</h2>}
          {meta && <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{meta}</span>}
        </div>
      )}
      {children}
    </section>
  );
}
