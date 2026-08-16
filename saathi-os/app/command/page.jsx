"use client";

/**
 * UI-NEXT-3.1 — Production Hybrid Command Center + V-NEXT canonical voice session.
 * Modes: Command · Agents · Investments · Evidence
 * Read-mostly · PAPER · zero execution / approval / TG override authority.
 * Voice is a consumer only: VoiceSessionManager owns mic/speaker, never authority.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import "./command-hybrid.css";
import { useHybridCommand } from "@/lib/useHybridCommand";
import {
  MODES,
  VOICE_SESSION_STATES,
  formatFraction,
  formatMoney,
  mapProductionUiIntent,
  yetiFromSystem,
  reasonCodeLabel,
} from "@/lib/command-read-model";
import {
  voicePresentation,
  riskMotionTone,
  proposalMotionTone,
  relatedEvidenceEvents,
} from "@/lib/command-motion";
import { LoadingState, ErrorState, EmptyState, StatusBadge, Button } from "@/components/ui";
import { useVoiceSession } from "@/components/voice/VoiceSessionProvider";

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
  const tone =
    p === "LIVE" || p === "REAL"
      ? "ok"
      : p === "FIXTURE" || p === "DEMO"
        ? "warn"
        : p === "UNAVAILABLE" || p === "ERROR"
          ? "crit"
          : "info";
  return <Pill tone={tone}>{p || "UNAVAILABLE"}</Pill>;
}

function Metric({ label, value, provenance }) {
  const display =
    value == null || value === ""
      ? provenance === "LOADING"
        ? "LOADING"
        : "UNAVAILABLE"
      : value;
  return (
    <div className="dl-metric">
      <label>{label}</label>
      <div className="val">{display}</div>
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
  const limitRaw = String(item.limit ?? item.hard_threshold ?? "1").replace(/[^0-9.]/g, "");
  const limit = Number(limitRaw) || 1;
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const st = String(item.status || "").toUpperCase();
  const fillCls =
    st === "OK" || st === "HEALTHY"
      ? "ok"
      : st === "BREACHED" || st === "BLOCK" || st === "CRITICAL"
        ? "crit"
        : "warn";
  return (
    <div className="dl-bar" data-status={item.status || ""}>
      <div className="dl-bar-label">
        <span>{item.name}</span>
        <span>
          {formatFraction(item.used)} / {formatFraction(item.limit)} · soft{" "}
          {formatFraction(item.soft_threshold)} · hard {formatFraction(item.hard_threshold)}
        </span>
      </div>
      <div
        className="dl-bar-track"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={item.name}
      >
        <div className={`dl-bar-fill ${fillCls}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="dl-bar-label">
        <span>status {item.status}</span>
        <span>remaining {item.remaining ?? "—"}</span>
      </div>
    </div>
  );
}

function PerformancePanel({ performance }) {
  const perf = performance?.paper_performance;
  if (!perf) {
    return (
      <div className="hc-perf" data-testid="performance-panel" data-state="empty">
        <h3 className="dl-subh">
          Performance <ProvenanceTag p={performance?.provenance || "UNAVAILABLE"} />
        </h3>
        <p className="dl-muted">{performance?.note || "Performance history UNAVAILABLE"}</p>
        <div className="hc-auth-label">Read-only · no frontend financial calculation</div>
      </div>
    );
  }
  const periods = perf.returns || perf.period_returns || [];
  const contrib = perf.position_contribution || perf.contributions || [];
  return (
    <div
      className="hc-perf"
      data-testid="performance-panel"
      data-period={perf.as_of || perf.period || "all"}
      aria-labelledby="hc-perf-h"
    >
      <h3 id="hc-perf-h" className="dl-subh">
        Performance <ProvenanceTag p={performance.provenance} />
      </h3>
      <div className="dl-pills" style={{ marginBottom: 8 }}>
        <Pill tone="info">PAPER</Pill>
        <Pill tone="crit">LIVE UNAVAILABLE</Pill>
        <Pill>T-NEXT-4 read</Pill>
      </div>
      <div className="dl-metric-grid" data-testid="performance-metrics">
        <Metric label="NAV" value={formatMoney(perf.nav ?? perf.current_nav)} provenance={performance.provenance} />
        <Metric
          label="return"
          value={formatFraction(perf.total_return ?? perf.return_pct ?? periods[0]?.return)}
          provenance={performance.provenance}
        />
        <Metric
          label="drawdown"
          value={formatFraction(perf.max_drawdown ?? perf.drawdown)}
          provenance={performance.provenance}
        />
        <Metric
          label="realized_pnl"
          value={formatMoney(perf.realized_pnl)}
          provenance={performance.provenance}
        />
        <Metric
          label="unrealized_pnl"
          value={formatMoney(perf.unrealized_pnl)}
          provenance={performance.provenance}
        />
      </div>
      {Array.isArray(perf.nav_history) && perf.nav_history.length ? (
        <p className="dl-muted" data-testid="nav-history-count">
          NAV history points: {perf.nav_history.length} · chart: tabular (no 3D)
        </p>
      ) : (
        <p className="dl-muted">NAV history UNAVAILABLE</p>
      )}
      {contrib.length ? (
        <div className="dl-pos-list" aria-label="Position contribution" data-testid="perf-contribution">
          {contrib.slice(0, 8).map((c, i) => (
            <div key={c.symbol || i} className="dl-pos" style={{ cursor: "default" }}>
              <span className="dl-mono">{c.symbol || "—"}</span>
              <span>{formatFraction(c.contribution ?? c.weight)}</span>
              <span>{formatMoney(c.pnl ?? c.unrealized_pnl)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="hc-auth-label">Pass-through only · inventsMetrics=false</div>
    </div>
  );
}

function ProposalPanel({
  proposal,
  focus,
  onFocus,
  showWhy,
  setShowWhy,
  selectedTrade,
  onSelectTrade,
}) {
  const pp = proposal?.portfolio_proposal;
  if (!pp) {
    return (
      <div className="hc-proposal" data-testid="proposal-empty">
        <div className="hc-auth-label">PROPOSAL · UNAVAILABLE</div>
        <p className="dl-muted">No active portfolio construction proposal. Not executed · not approved.</p>
        <ProvenanceTag p={proposal?.provenance || "UNAVAILABLE"} />
      </div>
    );
  }
  const status = pp.status || "DRAFT";
  const propTone = proposalMotionTone(status);
  const trades = (pp.trades || []).filter((t) => t.action === "BUY" || t.action === "SELL");
  const linked = !!selectedTrade;
  return (
    <div
      className={`hc-proposal ${focus === "proposal" ? "dl-focus" : ""}`}
      data-status={status}
      data-testid="proposal-panel"
      aria-labelledby="hc-prop-h"
    >
      <h3 id="hc-prop-h" className="dl-subh">
        Portfolio proposal <ProvenanceTag p={proposal.provenance} />
      </h3>
      <div className="dl-pills" style={{ marginBottom: 8 }}>
        <Pill tone="info">PROPOSAL</Pill>
        <Pill tone={propTone}>{status}</Pill>
        <Pill tone="crit">NOT EXECUTED</Pill>
        <Pill tone="crit">LIVE UNAVAILABLE</Pill>
        <Pill>PAPER</Pill>
      </div>
      <div className="dl-muted">
        {pp.id} · {pp.method || pp.source || "—"} · auth exec={String(!!pp.authorizes_execution)}
      </div>
      {(pp.current || pp.proposed) && (
        <div
          className={`hc-compare ${linked ? "hc-compare-sync" : ""}`}
          data-testid="proposal-compare"
          data-linked={linked ? "1" : "0"}
        >
          <div className={linked ? "hc-compare-side-linked" : undefined} data-side="current">
            <strong>CURRENT</strong>
            <div>cash {formatMoney(pp.current?.cash)}</div>
            <div>NAV {formatMoney(pp.current?.nav)}</div>
            <div>largest {formatFraction(pp.current?.largest_position)}</div>
            <div>risk {pp.current?.risk_status || "—"}</div>
            {selectedTrade ? (
              <div className="dl-mono" data-testid="compare-trade-current">
                {selectedTrade.symbol} {formatFraction(selectedTrade.current_weight)}
              </div>
            ) : null}
          </div>
          <div className="arrow" aria-hidden="true">
            →
          </div>
          <div className={linked ? "hc-compare-side-linked" : undefined} data-side="proposed">
            <strong>PROPOSED</strong>
            <div>cash {formatMoney(pp.proposed?.cash)}</div>
            <div>NAV {formatMoney(pp.proposed?.nav)}</div>
            <div>largest {formatFraction(pp.proposed?.largest_position)}</div>
            <div>risk {pp.proposed?.risk_status || "—"}</div>
            {selectedTrade ? (
              <div className="dl-mono" data-testid="compare-trade-proposed">
                {selectedTrade.symbol} {formatFraction(selectedTrade.target_weight)}
              </div>
            ) : null}
          </div>
        </div>
      )}
      {selectedTrade?.reason_codes?.length || selectedTrade ? (
        <div className="dl-muted" data-testid="compare-trade-meta">
          trade {selectedTrade?.action} {selectedTrade?.symbol}
          {selectedTrade?.reason_codes?.length
            ? ` · reason ${selectedTrade.reason_codes.join(", ")}`
            : ""}
          {pp.projected_risk?.risk_status
            ? ` · projected risk ${pp.projected_risk.risk_status}`
            : ""}
        </div>
      ) : null}
      {trades.length ? (
        <div className="dl-pos-list" aria-label="Proposed trades" data-testid="proposal-trades">
          {trades.map((t, i) => {
            const sel = selectedTrade?.symbol === t.symbol && selectedTrade?.action === t.action;
            return (
              <button
                key={`${t.symbol}-${i}`}
                type="button"
                className="dl-pos hc-trade-row"
                data-selected={sel ? "1" : "0"}
                data-testid={`trade-row-${t.symbol}`}
                aria-pressed={sel}
                onClick={() => {
                  onSelectTrade?.(sel ? null : t);
                  onFocus?.("proposal", pp.id, `Trade ${t.action} ${t.symbol}`);
                }}
              >
                <span className="dl-mono">
                  {t.action} {t.symbol}
                </span>
                <span>
                  {formatFraction(t.current_weight)} → {formatFraction(t.target_weight)}
                </span>
                <span>qty {t.estimated_quantity ?? "—"}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="dl-muted">No material BUY/SELL rows</p>
      )}
      <button
        type="button"
        className="dl-btn dl-btn-ghost"
        data-testid="proposal-why"
        onClick={() => {
          setShowWhy((v) => !v);
          onFocus?.("proposal", pp.id, `Proposal ${pp.id}`);
        }}
      >
        Why?
      </button>
      {showWhy ? (
        <div className="hc-why" data-testid="proposal-why-panel">
          <strong>Deterministic basis</strong>
          <ul className="dl-list">
            {(pp.reason_labels || (pp.reason_codes || []).map((c) => ({ code: c, label: reasonCodeLabel(c) }))).map(
              (r) => (
                <li key={r.code}>
                  <code>{r.code}</code> — {r.label}
                </li>
              ),
            )}
          </ul>
          {pp.warnings?.length ? <div className="dl-muted">warnings: {pp.warnings.join(", ")}</div> : null}
          {pp.evidence_refs && Object.keys(pp.evidence_refs).length ? (
            <div className="dl-muted">evidence: {JSON.stringify(pp.evidence_refs)}</div>
          ) : (
            <div className="dl-muted">evidence refs: UNAVAILABLE</div>
          )}
          <div className="hc-auth-label">READY_FOR_APPROVAL ≠ EXECUTED · construction has zero execution authority</div>
        </div>
      ) : null}
    </div>
  );
}

export default function CommandCenterPage() {
  const [fixtureScenario, setFixtureScenario] = useState(null);
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      setFixtureScenario(q.get("fixture"));
    } catch {
      setFixtureScenario(null);
    }
  }, []);

  const { loading, model, refresh } = useHybridCommand({ fixtureScenario });
  const voiceSession = useVoiceSession();

  const [mode, setMode] = useState("command");
  const [modeEnter, setModeEnter] = useState(false);
  // Presentation-only voice override. The canonical owner is VoiceSessionManager
  // (V-NEXT-1) published through VoiceSessionProvider; this holds the local
  // read-model / demo-intent label used when no real session owns the mic.
  const [voiceOverride, setVoiceOverride] = useState("READY");
  const [focus, setFocus] = useState("saathi");
  const [context, setContext] = useState({ kind: null, id: null, label: "None" });
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [input, setInput] = useState("");
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState(
    "Ask about portfolio, risk, proposal, agents, or evidence. I cannot authorize trades.",
  );
  const [reducedMotion, setReducedMotion] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [riskFlash, setRiskFlash] = useState(false);
  const prevRiskRef = useRef(null);

  useEffect(() => {
    if (model?.saathi?.voice_session_state) setVoiceOverride(model.saathi.voice_session_state);
  }, [model?.saathi?.voice_session_state]);

  // V-NEXT-1 single-owner rule: when a real VoiceSession holds the mic/speaker,
  // its state wins over any local presentation label. IDLE/CLOSED means the
  // manager owns nothing, so the local read-model label is shown instead.
  const canonicalVoiceState = voiceSession?.session?.state;
  const canonicalVoiceOwns =
    !!canonicalVoiceState && canonicalVoiceState !== "IDLE" && canonicalVoiceState !== "CLOSED";
  const voice = canonicalVoiceOwns ? canonicalVoiceState : voiceOverride;

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      const on = !!mq.matches;
      setReducedMotion(on);
      document.documentElement.classList.toggle("dl-reduced-root", on);
    };
    apply();
    mq.addEventListener?.("change", apply);
    return () => {
      mq.removeEventListener?.("change", apply);
      document.documentElement.classList.remove("dl-reduced-root");
    };
  }, []);

  const portfolio = model?.portfolio;
  const risk = model?.risk;
  const proposal = model?.proposal;
  const performance = model?.performance;
  const system = model?.system;
  const reconBlocked =
    portfolio?.portfolio_status === "RECONCILIATION_REQUIRED" ||
    portfolio?.reconciliation?.portfolio_status === "RECONCILIATION_REQUIRED";
  const riskStatus = risk?.risk_status || (reconBlocked ? "RECONCILIATION_REQUIRED" : "UNAVAILABLE");
  const voiceMeta = useMemo(() => voicePresentation(voice), [voice]);

  // Risk transition flash — only on meaningful status change; never permanent pulse
  useEffect(() => {
    const next = riskStatus;
    const prev = prevRiskRef.current;
    prevRiskRef.current = next;
    if (prev == null || prev === next || reducedMotion) return;
    if (["WARNING", "BREACHED", "RECONCILIATION_REQUIRED", "DATA_INSUFFICIENT", "HEALTHY"].includes(next)) {
      setRiskFlash(true);
      const t = window.setTimeout(() => setRiskFlash(false), 280);
      return () => window.clearTimeout(t);
    }
  }, [riskStatus, reducedMotion]);

  const changeMode = useCallback(
    (next) => {
      if (next === mode) return;
      setMode(next);
      if (reducedMotion) {
        setModeEnter(false);
        return;
      }
      setModeEnter(true);
      window.setTimeout(() => setModeEnter(false), 200);
    },
    [mode, reducedMotion],
  );

  const yeti = useMemo(
    () => yetiFromSystem({ voice, attention: model?.attention, risk }),
    [voice, model, risk],
  );

  const setCtx = useCallback((kind, id, label) => {
    setContext({ kind, id, label });
    setFocus(
      kind === "agent"
        ? "agents"
        : kind === "position" || kind === "risk"
          ? "risk"
          : kind === "evidence"
            ? "evidence"
            : kind === "proposal"
              ? "proposal"
              : "attention",
    );
  }, []);

  const onSubmit = useCallback(
    (e) => {
      e?.preventDefault?.();
      const text = input.trim();
      if (!text) return;
      setTranscript(text);
      setVoiceOverride("THINKING");
      const intent = mapProductionUiIntent(text);
      window.setTimeout(() => {
        if (intent.mode) changeMode(intent.mode);
        if (intent.focus) setFocus(intent.focus);
        setVoiceOverride(intent.voice || "SPEAKING");
        setReply(intent.reply || "");
        setInput("");
        if (intent.type === "stop") setFocus("saathi");
      }, reducedMotion ? 0 : 180);
    },
    [input, reducedMotion, changeMode],
  );

  const relatedEvidenceIds = useMemo(() => {
    const events = model?.evidence?.events || [];
    const sel = {
      kind: context.kind,
      id:
        context.id ||
        selectedTrade?.symbol ||
        model?.proposal?.portfolio_proposal?.id ||
        selectedAgent ||
        selectedPosition,
      relatedIds: [
        selectedTrade?.symbol,
        model?.proposal?.portfolio_proposal?.id,
        selectedAgent,
        selectedPosition,
        ...(selectedTrade?.reason_codes || []),
      ].filter(Boolean),
    };
    return new Set(relatedEvidenceEvents(events, sel).map((e) => e.id));
  }, [
    context.kind,
    context.id,
    selectedTrade,
    model?.proposal?.portfolio_proposal?.id,
    selectedAgent,
    selectedPosition,
    model?.evidence?.events,
  ]);

  if (loading && !model) {
    return (
      <div className="dl-root hc-root" data-testid="command-loading" aria-busy="true">
        <LoadingState label="LOADING · Hybrid Command…" />
      </div>
    );
  }

  if (!model) {
    return (
      <div className="dl-root hc-root" data-testid="command-error">
        <ErrorState
          title="Command composition unavailable"
          description="Hybrid Command could not compose a read model."
          action={
            <Link href="/" className="dl-btn dl-btn-ghost">
              Home
            </Link>
          }
        />
      </div>
    );
  }

  const showAgents = mode === "agents" || mode === "command";
  const showInvest = mode === "investments" || mode === "command";
  const showEvidence = mode === "evidence" || mode === "command";
  const agentNodes = model.agents?.nodes || [];
  const agentDetail = agentNodes.find((n) => n.id === selectedAgent);
  const posDetail = (portfolio?.positions || []).find((p) => p.symbol === selectedPosition);
  const evDetail = (model.evidence?.events || []).find((e) => e.id === selectedEvidence);
  const missions = model.missions?.items || [];
  const contextLabel =
    context.label !== "None"
      ? context.label
      : proposal?.portfolio_proposal
        ? `Proposal ${proposal.portfolio_proposal.id}`
        : "Command";

  return (
    <div
      className={`dl-root hc-root ${reducedMotion ? "dl-reduced" : ""}`}
      data-testid="hybrid-command-root"
      data-mode={mode}
      data-mode-enter={modeEnter ? "1" : "0"}
      data-voice={voice}
      data-risk={riskStatus}
      data-recon={portfolio?.portfolio_status}
      data-fixture={fixtureScenario || ""}
      data-motion="ui-next-3.1"
    >
      <div className="dl-banner" role="status" data-testid="command-banner">
        {model.banner} · provenance {model.global_provenance}
      </div>

      {reconBlocked ? (
        <div className="dl-recon-banner" role="alert" data-testid="recon-banner">
          RECONCILIATION REQUIRED — portfolio/risk confidence reduced · pending posts:{" "}
          {portfolio?.reconciliation?.pending_ledger_posts ?? "—"}
        </div>
      ) : null}

      <header className="dl-top">
        <div className="dl-brand">SAATHIOS · Hybrid Command</div>
        <div className="dl-pills" aria-label="System status strip" data-testid="system-strip">
          <Pill tone="info">{system?.paper?.value || "PAPER"}</Pill>
          <Pill tone="crit">LIVE UNAVAILABLE</Pill>
          <Pill tone={system?.trading_guardian?.status === "HEALTHY" ? "ok" : "warn"}>
            TG {system?.trading_guardian?.value || "—"}
          </Pill>
          <Pill tone={reconBlocked ? "crit" : "ok"}>RECON {system?.recon?.value || "—"}</Pill>
          <Pill
            tone={
              system?.risk?.status === "HEALTHY" ? "ok" : system?.risk?.status === "WARNING" ? "warn" : "crit"
            }
          >
            RISK {system?.risk?.value || "—"}
          </Pill>
          <Pill tone={system?.voice?.status === "HEALTHY" ? "info" : "warn"}>VOICE {voice}</Pill>
          <Pill>MODELS {system?.models?.value || "—"}</Pill>
          <Pill tone="ok">GW {system?.gateway?.value || "EG"}</Pill>
        </div>
        <div className="dl-top-actions">
          <StatusBadge status="info" label={`VOICE ${voice}`} />
          <Button type="button" variant="ghost" className="dl-btn dl-btn-ghost" onClick={() => refresh?.()}>
            Refresh
          </Button>
          <Link href="/design-lab" className="dl-btn dl-btn-ghost">
            Design lab
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
            data-testid={`mode-${m.id}`}
            onClick={() => changeMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <p className="dl-context" data-testid="context-focus">
        Focus: <strong>{contextLabel}</strong> · mode <strong>{mode}</strong> · Yeti <strong>{yeti}</strong>
        {reducedMotion ? " · reduced motion" : ""}
      </p>

      <div className="dl-grid dl-layout-c" data-testid="hybrid-command-grid">
        <section
          className={`dl-panel dl-area-att ${focus === "attention" ? "dl-focus" : ""}`}
          aria-labelledby="hc-att-h"
        >
          <h2 id="hc-att-h">
            Attention <ProvenanceTag p={model.attention?.provenance} />
          </h2>
          <ul className="dl-list" data-testid="attention-list">
            {(model.attention?.items || []).map((a) => (
              <li key={a.id} data-sev={a.rank === "CRITICAL" ? "high" : a.severity || a.rank}>
                <button
                  type="button"
                  className="dl-linkish"
                  onClick={() => {
                    setCtx("attention", a.id, a.title);
                    if (a.focus === "proposal" || a.kind?.includes("proposal")) {
                      setMode("investments");
                      setFocus("proposal");
                    } else if (a.focus === "risk" || a.kind?.includes("risk")) setMode("investments");
                    else if (a.focus === "agents" || a.kind?.includes("agent") || a.kind?.includes("mission"))
                      setMode("agents");
                  }}
                >
                  <strong>{a.title}</strong>
                  <div className="dl-muted">
                    {a.rank || a.severity} · {a.kind}
                  </div>
                </button>
              </li>
            ))}
            {!model.attention?.items?.length ? (
              <li className="dl-empty" data-testid="attention-empty">
                <EmptyState title="No attention items" description="System quiet" />
              </li>
            ) : null}
          </ul>
        </section>

        <section
          className={`dl-panel dl-area-saathi ${focus === "saathi" ? "dl-focus" : ""}`}
          aria-labelledby="hc-saathi-h"
        >
          <h2 id="hc-saathi-h">Saathi Core</h2>
          <div className="dl-saathi-core">
            <div
              className="dl-orb"
              data-state={voice}
              data-reduced={reducedMotion ? "1" : "0"}
              data-loop={voiceMeta.loop && !reducedMotion ? "1" : "0"}
              role="img"
              aria-label={`Voice session ${voiceMeta.label}`}
              data-testid="saathi-orb"
            />
            <div
              className="hc-voice-badge"
              data-state={voice}
              data-testid="voice-state-badge"
              aria-live="polite"
            >
              {voiceMeta.label.toUpperCase()}
            </div>
            <div className="dl-yeti" data-testid="yeti-state">
              Mr. Yeti · {yeti}
            </div>
            <div className="dl-transcript" data-testid="transcript">
              {transcript || model.saathi?.transcript
                ? `You: “${transcript || model.saathi.transcript}”`
                : "No transcript yet"}
            </div>
            <div className="dl-transcript dl-reply" data-testid="assistant-reply">
              Saathi: {reply || model.saathi?.reply || "—"}
            </div>
            <div className="dl-muted">
              Focus entity: {contextLabel}
              {missions[0] ? ` · mission ${missions[0].name}` : ""}
            </div>
            <div className="hc-auth-label">Voice consumer only · no financial authorization</div>
            <button
              type="button"
              className="dl-btn dl-btn-ghost"
              data-testid="cycle-voice"
              onClick={() => {
                const i = VOICE_SESSION_STATES.indexOf(voice);
                setVoiceOverride(VOICE_SESSION_STATES[(i + 1) % VOICE_SESSION_STATES.length]);
              }}
            >
              Cycle voice state (test)
            </button>
          </div>
        </section>

        <section
          className={`dl-panel dl-area-sys ${focus === "risk" ? "dl-focus" : ""} ${riskFlash ? "hc-risk-flash" : ""}`}
          data-risk-status={riskStatus}
          data-testid="risk-panel"
          aria-labelledby="hc-sys-h"
        >
          <h2 id="hc-sys-h">
            System / Risk <ProvenanceTag p={risk?.provenance} />
          </h2>
          <div className="dl-pills" style={{ marginBottom: 8 }}>
            <Pill tone="info">PAPER RISK</Pill>
            <Pill tone="crit">LIVE UNAVAILABLE</Pill>
            <Pill tone={riskMotionTone(riskStatus)}>
              {risk?.risk_status || riskStatus || "UNAVAILABLE"}
            </Pill>
          </div>
          <div className="dl-metric-grid">
            <Metric label="drawdown" value={formatFraction(risk?.drawdown)} provenance={risk?.provenance} />
            <Metric label="daily_pnl" value={formatMoney(risk?.daily_pnl)} provenance={risk?.provenance} />
            <Metric label="weekly_pnl" value={formatMoney(risk?.weekly_pnl)} provenance={risk?.provenance} />
            <Metric label="cash %" value={formatFraction(risk?.cash_pct)} provenance={risk?.provenance} />
            <Metric
              label="largest"
              value={formatFraction(risk?.largest_position)}
              provenance={risk?.provenance}
            />
            <Metric label="budget" value={risk?.budget_version} provenance={risk?.provenance} />
          </div>
          {(risk?.risk_budget_consumed || []).map((b) => (
            <BudgetBar key={b.name} item={b} />
          ))}
          {risk?.reason_codes?.length ? (
            <p className="dl-muted" style={{ marginTop: 8 }}>
              reason_codes: {risk.reason_codes.join(", ")}
            </p>
          ) : null}
        </section>

        {showAgents && (
          <section
            className={`dl-panel dl-area-agents hc-mode-panel ${focus === "agents" ? "dl-focus" : ""}`}
            aria-labelledby="hc-ag-h"
            data-testid="agents-panel"
          >
            <h2 id="hc-ag-h">
              Agents / Missions <ProvenanceTag p={model.agents?.provenance} />
            </h2>
            {missions.length ? (
              <div className="dl-mission" aria-label="Missions" data-testid="mission-stages">
                {missions.map((m) => (
                  <span
                    key={m.id}
                    className="dl-stage"
                    data-status={m.status || m.stage || "ACTIVE"}
                    title={m.status}
                  >
                    {m.name}: {m.stage || m.status}
                  </span>
                ))}
              </div>
            ) : (
              <p className="dl-empty">No mission membership graph · list empty</p>
            )}
            <div className="dl-agent-graph" data-testid="agent-graph">
              {agentNodes.length === 0 ? (
                <p className="dl-empty" data-testid="agents-empty">
                  No agents · UNAVAILABLE
                </p>
              ) : null}
              {agentNodes.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`dl-node ${selectedAgent === n.id ? "dl-node-sel" : ""}`}
                  data-status={n.status}
                  data-testid={`agent-node-${n.id}`}
                  aria-label={`Agent ${n.name} status ${n.status}`}
                  onClick={() => {
                    setSelectedAgent(n.id);
                    setCtx("agent", n.id, `${n.name} · ${n.status}`);
                  }}
                >
                  <span>{n.name}</span>
                  <span className="dl-mono" aria-hidden="true">
                    {n.status}
                  </span>
                </button>
              ))}
            </div>
            {agentDetail ? (
              <div className="dl-detail" data-testid="agent-detail">
                <strong>{agentDetail.name}</strong>
                <div>role: {agentDetail.role || "—"}</div>
                <div>task: {agentDetail.task || "—"}</div>
                <div>mission: {agentDetail.mission || "—"}</div>
                <div>deps: {(agentDetail.dependencies || []).join(" → ") || "UNAVAILABLE"}</div>
                <div>
                  evidence:{" "}
                  {Array.isArray(agentDetail.evidence) && agentDetail.evidence.length
                    ? agentDetail.evidence.join(", ")
                    : "UNAVAILABLE"}
                </div>
              </div>
            ) : null}
          </section>
        )}

        {showInvest && (
          <section
            className={`dl-panel dl-area-invest hc-mode-panel ${focus === "risk" || focus === "proposal" ? "dl-focus" : ""}`}
            aria-labelledby="hc-inv-h"
            data-testid="investments-panel"
          >
            <h2 id="hc-inv-h">
              Investments <ProvenanceTag p={portfolio?.provenance} />
            </h2>
            <div className="dl-pills" style={{ marginBottom: 8 }}>
              <Pill tone="info">PAPER</Pill>
              <Pill tone="crit">LIVE UNAVAILABLE</Pill>
              <Pill tone={reconBlocked ? "crit" : "ok"}>{portfolio?.portfolio_status || "UNAVAILABLE"}</Pill>
              <Pill>authority {portfolio?.authority || "—"}</Pill>
            </div>
            <div className="dl-metric-grid" data-testid="portfolio-metrics">
              <Metric
                label="paper_nav"
                value={formatMoney(portfolio?.paper_nav)}
                provenance={portfolio?.provenance}
              />
              <Metric label="cash" value={formatMoney(portfolio?.cash)} provenance={portfolio?.provenance} />
              <Metric
                label="realized_pnl"
                value={formatMoney(portfolio?.realized_pnl)}
                provenance={portfolio?.provenance}
              />
              <Metric
                label="unrealized_pnl"
                value={formatMoney(portfolio?.unrealized_pnl)}
                provenance={portfolio?.provenance}
              />
              <Metric
                label="gross_exposure"
                value={formatMoney(portfolio?.gross_exposure)}
                provenance={portfolio?.provenance}
              />
              <Metric
                label="net_exposure"
                value={formatMoney(portfolio?.net_exposure)}
                provenance={portfolio?.provenance}
              />
            </div>

            <ProposalPanel
              proposal={proposal}
              focus={focus}
              onFocus={setCtx}
              showWhy={showWhy}
              setShowWhy={setShowWhy}
              selectedTrade={selectedTrade}
              onSelectTrade={(t) => {
                setSelectedTrade(t);
                if (t?.symbol) setSelectedPosition(t.symbol);
              }}
            />

            <PerformancePanel performance={performance} />

            <h3 className="dl-subh">Positions</h3>
            {portfolio?.error ? (
              <p className="dl-empty" data-testid="portfolio-error">
                Portfolio read failed · {portfolio.error}
              </p>
            ) : null}
            <div className="dl-pos-list">
              {(portfolio?.positions || []).length === 0 && !portfolio?.error ? (
                <p className="dl-empty" data-testid="positions-empty">
                  No open positions · cash-only or UNAVAILABLE
                </p>
              ) : null}
              {(portfolio?.positions || []).map((p) => (
                <button
                  key={p.symbol || p.security_id}
                  type="button"
                  className={`dl-pos ${selectedPosition === p.symbol ? "dl-pos-sel" : ""}`}
                  data-linked={selectedTrade?.symbol === p.symbol ? "1" : "0"}
                  aria-label={`Position ${p.symbol} weight ${p.weight}`}
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
                <div>quantity: {posDetail.quantity ?? "—"}</div>
                <div>market_value: {formatMoney(posDetail.market_value)}</div>
                <div>cost_basis: {formatMoney(posDetail.cost_basis)}</div>
                <div>avg_cost: {posDetail.avg_cost ?? "—"}</div>
                <div>unrealized_pnl: {formatMoney(posDetail.unrealized_pnl)}</div>
                <div>realized_pnl: {formatMoney(posDetail.realized_pnl)}</div>
                <div>weight: {formatFraction(posDetail.weight)}</div>
                <div>
                  freshness: {posDetail.mark_stale ? "STALE" : "OK"} · mark {posDetail.mark?.source || "—"}
                </div>
                <div>risk contribution: UNAVAILABLE</div>
              </div>
            ) : null}

            <h3 className="dl-subh">Stress</h3>
            <div className="dl-stress">
              {(risk?.stress || []).length === 0 ? (
                <p className="dl-empty">Stress scenarios UNAVAILABLE</p>
              ) : (
                (risk.stress || []).map((s, i) => (
                  <div key={s.scenario?.scenario_id || i} className="dl-stress-card">
                    <div className="dl-mono">{s.scenario?.name || s.name || "scenario"}</div>
                    <div>NAV {formatMoney(s.projected_nav)}</div>
                    <div>loss {formatMoney(s.loss)}</div>
                    <div>status {s.status || "—"}</div>
                  </div>
                ))
              )}
            </div>

            <h3 className="dl-subh">Approvals (read-only)</h3>
            <ul className="dl-list">
              {(model.approvals?.items || []).length === 0 ? (
                <li className="dl-empty">No pending approvals · UNAVAILABLE or empty</li>
              ) : (
                (model.approvals.items || []).map((a) => (
                  <li key={a.id || a.approval_id}>
                    <strong>{a.requested_action || a.title || a.action || "Approval"}</strong>
                    <div className="dl-muted">
                      {a.requester || "—"} · {a.status || a.state} · PAPER scope
                    </div>
                  </li>
                ))
              )}
            </ul>
          </section>
        )}

        {showEvidence && (
          <section
            className={`dl-panel dl-area-evidence hc-mode-panel ${focus === "evidence" ? "dl-focus" : ""}`}
            aria-labelledby="hc-ev-h"
            data-testid="evidence-panel"
          >
            <h2 id="hc-ev-h">
              Evidence <ProvenanceTag p={model.evidence?.provenance} />
            </h2>
            <div className="hc-chain" data-testid="causal-chain" role="group" aria-label="Causal chain">
              {(model.evidence?.causal_chain || []).map((c) => (
                <span key={c.type} data-ok={c.provenance === "LIVE" || c.provenance === "DERIVED" ? "1" : "0"}>
                  {c.type}:{c.status}
                </span>
              ))}
            </div>
            <div className="dl-timeline" data-testid="evidence-timeline">
              {(model.evidence?.events || []).length === 0 ? (
                <p className="dl-empty">No evidence events · UNAVAILABLE</p>
              ) : (
                (model.evidence.events || []).map((ev) => (
                  <button
                    key={ev.id}
                    type="button"
                    className={`dl-ev ${selectedEvidence === ev.id ? "dl-ev-sel" : ""}`}
                    data-related={relatedEvidenceIds.has(ev.id) ? "1" : "0"}
                    data-testid={`evidence-ev-${ev.id}`}
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
                ))
              )}
            </div>
            {evDetail ? (
              <div className="dl-detail" data-testid="evidence-detail">
                <strong>{evDetail.type}</strong>
                <div>timestamp: {evDetail.timestamp || "UNAVAILABLE"}</div>
                <div>actor: {evDetail.actor || "UNAVAILABLE"}</div>
                <div>status: {evDetail.status}</div>
                <div>reason: {evDetail.reason || "—"}</div>
                <div>evidence ID: {evDetail.id}</div>
                <div>related: {(evDetail.related_ids || []).join(", ") || "—"}</div>
              </div>
            ) : null}
          </section>
        )}

        <form
          className={`dl-panel dl-composer dl-area-composer ${focus === "composer" ? "dl-focus" : ""}`}
          onSubmit={onSubmit}
          aria-label="Ask Saathi"
        >
          <span className="dl-scope">
            scope:{mode}
            {context.kind ? ` · ask about ${context.label}` : ""}
          </span>
          <input
            className="dl-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. show the proposal · show risk · what needs approval"
            aria-label="Command input"
            data-testid="command-input"
          />
          <button
            type="button"
            className="dl-btn dl-btn-ghost"
            data-testid="listen-btn"
            onClick={() => {
              setVoiceOverride("LISTENING");
              voiceSession?.beginInput?.({ reason: "COMMAND_LISTEN" });
            }}
          >
            Listen
          </button>
          <button type="submit" className="dl-btn">
            Ask
          </button>
        </form>
      </div>

      <nav className="hc-bottom-nav" role="tablist" aria-label="Mobile modes" data-testid="mobile-nav">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            onClick={() => changeMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </nav>

      <footer className="dl-foot">
        UI-NEXT-3.1 Production Motion · inventsMetrics=
        {String(model.meta?.inventsMetrics)} · liveTrading={String(model.meta?.liveTrading)} · exec=
        {String(model.meta?.authorizesExecution)} · gsap=DEFERRED · lottie=DEFERRED · three=DEFERRED ·{" "}
        <Link href="/missions">Missions</Link> · <Link href="/approvals">Approvals</Link> ·{" "}
        <Link href="/trading">Trading</Link> · <Link href="/evidence">Evidence</Link> ·{" "}
        <Link href="/settings/voice">Voice</Link>
      </footer>
    </div>
  );
}
