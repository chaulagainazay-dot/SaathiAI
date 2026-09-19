"use client";

/**
 * AI Company — the visual organization view of SaathiOS.
 * Every worker maps to a canonical backend role (/api/v1/organization/company);
 * statuses are derived from real runtime state, never invented. Missions run
 * deterministic read-only analyses; no agent here has execution authority.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import "./company.css";
import Building, { CompanyList, Icon } from "@/components/company/Building";
import Inspector from "@/components/company/Inspector";
import DelegationOverlay from "@/components/company/DelegationOverlay";
import AgentWorker from "@/components/company/AgentWorker";
import { orgApi, useOrganization } from "@/lib/useOrganization";
import {
  activePath, activeRoles, activityText, formatAgo, headerMetrics, indexCompany,
  statusMeta, systemTone, treeRoleIds,
} from "@/lib/organization";
import { LoadingState, ErrorState } from "@/components/ui";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return undefined;
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

function Metric({ label, value, tone }) {
  return (
    <div className="co-metric" data-tone={tone}>
      <span className="co-metric-value">{value ?? "—"}</span>
      <span className="co-metric-label">{label}</span>
    </div>
  );
}

function CommandBar({ onStarted, disabled }) {
  const [text, setText] = useState("");
  const [templates, setTemplates] = useState([]);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { orgApi.templates().then((d) => setTemplates(d.templates || [])).catch(() => {}); }, []);
  const start = async (body) => {
    setBusy(true);
    setMsg(null);
    try {
      const d = await orgApi.startMission(body);
      setText("");
      onStarted(d.mission.id);
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="co-command">
      <form className="co-command-form" onSubmit={(e) => { e.preventDefault(); if (text.trim()) start({ objective: text.trim() }); }}>
        <label htmlFor="co-command-input" className="co-sr">Give Saathi a goal</label>
        <input id="co-command-input" value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
          placeholder="Saathi, analyze my portfolio and identify important risks…" disabled={busy || disabled} />
        <button type="submit" disabled={busy || disabled || !text.trim()}>Start mission</button>
      </form>
      <div className="co-templates" aria-label="Mission templates">
        {templates.map((t) => (
          <button key={t.template_id} type="button" className="co-chip" disabled={busy || disabled}
            onClick={() => start({ template_id: t.template_id, objective: t.objective })}>{t.title}</button>
        ))}
      </div>
      <p className="co-command-note">
        Missions run deterministic, read-only analyses through the organization. No orders, approvals or risk-limit changes.
        {disabled ? " A mission is already running (limit 1)." : ""}
      </p>
      {msg ? <p className="co-reason" role="alert">{msg}</p> : null}
    </div>
  );
}

function Rail({ snap, systems, onOpen, liveConnected }) {
  const focus = snap.today_focus;
  return (
    <aside className="co-rail" aria-label="Operations">
      <section className="co-card">
        <h2>Today’s focus</h2>
        {focus?.state === "OK" ? (
          <ul className="co-focus">
            {focus.items.map((g) => (
              <li key={g.id}><span aria-hidden="true">{g.done ? "✓" : "○"}</span> {g.text}</li>
            ))}
          </ul>
        ) : (
          <p className="co-muted">
            {focus?.state === "EMPTY" ? "No owner goals recorded." : `Unavailable${focus?.reason ? ` — ${focus.reason}` : ""}`}{" "}
            <Link href="/ceo">Set goals in CEO OS</Link>
          </p>
        )}
      </section>

      <section className="co-card">
        <div className="co-card-head">
          <h2>Live activity</h2>
          <span className="co-live" data-on={liveConnected ? "1" : "0"}>{liveConnected ? "Live" : "Polling"}</span>
        </div>
        {snap.live_activity?.length ? (
          <ul className="co-feed">
            {snap.live_activity.slice(0, 7).map((e) => (
              <li key={e.id}>
                <button type="button" className="co-link" onClick={() => e.role_id ? onOpen("agent", e.role_id) : onOpen("mission", e.mission_id)}>
                  {activityText(e)}
                </button>
                <span className="co-muted co-small">{formatAgo(e.at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="co-muted">No organization activity yet. Start a mission to watch the company work.</p>}
      </section>

      <section className="co-card">
        <h2>System status</h2>
        {!systems ? <p className="co-muted">Checking…</p> : systems.error ? (
          <p className="co-muted">Unknown — {systems.error}</p>
        ) : (
          <ul className="co-systems">
            {systems.systems.map((s) => (
              <li key={s.system_id} title={s.detail}>
                <span className="co-sys-dot" data-tone={systemTone(s.status)} aria-hidden="true" />
                <span className="co-sys-name">{s.name}</span>
                <span className="co-sys-status" data-tone={systemTone(s.status)}>{s.status.replace("_", " ")}</span>
                <span className="co-sys-detail">{s.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="co-card">
        <h2>Authority chain</h2>
        <p className="co-muted co-small">Reasoning (proposals): {snap.reasoning_chain?.join(" → ")}</p>
        <ol className="co-chain">
          {snap.authority_chain?.map((s) => (
            <li key={s.system_id}>
              <span className="co-chain-name">{s.name}</span>
              <span className="co-chain-status" data-tone={s.status === "UNKNOWN" ? "neutral" : "success"}>{s.status}</span>
              <span className="co-muted co-small">{s.detail}</span>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}

export default function CompanyPage() {
  const { snap, error, loading, systems, refresh, liveConnected, missionActive } = useOrganization();
  const reduced = useReducedMotion();
  const [target, setTarget] = useState(null);
  const [missionTree, setMissionTree] = useState(null);
  const buildingRef = useRef(null);
  const index = useMemo(() => indexCompany(snap), [snap]);

  const activeMissionId = snap?.active_missions?.[0]?.id || null;
  useEffect(() => {
    if (!activeMissionId) { setMissionTree(null); return; }
    let alive = true;
    orgApi.mission(activeMissionId).then((d) => alive && setMissionTree(d.tree)).catch(() => {});
    return () => { alive = false; };
  }, [activeMissionId, snap?.generated_at]);

  const missionIds = useMemo(() => (missionTree ? treeRoleIds(missionTree) : new Set()), [missionTree]);
  const path = useMemo(() => activePath(missionTree), [missionTree]);
  const highlightOffices = useMemo(() => {
    const s = new Set();
    if (index) missionIds.forEach((id) => { const r = index.roles[id]; if (r) s.add(r.office_id); });
    return s;
  }, [missionIds, index]);

  const open = useCallback((kind, id) => setTarget(id ? { kind, id } : null), []);
  const nameOf = useMemo(() => ({
    role: (id) => (id === "owner" ? snap?.owner?.name || "Owner" : index?.roles[id]?.name || id),
    office: (id) => index?.offices[id]?.name || id,
  }), [index, snap]);

  if (loading && !snap) return <div className="co-page"><LoadingState label="Opening the headquarters…" /></div>;
  if (error && !snap) {
    return (
      <div className="co-page">
        <ErrorState title="AI Company unavailable" description={error.message}
          action={<button type="button" onClick={refresh}>Retry</button>} />
      </div>
    );
  }
  const m = headerMetrics(snap);
  const active = activeRoles(snap);

  return (
    <div className={`co-page${target ? " has-inspector" : ""}`}>
      <header className="co-header">
        <div className="co-title">
          <p className="co-eyebrow">Operate · AI Company</p>
          <h1>SaathiOS <span>AI Company</span></h1>
          <p className="co-sub">A team of logical agents working for {snap.owner?.name}. Statuses come from the live runtime.</p>
        </div>
        <div className="co-metrics" role="group" aria-label="Organization metrics">
          <Metric label="Total agents" value={m.total} />
          <Metric label="Active" value={m.active} tone="success" />
          <Metric label="Idle" value={m.idle} />
          <Metric label="In review" value={m.in_review} tone="pending" />
          <Metric label="Queued / waiting" value={(m.assigned || 0) + (m.waiting || 0)} tone="warning" />
          <Metric label="Blocked / errors" value={(m.blocked || 0) + (m.errors || 0)} tone="danger" />
          <Metric label="Unavailable" value={m.unavailable} />
        </div>
      </header>

      <CommandBar disabled={missionActive} onStarted={(id) => { open("mission", id); refresh(); }} />

      {Object.values(snap.sources || {}).some((s) => s && s.ok === false) ? (
        <p className="co-banner" role="status">
          Some runtime sources could not be read — affected agents show UNKNOWN.
        </p>
      ) : null}

      <div className="co-layout">
        <main className="co-main">
          <div className="co-building-wrap" ref={buildingRef}>
            {path.length > 1 ? (
              <p className="co-path" role="status" aria-live="polite">
                {path.map(nameOf.role).join(" → ")}
              </p>
            ) : null}
            <Building index={index} owner={snap.owner} desk={snap.owner_desk} selectedId={target?.kind === "agent" ? target.id : null}
              onSelectAgent={(id) => open("agent", id)} onOpenOffice={(id) => open("office", id)}
              reducedMotion={reduced} missionIds={missionIds} highlightOffices={highlightOffices} />
            <DelegationOverlay containerRef={buildingRef} path={path} />
          </div>
          <CompanyList index={index} onSelectAgent={(id) => open("agent", id)} onOpenOffice={(id) => open("office", id)} />

          <div className="co-bottom">
            <section className="co-card co-active" aria-label="Active agents">
              <h2>Active agents ({active.length})</h2>
              {active.length ? (
                <div className="co-active-row">
                  {active.slice(0, 10).map((r) => (
                    <div key={r.role_id} className="co-active-card">
                      <AgentWorker role={r} size="md" onSelect={(id) => open("agent", id)} reducedMotion={reduced} />
                      <span className="co-active-name">{r.name}</span>
                      <span className="co-active-status" data-tone={statusMeta(r.status).tone}>{statusMeta(r.status).label}</span>
                    </div>
                  ))}
                  {active.length > 10 ? <span className="co-more">+{active.length - 10} more</span> : null}
                </div>
              ) : <p className="co-muted">No agent is working right now. Everyone else is idle, and that is the true state.</p>}
            </section>
            <section className="co-card co-outputs" aria-label="Recent missions and outputs">
              <h2>Recent missions &amp; outputs</h2>
              {snap.recent_outputs?.length ? (
                <ul className="co-output-list">
                  {snap.recent_outputs.map((o) => (
                    <li key={`${o.kind}-${o.id}`}>
                      <span className="co-tag">{o.kind === "org_mission" ? "Mission" : "Artifact"}</span>
                      {o.kind === "org_mission" ? (
                        <button type="button" className="co-link" onClick={() => open("mission", o.id)}>{o.title}</button>
                      ) : <span>{o.title}</span>}
                      <span className="co-muted co-small">{o.status?.replaceAll("_", " ")} · {formatAgo(o.at)}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="co-muted">No outputs yet.</p>}
            </section>
          </div>
        </main>
        <Rail snap={snap} systems={systems} onOpen={open} liveConnected={liveConnected} />
      </div>

      {target ? (
        <Inspector target={target} version={snap.generated_at} onClose={() => setTarget(null)} onOpen={open} nameOf={nameOf} />
      ) : null}
      <p className="co-footnote"><Icon name="shield" size={12} /> Execution authority for every agent: NONE. Financial actions remain gated by Portfolio Risk, Trading Guardian, owner approval and the Execution Gateway (paper-only).</p>
    </div>
  );
}
