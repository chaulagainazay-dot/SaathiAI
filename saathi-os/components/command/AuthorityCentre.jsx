"use client";

/**
 * "Authority Centre" — what the system has decided, and what awaits the owner.
 *
 * Stronger than the operational panels, because an authority decision outranks
 * ordinary status, and calmer than an alarm, because none of this is an
 * emergency: it is the system stating its position.
 *
 * Read-only by construction. There is no approve, deny, retry, override or
 * unlock control here — not because the backend lacks the routes, but because
 * authority has to be inspectable before it is actionable.
 */

import { AUTHORITY_TYPE, PROVENANCE_LABEL } from "@/lib/command-authority-centre";

function contextWord(item) {
  if (item.contextClass === "IN_CONTEXT") return "In this conversation";
  if (item.contextClass === "BACKGROUND") return "Background";
  return "Unassociated";
}

function AuthorityRow({ item }) {
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

      <style jsx>{`
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
          {items.map((item) => <AuthorityRow key={item.id} item={item} />)}
        </div>
      )}

      <style jsx>{`
        .ac { display: flex; flex-direction: column; gap: 9px; min-width: 0; }
        .ac-list { display: flex; flex-direction: column; gap: 6px; }
      `}</style>
    </section>
  );
}
