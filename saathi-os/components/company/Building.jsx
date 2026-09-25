"use client";

// The cutaway headquarters: floors (top first) → offices → workers.
// Pure presentation over the indexed snapshot; no data fetching here.

import { useState } from "react";
import AgentWorker from "./AgentWorker";
import { officeSummary, statusMeta } from "@/lib/organization";

const ICONS = {
  scale: "M12 3v18M5 7h14M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0zM8 21h8",
  spark: "M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  coin: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.5 8h4a2 2 0 0 1 0 4h-4h4.5a2 2 0 0 1 0 4H9.5zM11 6.5v11",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
  pie: "M12 3v9h9A9 9 0 1 1 12 3zM15 3.5A9 9 0 0 1 20.5 9H15z",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  doc: "M7 3h7l5 5v13H7zM14 3v5h5",
  bars: "M4 20V10M10 20V4M16 20v-7M21 20H3",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  cpu: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4",
  code: "M8 8l-4 4 4 4M16 8l4 4-4 4",
  server: "M4 5h16v5H4zM4 14h16v5H4z",
  lock: "M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3",
  briefcase: "M4 8h16v11H4zM9 8V5h6v3",
  dollar: "M12 3v18M16 7h-6a2.5 2.5 0 0 0 0 5h4a2.5 2.5 0 0 1 0 5H8",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5",
  book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 21V5",
};

export function Icon({ name, size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={ICONS[name] || ICONS.doc} />
    </svg>
  );
}

function OfficeHeader({ office, onOpen }) {
  const s = officeSummary(office);
  const note = [
    s.busy ? `${s.busy} active` : null,
    s.attention ? `${s.attention} need attention` : null,
  ].filter(Boolean).join(", ");
  return (
    <button type="button" className="co-office-tag" onClick={() => onOpen(office.office_id)}
      aria-label={`${office.name} office, ${s.members} members${note ? `, ${note}` : ""}. Open office detail`}>
      <span className="co-office-icon"><Icon name={office.icon} /></span>
      <span className="co-office-name">{office.name}</span>
      {s.busy > 0 && <span className="co-office-count" aria-hidden="true">{s.busy}</span>}
      {s.attention > 0 && <span className="co-office-alert" aria-hidden="true">!</span>}
    </button>
  );
}

function OwnerOffice({ office, owner, desk, onOpen }) {
  const pending = [desk?.pending_platform_approvals, desk?.pending_agent_approvals];
  const known = pending.every((v) => v !== null && v !== undefined);
  const total = known ? pending.reduce((a, b) => a + b, 0) : null;
  return (
    <section className={`co-room hue-${office.accent} co-room-owner`} aria-label="Owner office">
      <div className="co-room-backdrop" aria-hidden="true" />
      <OfficeHeader office={{ ...office, roles: [] }} onOpen={onOpen} />
      <div className="co-owner">
        <div className="co-owner-avatar" data-role-id="owner" aria-hidden="true">{owner?.initials || "?"}</div>
        <div className="co-owner-plate">
          <strong>{owner?.name}</strong>
          <span>{owner?.title}</span>
        </div>
        <dl className="co-owner-facts">
          <div><dt>Approvals</dt><dd>{total === null ? "Unknown" : total}</dd></div>
          <div><dt>Decisions</dt><dd>{desk?.open_decisions ?? "Unknown"}</dd></div>
          <div><dt>Paper accts</dt><dd>{desk?.paper_accounts ?? "Unknown"}</dd></div>
        </dl>
      </div>
    </section>
  );
}

function CeoOffice({ office, selectedId, onSelect, onOpen, reducedMotion, missionIds }) {
  const saathi = office.roles[0];
  return (
    <section className={`co-room hue-${office.accent} co-room-ceo`} aria-label="CEO office">
      <div className="co-skyline" aria-hidden="true" />
      <OfficeHeader office={office} onOpen={onOpen} />
      <div className="co-ceo">
        {saathi && (
          <AgentWorker role={saathi} size="lg" selected={selectedId === saathi.role_id}
            onSelect={onSelect} reducedMotion={reducedMotion} inMission={missionIds.has(saathi.role_id)} />
        )}
        <p className="co-ceo-plate">Orchestrate · Delegate · Report</p>
      </div>
    </section>
  );
}

function Room({ office, selectedId, onSelect, onOpen, reducedMotion, missionIds, highlighted }) {
  const specialists = office.roles.filter((r) => r.tier !== "mandate");
  const mandates = office.roles.filter((r) => r.tier === "mandate");
  const grow = Math.max(2.2, specialists.length + mandates.length * 0.45);
  return (
    <section className={`co-room hue-${office.accent}${highlighted ? " is-highlighted" : ""}`}
      style={{ flexGrow: grow }} aria-label={`${office.name} office`}>
      <div className="co-room-backdrop" aria-hidden="true" />
      <OfficeHeader office={office} onOpen={onOpen} />
      <div className="co-desks" role="group" aria-label={`${office.name} agents`}>
        {specialists.map((r) => (
          <AgentWorker key={r.role_id} role={r} selected={selectedId === r.role_id} onSelect={onSelect}
            reducedMotion={reducedMotion} inMission={missionIds.has(r.role_id)} />
        ))}
      </div>
      {mandates.length > 0 && (
        <div className="co-mandates" role="group" aria-label={`${office.name} strategy mandates`}>
          {mandates.map((r) => (
            <AgentWorker key={r.role_id} role={r} size="sm" selected={selectedId === r.role_id}
              onSelect={onSelect} reducedMotion={reducedMotion} inMission={missionIds.has(r.role_id)} />
          ))}
        </div>
      )}
    </section>
  );
}

export default function Building({ index, owner, desk, selectedId, onSelectAgent, onOpenOffice,
  reducedMotion, missionIds, highlightOffices }) {
  const [collapsed, setCollapsed] = useState({});
  return (
    <div className="co-building" role="region" aria-label="AI company headquarters">
      {index.floors.map((floor) => {
        const isCollapsed = !!collapsed[floor.floor_id];
        const busy = floor.offices.reduce((n, o) => n + officeSummary(o).busy, 0);
        return (
          <div key={floor.floor_id} className={`co-floor${isCollapsed ? " is-collapsed" : ""}`}
            data-floor={floor.floor_id}>
            <div className="co-floor-label">
              <span className="co-floor-no">Floor {floor.number}</span>
              <span className="co-floor-name">{floor.name}</span>
              <span className="co-floor-tag">{floor.tagline}</span>
              <button type="button" className="co-floor-toggle"
                aria-expanded={!isCollapsed}
                aria-label={`${isCollapsed ? "Expand" : "Collapse"} floor ${floor.number}, ${floor.name}`}
                onClick={() => setCollapsed((c) => ({ ...c, [floor.floor_id]: !c[floor.floor_id] }))}>
                {isCollapsed ? "Expand" : "Collapse"}
                {busy > 0 ? <span className="co-floor-busy"> · {busy} active</span> : null}
              </button>
            </div>
            {isCollapsed ? (
              <div className="co-floor-collapsed">
                {floor.offices.map((o) => (
                  <button key={o.office_id} type="button" className="co-chip" onClick={() => onOpenOffice(o.office_id)}>
                    {o.name} · {o.roles.length}
                  </button>
                ))}
              </div>
            ) : (
              <div className="co-rooms">
                {floor.offices.map((o) => {
                  if (o.office_id === "owner") {
                    return <OwnerOffice key={o.office_id} office={o} owner={owner} desk={desk} onOpen={onOpenOffice} />;
                  }
                  if (o.office_id === "ceo") {
                    return <CeoOffice key={o.office_id} office={o} selectedId={selectedId} onSelect={onSelectAgent}
                      onOpen={onOpenOffice} reducedMotion={reducedMotion} missionIds={missionIds} />;
                  }
                  return <Room key={o.office_id} office={o} selectedId={selectedId} onSelect={onSelectAgent}
                    onOpen={onOpenOffice} reducedMotion={reducedMotion} missionIds={missionIds}
                    highlighted={highlightOffices.has(o.office_id)} />;
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Compact department → office → agent list for narrow screens. */
export function CompanyList({ index, onSelectAgent, onOpenOffice }) {
  return (
    <div className="co-list" role="region" aria-label="AI company departments">
      {index.floors.map((floor) => (
        <details key={floor.floor_id} className="co-list-floor" open={floor.number >= 6}>
          <summary><span>Floor {floor.number}</span> {floor.name}</summary>
          {floor.offices.map((o) => (
            <div key={o.office_id} className={`co-list-office hue-${o.accent}`}>
              <button type="button" className="co-list-office-name" onClick={() => onOpenOffice(o.office_id)}>
                <Icon name={o.icon} /> {o.name}
              </button>
              <ul>
                {o.roles.map((r) => {
                  const m = statusMeta(r.status);
                  return (
                    <li key={r.role_id}>
                      <button type="button" onClick={() => onSelectAgent(r.role_id)} data-tone={m.tone}>
                        <span className="co-list-glyph" aria-hidden="true">{m.glyph}</span>
                        <span className="co-list-name">{r.name}</span>
                        <span className="co-list-status">{m.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </details>
      ))}
    </div>
  );
}
