"use client";

/**
 * UI-NEXT-2 — isolated Hybrid Command design lab.
 * Does NOT replace /command. DEMO metrics only.
 */

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import "./design-lab.css";
import {
  CONCEPTS,
  DEMO_BANNER,
  MODES,
  VOICE_STATES,
  demoAgents,
  demoAttention,
  demoEvidence,
  demoPortfolio,
  demoRisk,
  demoSystem,
  mapVoiceCommand,
} from "@/lib/design-lab-demo";

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

function Metric({ label, value }) {
  return (
    <div className="dl-metric">
      <label>{label}</label>
      <div className="val">{value}</div>
    </div>
  );
}

function BudgetBar({ item }) {
  const usedNum = parseFloat(String(item.used).replace("%", "")) || 0;
  const limitNum = parseFloat(String(item.limit).replace(/[^0-9.]/g, "")) || 100;
  const pct = Math.min(100, Math.round((usedNum / (limitNum || 1)) * 100));
  const fillCls = item.status === "WARNING" || item.status === "BREACHED" ? "warn" : "ok";
  return (
    <div className="dl-bar">
      <div className="dl-bar-label">
        <span>{item.name}</span>
        <span>
          {item.used} / {item.limit}
        </span>
      </div>
      <div className="dl-bar-track" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`dl-bar-fill ${fillCls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function DesignLabPage() {
  const [concept, setConcept] = useState("C");
  const [mode, setMode] = useState("command");
  const [voice, setVoice] = useState("READY");
  const [focus, setFocus] = useState("saathi");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState("Ask Saathi — DEMO navigation only.");
  const [transcript, setTranscript] = useState("");

  const layoutClass =
    concept === "A" ? "dl-layout-a" : concept === "B" ? "dl-layout-b" : "dl-layout-c";

  const onSubmit = useCallback(
    (e) => {
      e?.preventDefault?.();
      const text = input.trim();
      if (!text) return;
      setTranscript(text);
      setVoice("THINKING");
      const mapped = mapVoiceCommand(text);
      window.setTimeout(() => {
        if (mapped.mode) setMode(mapped.mode);
        if (mapped.focus) setFocus(mapped.focus);
        setVoice(mapped.voice || "SPEAKING");
        setReply(mapped.reply || "");
        setInput("");
      }, 280);
    },
    [input],
  );

  const cycleVoice = useCallback(() => {
    const i = VOICE_STATES.indexOf(voice);
    setVoice(VOICE_STATES[(i + 1) % VOICE_STATES.length]);
  }, [voice]);

  const showAgents = mode === "agents" || mode === "command";
  const showInvest = mode === "investments" || mode === "command";
  const showEvidence = mode === "evidence" || mode === "command";

  const yetiState = useMemo(() => {
    if (voice === "LISTENING") return "listening";
    if (voice === "THINKING" || voice === "TRANSCRIBING") return "thinking";
    if (voice === "SPEAKING") return "speaking";
    if (voice === "DEGRADED" || voice === "ERROR") return "degraded";
    if (demoAttention.some((a) => a.severity === "high")) return "approval waiting";
    return "idle";
  }, [voice]);

  return (
    <div className="dl-root" data-testid="design-lab-root">
      <div className="dl-banner" role="status">
        {DEMO_BANNER} · UI-NEXT-2 prototype · does not replace /command
      </div>

      <div className="dl-top">
        <div className="dl-brand">SAATHIOS · Design Lab</div>
        <div className="dl-pills" aria-label="Authority strip">
          <Pill tone="info">{demoSystem.paper}</Pill>
          <Pill tone="crit">LIVE {demoSystem.live}</Pill>
          <Pill tone="ok">TG {demoSystem.tg}</Pill>
          <Pill tone="ok">{demoSystem.health}</Pill>
          <Pill tone="info">VOICE {voice}</Pill>
          <Pill>Gateway {demoSystem.gateway}</Pill>
        </div>
        <Link href="/command" className="dl-btn dl-btn-ghost" style={{ textDecoration: "none", display: "inline-block" }}>
          Production Command →
        </Link>
      </div>

      <div className="dl-concepts" role="group" aria-label="Concept architecture">
        {CONCEPTS.map((c) => (
          <button
            key={c.id}
            type="button"
            className="dl-concept"
            aria-pressed={concept === c.id}
            onClick={() => setConcept(c.id)}
            title={c.blurb}
          >
            {c.label}
          </button>
        ))}
      </div>

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

      <div className={`dl-grid ${layoutClass}`} data-testid="design-lab-grid" data-concept={concept} data-mode={mode}>
        <section
          className={`dl-panel dl-area-att ${focus === "attention" ? "dl-focus" : ""}`}
          aria-labelledby="dl-att-h"
        >
          <h2 id="dl-att-h">Attention</h2>
          <ul className="dl-list">
            {demoAttention.map((a) => (
              <li key={a.id} data-sev={a.severity}>
                <strong>{a.title}</strong>
                <div style={{ color: "var(--dl-muted)", marginTop: 2 }}>{a.kind}</div>
              </li>
            ))}
          </ul>
        </section>

        <section
          className={`dl-panel dl-saathi dl-area-saathi ${focus === "saathi" ? "dl-focus" : ""}`}
          aria-labelledby="dl-saathi-h"
        >
          <h2 id="dl-saathi-h">Saathi core</h2>
          <div className="dl-saathi-core">
            <div
              className="dl-orb"
              data-state={voice}
              role="img"
              aria-label={`Saathi voice state ${voice}`}
              data-testid="saathi-orb"
            />
            <div className="dl-yeti">Mr. Yeti · 2D concept · state: {yetiState}</div>
            <div className="dl-transcript" data-testid="saathi-transcript">
              {transcript ? `“${transcript}”` : "Ready for voice or text (DEMO)."}
            </div>
            <div className="dl-transcript" style={{ color: "var(--dl-text)" }}>
              {reply}
            </div>
            <button type="button" className="dl-btn dl-btn-ghost" onClick={cycleVoice}>
              Cycle voice state
            </button>
          </div>
        </section>

        <section className={`dl-panel dl-area-sys ${focus === "risk" ? "dl-focus" : ""}`} aria-labelledby="dl-sys-h">
          <h2 id="dl-sys-h">System / Risk</h2>
          <div className="dl-metric-grid">
            <Metric label="TG" value={demoSystem.tg} />
            <Metric label="Risk" value={demoRisk.risk_status} />
            <Metric label="Gateway" value={demoSystem.gateway} />
            <Metric label="Models" value={demoSystem.models} />
            <Metric label="Recon" value={demoPortfolio.reconciliation} />
          </div>
          <div style={{ marginTop: 8 }}>
            {demoRisk.risk_budget_consumed.map((b) => (
              <BudgetBar key={b.name} item={b} />
            ))}
          </div>
          <p style={{ fontSize: 11, color: "var(--dl-muted)", marginTop: 8 }}>{demoRisk.label} · {demoRisk.budget_version}</p>
        </section>

        {showAgents && (
          <section
            className={`dl-panel dl-agents dl-area-agents ${focus === "agents" ? "dl-focus" : ""}`}
            aria-labelledby="dl-ag-h"
          >
            <h2 id="dl-ag-h">Agent / Mission topology</h2>
            <div className="dl-agent-graph" data-testid="agent-graph">
              {demoAgents.map((n) => (
                <div key={n.id} className="dl-node" data-status={n.status}>
                  <span>{n.label}</span>
                  <span style={{ color: "var(--dl-muted)", fontFamily: "ui-monospace, Menlo, monospace" }}>
                    {n.status}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {showInvest && (
          <section
            className={`dl-panel dl-area-invest ${focus === "risk" ? "dl-focus" : ""}`}
            aria-labelledby="dl-inv-h"
          >
            <h2 id="dl-inv-h">Portfolio / Risk · PAPER</h2>
            <div className="dl-pills" style={{ marginBottom: 8 }}>
              <Pill tone="info">PAPER</Pill>
              <Pill tone="crit">LIVE UNAVAILABLE</Pill>
              <Pill tone="ok">{demoPortfolio.portfolio_status}</Pill>
            </div>
            <div className="dl-metric-grid">
              <Metric label="paper_nav" value={demoPortfolio.paper_nav} />
              <Metric label="cash" value={demoPortfolio.cash} />
              <Metric label="realized_pnl" value={demoPortfolio.realized_pnl} />
              <Metric label="unrealized_pnl" value={demoPortfolio.unrealized_pnl} />
              <Metric label="daily_pnl" value={demoPortfolio.daily_pnl} />
              <Metric label="weekly_pnl" value={demoPortfolio.weekly_pnl} />
              <Metric label="drawdown" value={demoPortfolio.drawdown} />
              <Metric label="gross_exposure" value={demoPortfolio.gross_exposure} />
              <Metric label="net_exposure" value={demoPortfolio.net_exposure} />
              <Metric label="largest_position" value={demoPortfolio.largest_position} />
              <Metric label="stress_loss" value={demoRisk.stress_loss} />
            </div>
            <p style={{ fontSize: 11, color: "var(--dl-muted)", marginTop: 8 }}>
              Fields named for T-NEXT ledger/risk contracts · values DEMO
            </p>
          </section>
        )}

        {showEvidence && (
          <section
            className={`dl-panel dl-evidence dl-area-evidence ${focus === "evidence" ? "dl-focus" : ""}`}
            aria-labelledby="dl-ev-h"
          >
            <h2 id="dl-ev-h">Evidence timeline</h2>
            <div className="dl-timeline">
              {demoEvidence.map((ev) => (
                <div key={ev.id} className="dl-ev">
                  <div className="t">{ev.t}</div>
                  <div className="stage">{ev.stage}</div>
                  <div>{ev.detail}</div>
                  <div className="t">{ev.id}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        <form
          className={`dl-panel dl-composer dl-area-composer ${focus === "composer" ? "dl-focus" : ""}`}
          onSubmit={onSubmit}
          aria-label="Ask Saathi"
        >
          <span aria-hidden="true">🎙</span>
          <input
            className="dl-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Saathi… e.g. show portfolio risk"
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

      <p className="dl-foot">
        Concept {concept} · Mode {mode} · VoiceSession {voice} · Hybrid selected in FINAL_DESIGN_DECISION · no Three.js ·
        no production /command replacement
      </p>
    </div>
  );
}
