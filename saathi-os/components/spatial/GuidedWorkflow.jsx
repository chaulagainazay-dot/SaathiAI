"use client";
// M60 — shared guided-workflow primitives. Not one giant component: a stepper,
// a stage row, a role-boundary notice, a draft-recovery banner, a server-
// reconciliation state chip, and a completion summary — composed by the routes.
import { StatusPulse } from "./frame";
import { frameClass } from "./primitives";

/* ---- WorkflowStepper — accessible step indicator with keyboard-reachable steps */
export function WorkflowStepper({ steps, activeId, onSelect }) {
  return (
    <nav aria-label="Workflow steps" className="glass-frame" style={{ padding: "var(--space-3) var(--space-4)" }}>
      <ol style={{ display: "flex", flexWrap: "wrap", gap: 4, listStyle: "none", margin: 0, padding: 0 }}>
        {steps.map((s, i) => {
          const active = s.id === activeId;
          return (
            <li key={s.id} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <button
                className="ws-chip"
                aria-current={active ? "step" : undefined}
                aria-pressed={active}
                onClick={() => onSelect?.(s.id)}
                style={active ? { borderColor: "color-mix(in srgb, var(--signal-active) 55%, transparent)", color: "var(--text-primary)" } : undefined}
              >
                <span className="mono" style={{ fontSize: "var(--fs-2xs)", opacity: 0.7 }}>{i + 1}</span>
                {s.complete && <span aria-label="complete" style={{ color: "var(--signal-success)" }}>✓</span>}
                {s.title}
                {s.safety && <span aria-label="safety step" title="Safety step" style={{ color: "var(--signal-attention)" }}>•</span>}
              </button>
              {i < steps.length - 1 && <span aria-hidden="true" style={{ color: "var(--text-muted)" }}>›</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/* ---- WorkflowStage — a lineage node with an explicit state ---- */
const STAGE_SIGNAL = { proposed: "idle", approved: "active", active: "active", blocked: "danger", completed: "success", failed: "danger", cancelled: "idle", unavailable: "idle" };
export function WorkflowStage({ label, state, detail }) {
  const sig = STAGE_SIGNAL[state] || "idle";
  return (
    <div className={`glass-frame ${frameClass(sig === "success" ? "active" : sig)}`} style={{ padding: "10px 12px", minWidth: 120 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusPulse signal={sig} size={7} />
        <span style={{ fontSize: "var(--fs-sm)", color: "var(--text-primary)" }}>{label}</span>
      </div>
      <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 2 }}>{state} · {detail}</div>
    </div>
  );
}

/* ---- RoleBoundaryNotice — honest permission state, not just hidden buttons ---- */
export function RoleBoundaryNotice({ role, permission, action }) {
  if (permission === "permitted") return null;
  const map = {
    insufficient: { c: "var(--signal-danger)", t: `Insufficient permission for "${action}" as ${role || "unknown role"}.` },
    requires_approval: { c: "var(--signal-attention)", t: `"${action}" requires an approval as ${role}.` },
    "read-only": { c: "var(--text-muted)", t: `"${action}" is read-only for ${role}.` },
    unavailable: { c: "var(--text-muted)", t: `"${action}" is unavailable.` },
    unknown: { c: "var(--text-muted)", t: `Permission for "${action}" is unknown.` },
  };
  const m = map[permission] || map.unknown;
  return (
    <p role="note" className="mono" style={{ fontSize: "var(--fs-2xs)", color: m.c, margin: "6px 0 0" }}>
      {m.t} Server authorization is always enforced regardless of this UI.
    </p>
  );
}

/* ---- DraftRecoveryBanner ---- */
export function DraftRecoveryBanner({ savedAt, onResume, onDiscard, label = "draft" }) {
  if (!savedAt) return null;
  return (
    <div className="glass-frame glass-frame--authority" style={{ padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }} role="status">
      <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-attention)" }}>Local {label} · saved {savedAt}</span>
      <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
        <button className="ws-chip" onClick={onResume}>Resume</button>
        <button className="ws-chip" onClick={onDiscard}>Discard</button>
      </span>
    </div>
  );
}

/* ---- ServerReconciliationState ---- */
const RECON_LABEL = {
  idle: ["", "var(--text-muted)"], submitting: ["Submitting…", "var(--signal-attention)"],
  server_accepted: ["Server accepted", "var(--signal-active)"], server_rejected: ["Server rejected", "var(--signal-danger)"],
  reconciling: ["Reconciling from server…", "var(--signal-attention)"], reconciled: ["Reconciled with server", "var(--signal-success)"],
  conflict: ["Conflict — server state differs", "var(--signal-danger)"], stale: ["Stale state — reload required", "var(--signal-danger)"],
  unknown: ["Unknown result — verify on server", "var(--text-muted)"],
};
export function ServerReconciliationState({ state }) {
  const [label, color] = RECON_LABEL[state] || RECON_LABEL.unknown;
  if (!label) return null;
  return <span role="status" aria-live="polite" className="mono" style={{ fontSize: "var(--fs-2xs)", color }}>{label}</span>;
}

/* ---- WorkflowCompletionSummary ---- */
export function WorkflowCompletionSummary({ title, items = [], nextRoute, onNext }) {
  return (
    <div className="glass-frame glass-frame--active" style={{ padding: "var(--space-5)" }} role="region" aria-label={title}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <StatusPulse signal="success" size={9} />
        <h2 className="display" style={{ fontSize: "var(--fs-lg)", margin: 0 }}>{title}</h2>
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text-secondary)", fontSize: "var(--fs-sm)", display: "grid", gap: 4 }}>
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
      {nextRoute && <button onClick={onNext} style={{ marginTop: 14, background: "color-mix(in srgb, var(--signal-active) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 45%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: "pointer" }}>Continue →</button>}
    </div>
  );
}
