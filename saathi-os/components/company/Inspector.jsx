"use client";

// Side inspector for an agent, office, mission or evidence record. Details are
// fetched lazily from /api/v1/organization/* and re-fetched whenever the company
// snapshot changes, so the panel shows real operational state.

import { useEffect, useRef, useState } from "react";
import { orgApi } from "@/lib/useOrganization";
import { flattenTree, formatAgo, formatElapsed, statusLabel, statusMeta } from "@/lib/organization";

function StatusPill({ status, label }) {
  const m = statusMeta(status);
  return (
    <span className="co-pill" data-tone={m.tone}>
      <span aria-hidden="true">{m.glyph}</span> {label || m.label}
    </span>
  );
}

function Field({ label, children }) {
  return (
    <div className="co-field">
      <dt>{label}</dt>
      <dd>{children ?? <span className="co-muted">—</span>}</dd>
    </div>
  );
}

function useDetail(kind, id, version) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    const fn = { agent: orgApi.role, office: orgApi.office, mission: orgApi.mission, evidence: orgApi.evidence }[kind];
    if (!fn || !id) return undefined;
    setState((s) => ({ ...s, loading: !s.data }));
    fn(id)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }));
    return () => { alive = false; };
  }, [kind, id, version]);
  return state;
}

function List({ items, empty = "None" }) {
  if (!items || !items.length) return <p className="co-muted">{empty}</p>;
  return <ul className="co-bullets">{items.map((t, i) => <li key={i}>{t}</li>)}</ul>;
}

function AgentPanel({ data, onOpen, nameOf }) {
  const r = data.role;
  const step = data.current_step;
  const act = r.activity;
  return (
    <>
      <header className="co-panel-head">
        <p className="co-eyebrow">{nameOf.office(r.office_id)} · {r.tier === "mandate" ? "Strategy mandate" : "Specialist"}</p>
        <h2 tabIndex={-1} data-autofocus>{r.name}</h2>
        <div className="co-panel-pills">
          <StatusPill status={r.status} label={statusLabel(r)} />
          <span className="co-pill co-pill-authority">Authority: {r.authority}</span>
        </div>
        {r.reason ? <p className="co-reason">{r.reason}</p> : null}
      </header>

      <section className={`co-exec-box${r.financial ? " is-financial" : ""}`} aria-label="Execution authority">
        <strong>EXECUTION AUTHORITY: {r.execution_authority}</strong>
        {r.financial ? <span>Outputs are proposals. Portfolio Risk, Trading Guardian, owner approval and the Execution Gateway decide.</span> : null}
      </section>

      <dl className="co-fields">
        <Field label="Mandate">{r.mandate}</Field>
        <Field label="Current mission">{act?.mission_title || act?.objective ? (
          act?.mission_id ? <button type="button" className="co-link" onClick={() => onOpen("mission", act.mission_id)}>
            {act.mission_title || act.objective}</button> : act.objective) : null}</Field>
        <Field label="Current task">{step?.objective || act?.objective}</Field>
        <Field label="Delegated by">{step ? nameOf.role(step.delegated_by) : null}</Field>
        <Field label="Collaborating with">{step?.collaborating_with?.length ? step.collaborating_with.map(nameOf.role).join(", ") : null}</Field>
        <Field label="Reviewed by">{step?.reviewed_by?.length ? step.reviewed_by.map(nameOf.role).join(", ") : null}</Field>
        <Field label="Started">{act?.started_at ? formatAgo(act.started_at) : null}</Field>
        <Field label="Elapsed">{act?.started_at ? formatElapsed(act.started_at, act.finished_at) : null}</Field>
        <Field label="Runtime binding">{r.binding.kind}{r.binding.ref ? ` · ${r.binding.ref}` : ""}</Field>
        <Field label="Model / provider">{data.runtime?.model_policy
          ? `policy ${data.runtime.model_policy}` : "No model inference (deterministic)"}</Field>
        <Field label="Tools">{(data.runtime?.allowed_tools || r.tools || []).join(", ") || null}</Field>
        <Field label="Evidence required">{r.evidence_requirements.join(", ") || null}</Field>
        <Field label="Escalates to">{r.escalates_to ? nameOf.role(r.escalates_to) : null}</Field>
        <Field label="Token cost">{data.resource_usage?.llm_tokens ?? "Not applicable — no model calls"}</Field>
      </dl>

      {step?.output?.summary ? (
        <section className="co-section">
          <h3>Latest output</h3>
          <p>{step.output.summary}</p>
          <List items={step.output.findings} empty="No findings" />
          {step.output.gaps?.length ? (<><h4>Gaps</h4><List items={step.output.gaps} /></>) : null}
          <h4>Evidence</h4>
          <EvidenceList items={step.evidence} onOpen={onOpen} />
        </section>
      ) : null}

      <section className="co-section co-can">
        <div><h3>Can</h3><List items={r.can} empty="Advise within its mandate" /></div>
        <div><h3>Cannot</h3><List items={r.cannot} /></div>
      </section>

      <section className="co-section">
        <h3>Recent activity</h3>
        {data.recent_steps?.length ? (
          <ul className="co-activity">
            {data.recent_steps.map((s) => (
              <li key={s.id}>
                <StatusPill status={s.status} />
                <button type="button" className="co-link" onClick={() => onOpen("mission", s.mission_id)}>{s.title}</button>
                <span className="co-muted"> · {s.objective} · {formatAgo(s.started_at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="co-muted">No organization missions yet for this role.</p>}
      </section>
    </>
  );
}

function EvidenceList({ items, onOpen }) {
  if (!items?.length) return <p className="co-muted">No evidence attached</p>;
  return (
    <ul className="co-evidence">
      {items.map((e, i) => (
        <li key={i}>
          <span className="co-tag">{e.source}</span>{" "}
          {e.source === "evidence_service" && /^[0-9a-f]{8,32}$/.test(e.ref || "") ? (
            <button type="button" className="co-link" onClick={() => onOpen("evidence", e.ref)}>{e.ref}</button>
          ) : <span>{e.ref}</span>}
          {e.detail ? <span className="co-muted"> · {e.detail}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function OfficePanel({ data, onOpen, nameOf }) {
  const o = data.office;
  return (
    <>
      <header className="co-panel-head">
        <p className="co-eyebrow">{data.department.name} · Floor {data.floor.number}</p>
        <h2 tabIndex={-1} data-autofocus>{o.name}</h2>
        <p>{o.purpose}</p>
      </header>
      <dl className="co-fields">
        <Field label="Office lead">{data.lead ? nameOf.role(data.lead) : "Owner (human)"}</Field>
        <Field label="Members">{data.members.length}</Field>
        <Field label="Resource use">{data.resource_usage?.llm_inference}</Field>
      </dl>
      <section className="co-section">
        <h3>Members</h3>
        <ul className="co-members">
          {data.members.map((m) => (
            <li key={m.role_id}>
              <button type="button" className="co-link" onClick={() => onOpen("agent", m.role_id)}>{m.name}</button>
              <StatusPill status={m.status} label={statusLabel(m)} />
              {m.reason ? <span className="co-muted co-small"> {m.reason}</span> : null}
            </li>
          ))}
        </ul>
      </section>
      {[["Active missions", data.active_work], ["Queued", data.queued_work],
        ["Blocked / awaiting evidence", data.blocked_work], ["Recent outputs", data.recent_outputs]].map(([t, rows]) => (
        <section className="co-section" key={t}>
          <h3>{t}</h3>
          {rows?.length ? (
            <ul className="co-activity">
              {rows.map((w) => (
                <li key={w.id}>
                  <StatusPill status={w.status} />
                  <button type="button" className="co-link" onClick={() => onOpen("mission", w.mission_id)}>{w.title}</button>
                  <span className="co-muted"> · {nameOf.role(w.role_id)}: {w.objective}{w.reason ? ` — ${w.reason}` : ""}</span>
                </li>
              ))}
            </ul>
          ) : <p className="co-muted">None</p>}
        </section>
      ))}
    </>
  );
}

function MissionPanel({ data, onOpen, nameOf }) {
  const m = data.mission;
  const rows = flattenTree(data.tree);
  const proposal = m.report?.decision_proposal;
  return (
    <>
      <header className="co-panel-head">
        <p className="co-eyebrow">Organization mission · {m.template}</p>
        <h2 tabIndex={-1} data-autofocus>{m.title}</h2>
        <p>“{m.objective}”</p>
        <div className="co-panel-pills">
          <span className="co-pill" data-tone={m.status === "RUNNING" ? "info" : m.status === "COMPLETE" ? "success" : "warning"}>{m.status.replaceAll("_", " ")}</span>
          <span className="co-pill">No model inference</span>
          {m.pacing_sec ? <span className="co-pill">Paced {m.pacing_sec}s/step for viewing</span> : null}
        </div>
        {m.reason ? <p className="co-reason">{m.reason}</p> : null}
      </header>
      <section className="co-section">
        <h3>Delegation tree</h3>
        <ol className="co-tree" aria-label="Delegation tree">
          {rows.map((n) => (
            <li key={n.step_id || "owner"}>
              <span className="co-tree-branch" aria-hidden="true">{n.connector}</span>
              <div className="co-tree-node">
                <div className="co-tree-line">
                  <StatusPill status={n.status} />
                  {n.role_id === "owner" ? <strong>{n.name}</strong> : (
                    <button type="button" className="co-link" onClick={() => onOpen("agent", n.role_id)}>{n.name}</button>
                  )}
                </div>
                <span className="co-muted co-small">{n.objective}</span>
                {n.reason ? <span className="co-reason co-small">{n.reason}</span> : null}
              </div>
            </li>
          ))}
        </ol>
      </section>
      {m.report?.summary ? (
        <section className="co-section">
          <h3>Report to owner</h3>
          <p>{m.report.summary}</p>
          {m.report.gaps?.length ? (<><h4>Missing information</h4><List items={m.report.gaps} /></>) : null}
        </section>
      ) : null}
      {proposal ? (
        <section className="co-section co-proposal">
          <h3>Committee proposal (not a decision)</h3>
          <dl className="co-fields">
            <Field label="Proposal">{proposal.proposal}</Field>
            <Field label="Uncertainty">{proposal.uncertainty}</Field>
            <Field label="Agreement">{proposal.agreement}</Field>
            <Field label="Committee engine">{proposal.committee_engine}</Field>
            <Field label="Authorizes execution">{String(proposal.authorizes_execution)}</Field>
            <Field label="Next step">{proposal.next_step}</Field>
          </dl>
          <h4>Supporting evidence</h4>
          <List items={proposal.supporting_evidence} />
        </section>
      ) : null}
      <section className="co-section">
        <h3>Event trace</h3>
        <ol className="co-trace">
          {[...(data.events || [])].reverse().slice(-40).map((e) => (
            <li key={e.id}><span className="co-muted">{new Date(e.created_at * 1000).toLocaleTimeString()}</span>{" "}
              <code>{e.name}</code> {e.role_id ? nameOf.role(e.role_id) : ""}</li>
          ))}
        </ol>
      </section>
    </>
  );
}

function EvidencePanel({ data }) {
  const e = data.evidence;
  const m = e.metrics || {};
  return (
    <>
      <header className="co-panel-head">
        <p className="co-eyebrow">Evidence Service · {e.department}</p>
        <h2 tabIndex={-1} data-autofocus>{m.statement || e.id}</h2>
      </header>
      <dl className="co-fields">
        <Field label="Id">{e.id}</Field>
        <Field label="Recorded">{e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : null}</Field>
        <Field label="Project / episode">{[e.project, e.episode].filter(Boolean).join(" · ")}</Field>
        <Field label="Status">{e.status}</Field>
        <Field label="Confidence">{e.confidence}</Field>
        <Field label="Source">{m.source_host ? `${m.source_host} (${m.source_tier || "tier unknown"})` : null}</Field>
        <Field label="Source URL">{m.source_url ? <span className="co-mono">{m.source_url}</span> : null}</Field>
      </dl>
      <section className="co-section">
        <h3>Recorded metrics</h3>
        <pre className="co-json">{JSON.stringify(m, null, 2)}</pre>
      </section>
    </>
  );
}

export default function Inspector({ target, version, onClose, onOpen, nameOf }) {
  const { data, error, loading } = useDetail(target.kind, target.id, version);
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  useEffect(() => {
    if (data) ref.current?.querySelector("[data-autofocus]")?.focus();
  }, [data, target.id]);
  return (
    <aside className="co-inspector" ref={ref} role="dialog" aria-modal="false"
      aria-label={`${target.kind} detail`}>
      <button type="button" className="co-close" onClick={onClose} aria-label="Close detail panel">Close ✕</button>
      {loading && !data ? <p className="co-muted">Loading…</p> : null}
      {error ? <p className="co-reason">Could not load: {error.message}</p> : null}
      {data && target.kind === "agent" ? <AgentPanel data={data} onOpen={onOpen} nameOf={nameOf} /> : null}
      {data && target.kind === "office" ? <OfficePanel data={data} onOpen={onOpen} nameOf={nameOf} /> : null}
      {data && target.kind === "mission" ? <MissionPanel data={data} onOpen={onOpen} nameOf={nameOf} /> : null}
      {data && target.kind === "evidence" ? <EvidencePanel data={data} /> : null}
    </aside>
  );
}
