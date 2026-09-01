"use client";

/**
 * "Who I've got working" — the orchestration surface around the conversation.
 *
 * Observational only. It renders what the backend asserted and nothing else:
 * no progress unless the server reported it, no invented agents, no actions.
 * The centre stays dominant; this panel is deliberately low-density.
 */

import { CONTEXT_CLASS } from "@/lib/agent-orchestration";

function livenessText(item) {
  const { kind, percent } = item.liveness || {};
  if (kind === "PROGRESS" && typeof percent === "number") return `${percent}% reported`;
  if (kind === "HEARTBEAT") return "still running";
  // UNKNOWN must stay visibly truthful — never 0%.
  return item.lifecycle.active ? "progress not reported" : "";
}

function WorkRow({ item, inContext }) {
  const detail = [item.lifecycle.label, livenessText(item)].filter(Boolean).join(" · ");
  return (
    <div className="wiw-row" data-terminal={item.lifecycle.terminal ? "true" : "false"}
      data-needs-you={item.needsYou || ""} data-testid="wiw-row" data-run-id={item.runId}>
      <span className="wiw-dot" data-active={item.lifecycle.active ? "true" : "false"} aria-hidden="true" />
      <span className="wiw-body">
        <span className="wiw-agent">{item.agent}</span>
        <span className="wiw-detail">{detail}</span>
        {item.objective ? <span className="wiw-objective">{item.objective}</span> : null}
        {item.failureReason ? <span className="wiw-failure">{item.failureReason}</span> : null}
      </span>
      {/* Classification is text, never colour alone. */}
      <span className="wiw-class">{inContext ? "In this conversation" : "Background"}</span>
    </div>
  );
}

export default function WhoIsWorking({ model }) {
  const inContext = model?.inContext || [];
  const background = [...(model?.background || []), ...(model?.unassociated || [])];
  const nothing = inContext.length === 0 && background.length === 0;

  return (
    <section className="dl-panel wiw" aria-labelledby="wiw-h" data-testid="who-is-working">
      <h2 id="wiw-h" className="dl-subh">Who I&apos;ve got working</h2>

      {nothing ? (
        <p className="dl-muted" data-testid="wiw-empty">No agents working right now.</p>
      ) : null}

      {inContext.length > 0 ? (
        <div className="wiw-group" data-group="in-context">
          <div className="wiw-group-label">In this conversation</div>
          {inContext.map((item) => (
            <WorkRow key={item.runId} item={item} inContext />
          ))}
        </div>
      ) : null}

      {background.length > 0 ? (
        <div className="wiw-group" data-group="background">
          <div className="wiw-group-label">In the background</div>
          {background.map((item) => (
            <WorkRow key={item.runId} item={item} inContext={false} />
          ))}
        </div>
      ) : null}

      <style jsx>{`
        .wiw { display: flex; flex-direction: column; gap: 10px; }
        .wiw-group { display: flex; flex-direction: column; gap: 6px; }
        .wiw-group-label {
          font-family: var(--font-mono, ui-monospace); font-size: 10px;
          letter-spacing: 0.14em; text-transform: uppercase; color: var(--dl-muted, #8b98b4);
        }
        .wiw-row {
          display: flex; align-items: flex-start; gap: 9px; padding: 7px 9px;
          border: 1px solid var(--glass-frame-border, rgba(255,255,255,0.08));
          border-radius: 10px; background: rgba(255,255,255,0.02);
        }
        .wiw-row[data-terminal="true"] { opacity: 0.62; }
        .wiw-dot {
          width: 7px; height: 7px; border-radius: 50%; margin-top: 5px; flex-shrink: 0;
          background: var(--dl-muted, #6c7a96);
        }
        .wiw-dot[data-active="true"] { background: var(--signal-active, #5b9fd4); }
        .wiw-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
        .wiw-agent { font-size: 13px; color: var(--dl-text, #eef3fc); }
        .wiw-detail { font-size: 11.5px; color: var(--dl-muted, #8b98b4); }
        .wiw-objective {
          font-size: 11px; color: var(--dl-muted, #8b98b4); opacity: 0.85;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .wiw-failure { font-size: 11px; color: var(--dl-crit, #d9534f); }
        .wiw-class {
          font-family: var(--font-mono, ui-monospace); font-size: 9px;
          letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--dl-muted, #8b98b4); white-space: nowrap; padding-top: 3px;
        }
      `}</style>
    </section>
  );
}
