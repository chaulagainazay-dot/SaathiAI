"use client";

/**
 * "Authority Centre" — what the system has decided, and what awaits the owner.
 *
 * Stronger than the operational panels, because an authority decision outranks
 * ordinary status, and calmer than an alarm, because none of this is an
 * emergency: it is the system stating its position.
 *
 * Phase 11 makes exactly one decision actionable: an owner may approve or deny a
 * pending approval, each behind an explicit confirmation. Nothing else is —
 * there is no retry, override, unblock or execute control, and there is no
 * execution-readiness claim, because approval is one authority step and not
 * permission to execute.
 *
 * The buttons request; they never grant. No row changes because it was clicked:
 * the server decides, and the panel learns the outcome by re-reading authority
 * truth. Hiding a button is presentation, so the server checks authority again
 * on every request regardless of what this surface shows.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AUTHORITY_TYPE, PROVENANCE_LABEL, CONFIRM_COPY } from "@/lib/command-authority-centre";

function contextWord(item) {
  if (item.contextClass === "IN_CONTEXT") return "In this conversation";
  if (item.contextClass === "BACKGROUND") return "Background";
  return "Unassociated";
}

/**
 * Confirmation before either decision, because both mutate authority state.
 *
 * Deliberately plain: an approval is routine, and dressing it as an emergency
 * would make the genuinely serious cases indistinguishable. The body says what
 * approval does and, just as importantly, what it does not promise.
 */
function ConfirmDialog({ intent, item, busy, error, onCancel, onConfirm }) {
  const copy = CONFIRM_COPY[intent];
  const confirmRef = useRef(null);
  const dialogRef = useRef(null);

  useEffect(() => { confirmRef.current?.focus(); }, []);

  const onKeyDown = useCallback((e) => {
    if (e.key === "Escape" && !busy) { e.stopPropagation(); onCancel(); return; }
    if (e.key !== "Tab") return;
    // Keep focus inside the dialog while a decision is open.
    const focusable = dialogRef.current?.querySelectorAll("button:not([disabled])");
    if (!focusable?.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }, [busy, onCancel]);

  return (
    <div
      className="ac-confirm"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`ac-confirm-h-${item.id}`}
      data-testid="ac-confirm"
      data-intent={intent}
      ref={dialogRef}
      onKeyDown={onKeyDown}
    >
      <p id={`ac-confirm-h-${item.id}`} className="ac-confirm-title">{copy.title}</p>
      {/* The action the backend recorded, quoted rather than described. */}
      {item.actionSummary ? (
        <p className="ac-confirm-action">{item.actionSummary}</p>
      ) : null}
      <p className="ac-confirm-body">{copy.body}</p>

      {error ? (
        <p className="ac-confirm-error" role="alert" data-testid="ac-error">{error}</p>
      ) : null}

      <div className="ac-confirm-actions">
        <button type="button" className="ac-btn" onClick={onCancel} disabled={busy}>
          {copy.cancel}
        </button>
        <button
          type="button"
          className="ac-btn ac-btn-primary"
          ref={confirmRef}
          onClick={onConfirm}
          disabled={busy}
          data-testid="ac-confirm-submit"
        >
          {busy ? "Working…" : copy.confirm}
        </button>
      </div>

      <style jsx>{`
        .ac-confirm {
          display: flex; flex-direction: column; gap: 6px;
          margin-top: 8px; padding: 10px;
          border-radius: 9px; min-width: 0;
          border: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.14));
          background: rgba(255, 255, 255, 0.05);
        }
        .ac-confirm-title { font-size: 12.5px; color: var(--dl-text, #eef3fc); }
        .ac-confirm-action {
          font-size: 11.5px; color: var(--dl-muted, #8b98b4);
          overflow-wrap: anywhere;
        }
        .ac-confirm-body { font-size: 11px; color: var(--dl-muted, #8b98b4); }
        .ac-confirm-error { font-size: 11px; color: var(--dl-crit, #d9534f); }
        .ac-confirm-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
        /* Declared here, not in AuthorityRow: styled-jsx only scopes markup
           rendered by the component that owns the block, so the row's .ac-btn
           rules never reached these buttons and they rendered as bare text. */
        .ac-btn {
          font: inherit; font-size: 11.5px; cursor: pointer;
          padding: 6px 14px; min-height: 36px; border-radius: 8px;
          color: var(--dl-text, #eef3fc);
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.14));
        }
        .ac-btn:disabled { opacity: 0.55; cursor: default; }
        .ac-btn-primary { background: rgba(255, 255, 255, 0.11); }
      `}</style>
    </div>
  );
}

function AuthorityRow({ item, onResolve }) {
  const [intent, setIntent] = useState(null);   // "approve" | "deny" | null
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const actionable = Boolean(item.canUserAct && item.actionableApprovalId);

  const submit = useCallback(async () => {
    if (busy) return;                            // one click, one mutation
    setBusy(true);
    setError(null);
    const res = await onResolve({
      runId: item.runId,
      approvalId: item.actionableApprovalId,
      approved: intent === "approve",
    });
    setBusy(false);
    if (res?.ok) {
      // The row is not removed here. It disappears when the refreshed authority
      // read no longer contains it -- which is the server's answer, not ours.
      setIntent(null);
      return;
    }
    setError(res?.error || null);
  }, [busy, intent, item.runId, item.actionableApprovalId, onResolve]);

  return (
    <div
      className="ac-row"
      data-testid="ac-row"
      data-authority-type={item.type}
      data-provenance={item.provenance}
      data-context={item.contextClass}
      data-authority-id={item.id}
      data-can-user-act={item.canUserAct ? "true" : "false"}
    >
      <span className="ac-mark" aria-hidden="true">
        {item.type === AUTHORITY_TYPE.BLOCKED ? "◼" : "◆"}
      </span>
      <span className="ac-body">
        <span className="ac-title">{item.title}</span>
        {item.subject ? <span className="ac-subject">{item.subject}</span> : null}
        {/* Deterministic system wording from the backend contract. */}
        {item.reason ? <span className="ac-reason">{item.reason}</span> : null}
        {item.detailCode ? <span className="ac-code">{item.detailCode}</span> : null}
        <span className="ac-meta">
          {contextWord(item)} · {PROVENANCE_LABEL[item.provenance] || item.provenance}
        </span>
      </span>

      {/* A control appears only for an approval that is genuinely actionable:
          pending, and bound to exactly one approval record. */}
      {actionable ? (
        <div className="ac-actions" data-testid="ac-actions">
          <button type="button" className="ac-btn" data-testid="ac-approve"
            onClick={() => { setError(null); setIntent("approve"); }} disabled={busy}>
            Approve
          </button>
          <button type="button" className="ac-btn" data-testid="ac-deny"
            onClick={() => { setError(null); setIntent("deny"); }} disabled={busy}>
            Deny
          </button>
        </div>
      ) : null}

      {intent ? (
        <ConfirmDialog
          intent={intent}
          item={item}
          busy={busy}
          error={error}
          onCancel={() => { setIntent(null); setError(null); }}
          onConfirm={submit}
        />
      ) : null}

      <style jsx>{`
        .ac-actions { display: flex; gap: 6px; flex-wrap: wrap; width: 100%; margin-top: 2px; }
        .ac-btn {
          font: inherit; font-size: 11.5px; cursor: pointer;
          padding: 5px 12px; min-height: 32px; border-radius: 8px;
          color: var(--dl-text, #eef3fc);
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.14));
        }
        .ac-btn:disabled { opacity: 0.55; cursor: default; }
        .ac-btn-primary { background: rgba(255, 255, 255, 0.11); }
        .ac-row {
          display: flex; align-items: flex-start; gap: 9px; padding: 8px 10px;
          border-radius: 10px; flex-wrap: wrap;
          border: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.08));
          background: rgba(255, 255, 255, 0.03);
          border-left: 3px solid var(--dl-muted, #8b98b4);
        }
        /* A block is the system refusing; an approval is the system waiting.
           Both are marked structurally, so neither depends on colour, and
           neither is styled as an alarm. */
        .ac-row[data-authority-type="BLOCKED"] {
          border-left-color: var(--dl-text, #eef3fc);
          background: rgba(255, 255, 255, 0.055);
        }
        .ac-mark {
          font-family: var(--font-mono, ui-monospace); font-size: 10px;
          line-height: 1.6; flex-shrink: 0; color: var(--dl-text, #eef3fc);
        }
        .ac-body { display: flex; flex-direction: column; gap: 1px; flex: 1 1 140px; min-width: 0; }
        .ac-title { font-size: 13px; color: var(--dl-text, #eef3fc); }
        .ac-subject {
          font-size: 11.5px; color: var(--dl-muted, #8b98b4);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .ac-reason { font-size: 11px; color: var(--dl-muted, #8b98b4); }
        .ac-code {
          font-family: var(--font-mono, ui-monospace); font-size: 10px;
          color: var(--dl-muted, #8b98b4); opacity: 0.85;
        }
        .ac-meta {
          font-family: var(--font-mono, ui-monospace); font-size: 9px;
          letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--dl-muted, #8b98b4); padding-top: 2px;
        }
      `}</style>
    </div>
  );
}

export default function AuthorityCentre({ model }) {
  const items = model?.items || [];

  return (
    <section className="dl-panel ac" aria-labelledby="ac-h" data-testid="authority-centre">
      <h2 id="ac-h" className="dl-subh">Authority centre</h2>

      {items.length === 0 ? (
        // Nothing is held right now. That is not a claim that anything is
        // cleared to execute -- this surface never makes that claim.
        <p className="dl-muted" data-testid="ac-empty">Nothing is waiting on your authority.</p>
      ) : (
        <div className="ac-list">
          {items.map((item) => (
            <AuthorityRow key={item.id} item={item} onResolve={model.resolveApproval} />
          ))}
        </div>
      )}

      <style jsx>{`
        .ac { display: flex; flex-direction: column; gap: 9px; min-width: 0; }
        .ac-list { display: flex; flex-direction: column; gap: 6px; }
      `}</style>
    </section>
  );
}
