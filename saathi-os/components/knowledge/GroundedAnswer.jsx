"use client";

import { useId, useState } from "react";
import { claimKindLabel, freshnessLabel } from "@/lib/knowledge";

/**
 * UI-safe grounded answer presentation.
 * Never renders absolute filesystem paths or secret filenames.
 */
export default function GroundedAnswer({
  text = "",
  grounding = null,
  compact = false,
}) {
  const baseId = useId();
  const [open, setOpen] = useState(false);
  const g = grounding || {};
  const citations = Array.isArray(g.citations) ? g.citations : [];
  const conflicts = Array.isArray(g.conflicts) ? g.conflicts : [];
  const stale = Array.isArray(g.stale_warnings) ? g.stale_warnings : [];
  const grounded = Boolean(g.grounded);
  const noEvidence = Boolean(g.no_evidence);
  const claim = claimKindLabel(g.claim_kind);

  return (
    <div
      className="knowledge-grounded-answer"
      data-grounded={grounded ? "true" : "false"}
      data-no-evidence={noEvidence ? "true" : "false"}
      data-claim-kind={g.claim_kind || ""}
    >
      <div className="knowledge-answer-meta" aria-live="polite">
        <span
          className={`knowledge-badge ${grounded ? "is-grounded" : "is-ungrounded"}`}
          title={grounded ? "Answer used indexed sources" : "No grounding applied"}
        >
          {grounded ? "Grounded" : noEvidence ? "No evidence" : "Ungrounded"}
        </span>
        <span className="knowledge-claim-kind">{claim}</span>
        {conflicts.length > 0 ? (
          <span className="knowledge-badge is-conflict" role="status">
            Conflict warning
          </span>
        ) : null}
      </div>

      {text ? (
        <div className="knowledge-answer-text" role="article">
          {text}
        </div>
      ) : null}

      {conflicts.length > 0 ? (
        <div className="knowledge-conflict" role="alert">
          <strong>Source conflict</strong>
          <ul>
            {conflicts.map((c, i) => (
              <li key={`${baseId}-c-${i}`}>{c.summary || c.type || "Conflict"}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {stale.length > 0 ? (
        <div className="knowledge-stale" role="status">
          {stale.slice(0, 3).map((s, i) => (
            <div key={`${baseId}-s-${i}`}>{s}</div>
          ))}
        </div>
      ) : null}

      {citations.length > 0 ? (
        <div className="knowledge-sources">
          <button
            type="button"
            className="knowledge-sources-toggle"
            aria-expanded={open}
            aria-controls={`${baseId}-sources`}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide sources" : `Sources (${citations.length})`}
          </button>
          {open || !compact ? (
            <ul id={`${baseId}-sources`} className="knowledge-source-list">
              {citations.map((c) => {
                const fr = freshnessLabel(c.freshness);
                return (
                  <li key={c.chunk_id || c.document_id || c.source_id} className="knowledge-source-item">
                    <div className="knowledge-source-title">
                      <strong>{c.title || c.source_id}</strong>
                      <span className={`knowledge-freshness tone-${fr.tone}`}>{fr.label}</span>
                    </div>
                    <div className="knowledge-source-meta">
                      <span>{c.authority}</span>
                      <span>{c.source_type}</span>
                      {c.milestone ? <span>{c.milestone}</span> : null}
                      {c.commit_sha ? <span>sha {c.commit_sha}</span> : null}
                    </div>
                    {c.path ? (
                      <code className="knowledge-source-path" title="Repository-relative path">
                        {String(c.path).replace(/^\/+/, "")}
                      </code>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      ) : noEvidence ? (
        <p className="knowledge-empty" role="status">
          No indexed authoritative sources matched this question.
        </p>
      ) : null}
    </div>
  );
}
