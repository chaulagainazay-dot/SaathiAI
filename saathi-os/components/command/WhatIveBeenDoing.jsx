"use client";

/**
 * "What I've been doing" — the history surface.
 *
 * Deliberately the quietest of the three panels. History is informative, never
 * urgent: a failed run here must not read as louder than an unresolved item in
 * "What needs you", because one is a fact and the other is a request.
 *
 * Read-only by construction — there is no control to retry, re-run or clear.
 */

import { VERIFICATION, VERIFICATION_LABEL } from "@/lib/command-history";

function contextWord(item) {
  if (item.contextClass === "IN_CONTEXT") return "In this conversation";
  if (item.contextClass === "BACKGROUND") return "Background";
  return "Unassociated";
}

function HistoryRow({ item }) {
  const verification = VERIFICATION_LABEL[item.verificationState] || null;

  // "Completed · Verified" reads as two facts, which is what they are.
  const line = [item.terminalLabel, verification].filter(Boolean).join(" · ");

  return (
    <div
      className="wibd-row"
      data-testid="wibd-row"
      data-terminal-state={item.terminalState}
      data-verification={item.verificationState}
      data-context={item.contextClass}
      data-history-id={item.id}
    >
      <span className="wibd-body">
        <span className="wibd-subject">{item.subject}</span>
        <span className="wibd-state">{line}</span>
        {/* Only a reason the backend wrote; absence stays absence. */}
        {item.failureReason ? (
          <span className="wibd-reason">{item.failureReason}</span>
        ) : null}
        <span className="wibd-meta">{contextWord(item)}</span>
      </span>

      <style jsx>{`
        .wibd-row {
          display: flex; align-items: flex-start; gap: 9px;
          padding: 6px 9px; border-radius: 10px;
          border: 1px solid transparent;
          border-left: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.08));
        }
        .wibd-body { display: flex; flex-direction: column; gap: 1px; flex: 1 1 140px; min-width: 0; }
        .wibd-subject {
          font-size: 12.5px; color: var(--dl-text, #eef3fc);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .wibd-state { font-size: 11px; color: var(--dl-muted, #8b98b4); }
        /* A verification failure is a distinct truth from a run failure, so it
           is named rather than folded into the terminal state. */
        .wibd-row[data-verification="FAILED"] .wibd-state { color: var(--dl-warn, #c9a227); }
        .wibd-reason { font-size: 10.5px; color: var(--dl-muted, #8b98b4); opacity: 0.85; }
        .wibd-meta {
          font-family: var(--font-mono, ui-monospace); font-size: 9px;
          letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--dl-muted, #8b98b4); padding-top: 2px;
        }
      `}</style>
    </div>
  );
}

export default function WhatIveBeenDoing({ model }) {
  const items = model?.items || [];
  const withheld = model?.withheld || 0;

  return (
    <section className="dl-panel wibd" aria-labelledby="wibd-h" data-testid="what-ive-been-doing">
      <h2 id="wibd-h" className="dl-subh">What I&apos;ve been doing</h2>

      {items.length === 0 ? (
        // Empty, not unavailable -- the difference matters.
        <p className="dl-muted" data-testid="wibd-empty">Nothing recorded yet.</p>
      ) : (
        <div className="wibd-list">
          {items.map((item) => <HistoryRow key={item.id} item={item} />)}
        </div>
      )}

      {withheld > 0 ? (
        <p className="dl-muted wibd-withheld" data-testid="wibd-withheld">
          {withheld} older {withheld === 1 ? "item" : "items"} not shown.
        </p>
      ) : null}

      <style jsx>{`
        /* Quieter than attention by design: history informs, it does not ask. */
        .wibd { display: flex; flex-direction: column; gap: 8px; min-width: 0; opacity: 0.92; }
        .wibd-list { display: flex; flex-direction: column; gap: 3px; }
        .wibd-withheld { font-size: 10.5px; }
      `}</style>
    </section>
  );
}
