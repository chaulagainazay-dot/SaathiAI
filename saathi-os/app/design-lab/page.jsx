"use client";

/**
 * UI-NEXT-2.1 — Hybrid Command interactive prototype (read-only).
 * Isolated from production /command. No execution/approval mutation.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import "./design-lab.css";
import {
  MODES,
  VOICE_SESSION_STATES,
  mapUiIntent,
  yetiFromSystem,
  PROVENANCE,
} from "@/lib/design-lab/contracts";
import { loadCommandReadModel, formatFraction, formatMoney } from "@/lib/design-lab/read-adapter";

function Pill({ children, tone = "default" }) {
  const cls =
    tone === "ok"
      ? "dl-pill dl-pill-ok"
      : tone === "warn"
        ? "dl-pill dl-pill-warn"
        : tone === "crit"
          ? "dl-pill dl-pill-crit"
          : tone === "info"
            ? "dl-pill dl-pill-info"
            : "dl-pill";
  return <span className={cls}>{children}</span>;
}

function ProvenanceTag({ p }) {
  const tone = p === "REAL" ? "ok" : p === "DEMO" ? "warn" : p === "UNAVAILABLE" ? "crit" : "info";
  return <Pill tone={tone}>{p || "UNAVAILABLE"}</Pill>;
}

function Metric({ label, value, provenance }) {
  return (
    <div className="dl-metric">
      <label>{label}</label>
      <div className="val">{value ?? "—"}</div>
      {provenance ? (
        <div className="dl-prov" data-prov={provenance}>
          {provenance}
        </div>
      ) : null}
    </div>
  );
}

function BudgetBar({ item }) {
  const used = Number(item.used) || 0;
  const limit = Number(String(item.limit).replace(/[^0-9.]/g, "")) || 1;
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const fillCls = item.status === "OK" ? "ok" : "warn";
  return (
    <div className="dl-bar">
      <div className="dl-bar-label">
        <span>{item.name}</span>
        <span>
          {formatFraction(item.used)} / {formatFraction(item.limit)} · soft {formatFraction(item.soft_threshold)} · hard{" "}
          {formatFraction(item.hard_threshold)}
        </span>
      </div>
      <div className="dl-bar-track" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={item.name}>
        <div className={`dl-bar-fill ${fillCls}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="dl-bar-label">
        <span>status {item.status}</span>
        <span>remaining {item.remaining}</span>
      </div>
    </div>
  );
}

const SCENARIOS = [
  { id: "healthy", label: "Healthy" },
  { id: "risk_warning", label: "Risk warning" },
  { id: "recon_required", label: "Recon required" },
  { id: "voice_degraded", label: "Voice degraded" },
];

export default function DesignLabPage() {
  const [scenario, setScenario] = useState("healthy");
  const [model, setModel] = useState(null);
  const [mode, setMode] = useState("command");
  const [voice, setVoice] = useState("READY");
  const [focus, setFocus] = useState("saathi");
  const [context, setContext] = useState({ kind: null, id: null, label: "None" });
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [input, setInput] = useState("");
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("Read-only Hybrid Command prototype. Ask for risk, missions, approvals, or evidence.");
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadCommandReadModel({ scenario }).then((m) => {
      if (!cancelled) {
        setModel(m);
        setVoice(m.voice_session_state || "READY");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [scenario]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(!!mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  const portfolio = model?.portfolio;
  const risk = model?.risk;
  const reconBlocked = portfolio?.portfolio_status === "RECONCILIATION_REQUIRED";

  const yeti = useMemo(
    () => yetiFromSystem({ voice, attention: model?.attention, risk }),
    [voice, model, risk],
  );

  const setCtx = useCallback((kind, id, label) => {
    setContext({ kind, id, label });
    setFocus(kind === "agent" ? "agents" : kind === "position" || kind === "risk" ? "risk" : kind === "evidence" ? "evidence" : "attention");
  }, []);

  const onSubmit = useCallback(
    (e) => {
      e?.preventDefault?.();
      const text = input.trim();
      if (!text) return;
      // Partial would be non-executable; only final submit runs intent
      setTranscript(text);
      setVoice("THINKING");
      const intent = mapUiIntent(text);
      window.setTimeout(() => {
        if (intent.mode) setMode(intent.mode);
        if (intent.focus) setFocus(intent.focus);
        setVoice(intent.voice || "SPEAKING");
        setReply(intent.reply || "");
        setInput("");
        if (intent.type === "stop") setFocus("saathi");
      }, reducedMotion ? 0 : 220);
    },
    [input, reducedMotion],
  );

  const cycleVoice = () => {
    const i = VOICE_SESSION_STATES.indexOf(voice);
    setVoice(VOICE_SESSION_STATES[(i + 1) % VOICE_SESSION_STATES.length]);
  };

  if (!model) {
    return (
      <div className="dl-root">
        <p className="dl-banner">Loading Hybrid Command prototype…</p>
      </div>
    );
  }

  const showAgents = mode === "agents" || mode === "command";
  const showInvest = mode === "investments" || mode === "command";
  const showEvidence = mode === "evidence" || mode === "command";
  const agentDetail = (model.agents.nodes || []).find((n) => n.id === selectedAgent);
  const posDetail = (portfolio.positions || []).find((p) => p.symbol === selectedPosition);
  const evDetail = (model.evidence.events || []).find((e) => e.id === selectedEvidence);

  return (
    <div
      className={`dl-root ${reducedMotion ? "dl-reduced" : ""}`}
      data-testid="design-lab-root"
      data-scenario={scenario}
      data-mode={mode}
      data-recon={portfolio.portfolio_status}
    >
      <div className="dl-banner" role="status" data-testid="demo-banner">
        {model.banner} · global provenance: {model.global_provenance} · production /command unchanged
      </div>

      {reconBlocked ? (
        <div className="dl-recon-banner" role="alert" data-testid="recon-banner">
          RECONCILIATION REQUIRED — portfolio/risk confidence reduced · pending posts:{" "}
          {portfolio.reconciliation?.pending_ledger_posts ?? "—"}
        </div>
      ) : null}

      <header className="dl-top">
        <div className="dl-brand">SAATHIOS · Hybrid Command Lab</div>
        <div className="dl-pills" aria-label="System status strip">
          <Pill tone="info">{model.system.paper.value}</Pill>
          <Pill tone="crit">LIVE UNAVAILABLE</Pill>
          <Pill tone={model.system.trading_guardian.status === "HEALTHY" ? "ok" : "warn"}>
            TG {model.system.trading_guardian.value}
          </Pill>
          <Pill tone={reconBlocked ? "crit" : "ok"}>RECON {model.system.ledger_reconciliation.value}</Pill>
          <Pill tone={model.system.risk.status === "HEALTHY" ? "ok" : model.system.risk.status === "WARNING" ? "warn" : "crit"}>
            RISK {model.system.risk.value}
          </Pill>
          <Pill tone={model.system.voice.status === "HEALTHY" ? "info" : "warn"}>VOICE {voice}</Pill>
          <Pill>MODELS {model.system.models.value}</Pill>
          <Pill tone="ok">GW {model.system.gateway.value}</Pill>
        </div>
        <div className="dl-top-actions">
          <label className="dl-scenario">
            Scenario{" "}
            <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Fixture scenario">
              {SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <Link href="/command" className="dl-btn dl-btn-ghost">
            Production Command →
          </Link>
        </div>
      </header>

      <div className="dl-tabs" role="tablist" aria-label="Operating mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            className="dl-tab"
            aria-selected={mode === m.id}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <p className="dl-context" data-testid="context-focus">
        Focus: <strong>{context.label}</strong> · scope <strong>{mode}</strong> · Yeti <strong>{yeti}</strong>
        {reducedMotion ? " · reduced motion" : ""}
      </p>

      <div className="dl-grid dl-layout-c" data-testid="design-lab-grid">
        {/* ATTENTION */}
        <section className={`dl-panel dl-area-att ${focus === "attention" ? "dl-focus" : ""}`} aria-labelledby="dl-att-h">
          <h2 id="dl-att-h">
            Attention <ProvenanceTag p={model.attention.provenance} />
          </h2>
          <ul className="dl-list">
            {(model.attention.items || []).map((a) => (
              <li key={a.id} data-sev={a.severity === "critical" ? "high" : a.severity}>
                <button
                  type="button"
                  className="dl-linkish"
                  onClick={() => {
                    setCtx("attention", a.id, a.title);
                    if (a.kind.includes("risk")) setMode("investments");
                    if (a.kind.includes("mission") || a.kind.includes("agent")) setMode("agents");
                  }}
                >
                  <strong>{a.title}</strong>
                  <div className="dl-muted">
                    {a.kind} · urgency {a.urgency}
                  </div>
                </button>
              </li>
            ))}
            {!model.attention.items?.length ? <li className="dl-muted">No attention items</li> : null}
          </ul>
        </section>

        {/* SAATHI CORE */}
        <section className={`dl-panel dl-area-saathi ${focus === "saathi" ? "dl-focus" : ""}`} aria-labelledby="dl-saathi-h">
          <h2 id="dl-saathi-h">Saathi Core</h2>
          <div className="dl-saathi-core">
            <div
              className="dl-orb"
              data-state={voice}
              data-reduced={reducedMotion ? "1" : "0"}
              role="img"
              aria-label={`Voice session ${voice}`}
              data-testid="saathi-orb"
            />
            <div className="dl-yeti" data-testid="yeti-state">
              Mr. Yeti (2D) · {yeti}
            </div>
            <div className="dl-transcript" data-testid="transcript">
              {transcript ? `You: “${transcript}”` : "No transcript yet"}
            </div>
            <div className="dl-transcript dl-reply" data-testid="assistant-reply">
              Saathi: {reply}
            </div>
            <div className="dl-muted">Active mission: {model.mission.name}</div>
            <button type="button" className="dl-btn dl-btn-ghost" onClick={cycleVoice}>
              Cycle voice state
            </button>
          </div>
        </section>

        {/* SYSTEM / RISK */}
        <section className={`dl-panel dl-area-sys ${focus === "risk" ? "dl-focus" : ""}`} aria-labelledby="dl-sys-h">
          <h2 id="dl-sys-h">
            System / Risk <ProvenanceTag p={risk.provenance} />
          </h2>
          <div className="dl-pills" style={{ marginBottom: 8 }}>
            <Pill tone="info">PAPER RISK</Pill>
            <Pill tone="crit">LIVE UNAVAILABLE</Pill>
            <Pill tone={risk.risk_status === "HEALTHY" ? "ok" : risk.risk_status === "WARNING" ? "warn" : "crit"}>
              {risk.risk_status}
            </Pill>
          </div>
          <div className="dl-metric-grid">
            <Metric label="drawdown" value={formatFraction(risk.drawdown)} provenance={risk.provenance} />
            <Metric label="daily_pnl" value={formatMoney(risk.daily_pnl)} provenance={risk.provenance} />
            <Metric label="weekly_pnl" value={formatMoney(risk.weekly_pnl)} provenance={risk.provenance} />
            <Metric label="cash %" value={formatFraction(risk.cash_pct)} provenance={risk.provenance} />
            <Metric label="largest" value={formatFraction(risk.largest_position)} provenance={risk.provenance} />
            <Metric label="budget" value={risk.budget_version} provenance={risk.provenance} />
          </div>
          {(risk.risk_budget_consumed || []).map((b) => (
            <BudgetBar key={b.name} item={b} />
          ))}
          {risk.reason_codes?.length ? (
            <p className="dl-muted" style={{ marginTop: 8 }}>
              reason_codes: {risk.reason_codes.join(", ")}
            </p>
          ) : null}
        </section>

        {/* AGENTS */}
        {showAgents && (
          <section className={`dl-panel dl-area-agents ${focus === "agents" ? "dl-focus" : ""}`} aria-labelledby="dl-ag-h">
            <h2 id="dl-ag-h">
              Agents / Missions <ProvenanceTag p={model.agents.provenance} />
            </h2>
            <div className="dl-mission" aria-label="Mission stages">
              {(model.mission.stages || []).map((s) => (
                <span key={s.id} className={`dl-stage dl-stage-${s.status.toLowerCase()}`} title={s.status}>
                  {s.label}
                </span>
              ))}
            </div>
            <div className="dl-agent-graph" data-testid="agent-graph">
              {(model.agents.nodes || []).map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`dl-node ${selectedAgent === n.id ? "dl-node-sel" : ""}`}
                  data-status={n.status}
                  onClick={() => {
                    setSelectedAgent(n.id);
                    setCtx("agent", n.id, `${n.name} · ${n.status}`);
                  }}
                >
                  <span>{n.name}</span>
                  <span className="dl-mono">{n.status}</span>
                </button>
              ))}
            </div>
            {agentDetail ? (
              <div className="dl-detail" data-testid="agent-detail">
                <strong>{agentDetail.name}</strong>
                <div>role: {agentDetail.role}</div>
                <div>task: {agentDetail.task || "—"}</div>
                <div>inputs: {(agentDetail.inputs || []).join(", ") || "—"}</div>
                <div>outputs: {(agentDetail.outputs || []).join(", ") || "—"}</div>
                <div>deps: {(agentDetail.dependencies || []).join(" → ") || "—"}</div>
                <div>evidence: {(agentDetail.evidence || []).join(", ") || "UNAVAILABLE"}</div>
              </div>
            ) : null}
          </section>
        )}

        {/* INVESTMENTS */}
        {showInvest && (
          <section className={`dl-panel dl-area-invest ${focus === "risk" ? "dl-focus" : ""}`} aria-labelledby="dl-inv-h">
            <h2 id="dl-inv-h">
              Portfolio / Risk <ProvenanceTag p={portfolio.provenance} />
            </h2>
            <div className="dl-pills" style={{ marginBottom: 8 }}>
              <Pill tone="info">PAPER</Pill>
              <Pill tone="crit">LIVE UNAVAILABLE</Pill>
              <Pill tone={reconBlocked ? "crit" : "ok"}>{portfolio.portfolio_status}</Pill>
              <Pill>authority {portfolio.authority}</Pill>
            </div>
            <div className="dl-metric-grid">
              <Metric label="paper_nav" value={formatMoney(portfolio.paper_nav)} provenance={portfolio.provenance} />
              <Metric label="cash" value={formatMoney(portfolio.cash)} provenance={portfolio.provenance} />
              <Metric label="realized_pnl" value={formatMoney(portfolio.realized_pnl)} provenance={portfolio.provenance} />
              <Metric label="unrealized_pnl" value={formatMoney(portfolio.unrealized_pnl)} provenance={portfolio.provenance} />
              <Metric label="gross_exposure" value={formatMoney(portfolio.gross_exposure)} provenance={portfolio.provenance} />
              <Metric label="net_exposure" value={formatMoney(portfolio.net_exposure)} provenance={portfolio.provenance} />
            </div>
            <h3 className="dl-subh">Positions</h3>
            <div className="dl-pos-list">
              {(portfolio.positions || []).map((p) => (
                <button
                  key={p.symbol}
                  type="button"
                  className={`dl-pos ${selectedPosition === p.symbol ? "dl-pos-sel" : ""}`}
                  onClick={() => {
                    setSelectedPosition(p.symbol);
                    setCtx("position", p.symbol, `Position ${p.symbol}`);
                  }}
                >
                  <span className="dl-mono">{p.symbol}</span>
                  <span>{formatFraction(p.weight)}</span>
                  <span>{formatMoney(p.market_value)}</span>
                </button>
              ))}
            </div>
            {posDetail ? (
              <div className="dl-detail" data-testid="position-detail">
                <strong>{posDetail.symbol}</strong>
                <div>quantity: {posDetail.quantity}</div>
                <div>market_value: {formatMoney(posDetail.market_value)}</div>
                <div>cost_basis: {formatMoney(posDetail.cost_basis)}</div>
                <div>avg_cost: {posDetail.avg_cost}</div>
                <div>unrealized_pnl: {formatMoney(posDetail.unrealized_pnl)}</div>
                <div>weight: {formatFraction(posDetail.weight)}</div>
                <div>freshness: {posDetail.mark_stale ? "STALE" : "OK"} · mark {posDetail.mark?.source || "—"}</div>
                <div>risk contribution: UNAVAILABLE (not in contract)</div>
              </div>
            ) : null}
            <h3 className="dl-subh">Stress (deterministic)</h3>
            <div className="dl-stress">
              {(risk.stress || []).map((s) => (
                <div key={s.scenario.scenario_id} className="dl-stress-card">
                  <div className="dl-mono">{s.scenario.name}</div>
                  <div>NAV {formatMoney(s.projected_nav)}</div>
                  <div>loss {formatMoney(s.loss)}</div>
                  <div>status {s.status}</div>
                </div>
              ))}
            </div>
            <h3 className="dl-subh">Approvals (read-only)</h3>
            <ul className="dl-list">
              {(model.approvals.items || []).map((a) => (
                <li key={a.id}>
                  <strong>{a.requested_action}</strong>
                  <div className="dl-muted">
                    {a.requester} · {a.risk_summary} · {a.scope} · exp {a.expiry} · {a.status}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* EVIDENCE */}
        {showEvidence && (
          <section className={`dl-panel dl-area-evidence ${focus === "evidence" ? "dl-focus" : ""}`} aria-labelledby="dl-ev-h">
            <h2 id="dl-ev-h">
              Evidence timeline <ProvenanceTag p={model.evidence.provenance} />
            </h2>
            <div className="dl-timeline">
              {(model.evidence.events || []).map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  className={`dl-ev ${selectedEvidence === ev.id ? "dl-ev-sel" : ""}`}
                  onClick={() => {
                    setSelectedEvidence(ev.id);
                    setCtx("evidence", ev.id, `${ev.type} ${ev.id}`);
                  }}
                >
                  <div className="t">{ev.timestamp || "UNAVAILABLE"}</div>
                  <div className="stage">{ev.type}</div>
                  <div>{ev.status}</div>
                  <div className="t">{ev.id}</div>
                </button>
              ))}
            </div>
            {evDetail ? (
              <div className="dl-detail" data-testid="evidence-detail">
                <strong>{evDetail.type}</strong>
                <div>timestamp: {evDetail.timestamp || "UNAVAILABLE"}</div>
                <div>actor: {evDetail.actor || "UNAVAILABLE"}</div>
                <div>status: {evDetail.status}</div>
                <div>reason: {evDetail.reason}</div>
                <div>evidence ID: {evDetail.id}</div>
                <div>related: {(evDetail.related_ids || []).join(", ") || "—"}</div>
              </div>
            ) : null}
          </section>
        )}

        {/* COMPOSER */}
        <form className={`dl-panel dl-composer dl-area-composer ${focus === "composer" ? "dl-focus" : ""}`} onSubmit={onSubmit} aria-label="Ask Saathi">
          <span className="dl-scope">scope:{mode}</span>
          <input
            className="dl-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Final transcript only · e.g. show portfolio risk"
            aria-label="Command input"
            data-testid="design-lab-input"
          />
          <button type="button" className="dl-btn dl-btn-ghost" onClick={() => setVoice("LISTENING")}>
            Listen
          </button>
          <button type="submit" className="dl-btn">
            Ask
          </button>
        </form>
      </div>

      <footer className="dl-foot">
        Hybrid Command · UI-NEXT-2.1 · no Three.js · no ledger/risk mutation · voice cannot authorize finance · READY_WITH_LIMITATIONS
        path toward production
      </footer>
    </div>
  );
}
