"use client";

/**
 * "What needs you" — a concise attention queue, not a feed.
 *
 * Read-first by construction: there is no control here, so there is nothing to
 * click that could approve, execute, retry or clear anything. Rows state what
 * the backend asserted and stop.
 *
 * Trust is carried by structure and wording, never by colour alone: an
 * AUTHORITATIVE item is marked with an explicit authority glyph and a solid
 * rule, an ADVISORY one is deliberately quieter, and every item spells out its
 * class in text for anyone who cannot see either.
 */

import { ATTENTION_TYPE, AUTHORITY_CLASS } from "@/lib/command-attention";

/** Authority is stated in words, so it never depends on seeing the styling. */
const AUTHORITY_WORD = {
  [AUTHORITY_CLASS.AUTHORITATIVE]: "Authoritative",
  [AUTHORITY_CLASS.TRUSTED_RUNTIME]: "Runtime-reported",
  [AUTHORITY_CLASS.ADVISORY]: "Advisory",
};

/** A glyph, not a colour, distinguishes the classes for quick scanning. */
const AUTHORITY_GLYPH = {
  [AUTHORITY_CLASS.AUTHORITATIVE]: "◆", // filled — the system decided
  [AUTHORITY_CLASS.TRUSTED_RUNTIME]: "◇", // hollow — the runtime reported
  [AUTHORITY_CLASS.ADVISORY]: "·", // quiet — for information
};

function contextWord(item) {
  if (item.type === ATTENTION_TYPE.DEGRADED) return "System-wide";
  return item.contextClass === "IN_CONTEXT" ? "In this conversation" : "Background";
}

function AttentionRow({ item }) {
  return (
    <div
      className="wny-row"
      data-testid="wny-row"
      data-type={item.type}
      data-authority={item.authorityClass}
      data-context={item.contextClass}
      data-attention-id={item.id}
    >
      <span className="wny-glyph" aria-hidden="true">{AUTHORITY_GLYPH[item.authorityClass]}</span>
      <span className="wny-body">
        <span className="wny-title">{item.title}</span>
        {item.subject ? <span className="wny-subject">{item.subject}</span> : null}
        {/* Only a reason the backend produced; absence stays absent. */}
        {item.reason ? <span className="wny-reason">{item.reason}</span> : null}
        <span className="wny-meta">
          {contextWord(item)} · {AUTHORITY_WORD[item.authorityClass]}
        </span>
      </span>

      <style jsx>{`
        .wny-row {
          display: flex; align-items: flex-start; gap: 9px; padding: 7px 9px;
          border-radius: 10px; background: rgba(255, 255, 255, 0.02);
          border: 1px solid var(--glass-frame-border, rgba(255, 255, 255, 0.08));
          flex-wrap: wrap;
        }
        /* Structural weight, not colour, separates the trust classes. An
           advisory item must never read as louder than an authoritative one. */
        .wny-row[data-authority="AUTHORITATIVE"] {
          border-left: 2px solid var(--dl-text, #eef3fc);
          background: rgba(255, 255, 255, 0.045);
        }
        .wny-row[data-authority="TRUSTED_RUNTIME"] { border-left: 2px solid var(--dl-muted, #8b98b4); }
        .wny-row[data-authority="ADVISORY"] { opacity: 0.78; }
        .wny-glyph {
          font-family: var(--font-mono, ui-monospace); font-size: 10px;
          line-height: 1.5; flex-shrink: 0; color: var(--dl-muted, #8b98b4);
        }
        .wny-row[data-authority="AUTHORITATIVE"] .wny-glyph { color: var(--dl-text, #eef3fc); }
        .wny-body { display: flex; flex-direction: column; gap: 1px; flex: 1 1 140px; min-width: 0; }
        .wny-title { font-size: 13px; color: var(--dl-text, #eef3fc); }
        .wny-subject {
          font-size: 11.5px; color: var(--dl-muted, #8b98b4);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .wny-reason { font-size: 11px; color: var(--dl-muted, #8b98b4); opacity: 0.85; }
        .wny-meta {
          font-family: var(--font-mono, ui-monospace); font-size: 9px;
          letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--dl-muted, #8b98b4); padding-top: 2px;
        }
      `}</style>
    </div>
  );
}

export default function WhatNeedsYou({ model }) {
  const items = model?.items || [];
  const withheld = model?.withheldFailed || 0;

  return (
    <section className="dl-panel wny" aria-labelledby="wny-h" data-testid="what-needs-you">
      <h2 id="wny-h" className="dl-subh">What needs you</h2>

      {items.length === 0 ? (
        <p className="dl-muted" data-testid="wny-empty">Nothing needs you right now.</p>
      ) : (
        <div className="wny-list">
          {items.map((item) => <AttentionRow key={item.id} item={item} />)}
        </div>
      )}

      {withheld > 0 ? (
        <p className="dl-muted wny-withheld" data-testid="wny-withheld">
          {withheld} older {withheld === 1 ? "failure" : "failures"} not listed.
        </p>
      ) : null}

      <style jsx>{`
        .wny { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
        .wny-list { display: flex; flex-direction: column; gap: 6px; }
        .wny-withheld { font-size: 10.5px; }
      `}</style>
    </section>
  );
}
