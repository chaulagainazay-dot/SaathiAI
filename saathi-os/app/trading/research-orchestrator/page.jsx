"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M287 — Autonomous Research Orchestrator Control Center.
 *  RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO ORDERS. NO LIVE TRADING.
 */
export default function ResearchOrchestratorPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [jobs, setJobs] = useState(null);
  const [workers, setWorkers] = useState(null);
  const [budget, setBudget] = useState(null);
  const [templates, setTemplates] = useState(null);
  const [notebook, setNotebook] = useState(null);
  const [failures, setFailures] = useState(null);
  const [hypotheses, setHypotheses] = useState(null);
  const [calendar, setCalendar] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET", body = undefined) => {
    if (!d.token) return;
    setError(null);
    try {
      const opts = { token: d.token, method };
      if (body !== undefined) opts.body = body;
      setter(await plat(path, opts));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const afterBootstrap = async () => {
    if (!d.token) return;
    setError(null);
    try {
      const boot = await plat("/tg/research-orchestrator/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      setJobs(await plat("/tg/research-orchestrator/jobs", { token: d.token }));
      setWorkers(await plat("/tg/research-orchestrator/workers", { token: d.token }));
      setBudget(await plat("/tg/research-orchestrator/budget", { token: d.token }));
      setTemplates(await plat("/tg/research-orchestrator/templates", { token: d.token }));
      setNotebook(await plat("/tg/research-orchestrator/notebook", { token: d.token }));
      setFailures(await plat("/tg/research-orchestrator/failures", { token: d.token }));
      setHypotheses(await plat("/tg/research-orchestrator/hypotheses", { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Autonomous Research Orchestrator"
        subtitle="Experiment queue, workers, budgets, templates, notebook and deterministic offline research scheduling."
      />
      <TradingTabs />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="research-only" style={pill("#5B8CFF")}>RESEARCH ONLY</span>
        <span className="mono" data-testid="offline-first" style={pill("#5B8CFF")}>OFFLINE-FIRST</span>
        <span className="mono" data-testid="deterministic" style={pill("#5B8CFF")}>DETERMINISTIC ORCHESTRATION</span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-order-execution" style={pill("#FF5A5A")}>NO ORDER EXECUTION</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
        <span className="mono" data-testid="no-guaranteed-profit" style={pill("#F5A623")}>NO GUARANTEED PROFITABILITY</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/research-orchestrator/dashboard", setDash)}>Overview</Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/research-orchestrator/verdict", setVerdict)}>Verdict</Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>Bootstrap Pipeline</Button>
          <Button data-testid="load-jobs" onClick={() => load("/tg/research-orchestrator/jobs", setJobs)}>Job Queue</Button>
          <Button data-testid="run-tick" onClick={() => load("/tg/research-orchestrator/tick?max_jobs=3", setBootstrap, "POST")}>Scheduler Tick</Button>
          <Button data-testid="load-workers" onClick={() => load("/tg/research-orchestrator/workers", setWorkers)}>Workers</Button>
          <Button data-testid="load-budget" onClick={() => load("/tg/research-orchestrator/budget", setBudget)}>Budget</Button>
          <Button data-testid="load-templates" onClick={() => load("/tg/research-orchestrator/templates", setTemplates)}>Templates</Button>
          <Button data-testid="load-notebook" onClick={() => load("/tg/research-orchestrator/notebook", setNotebook)}>Lab Notebook</Button>
          <Button data-testid="load-failures" onClick={() => load("/tg/research-orchestrator/failures", setFailures)}>Failure Analysis</Button>
          <Button data-testid="load-calendar" onClick={() => load("/tg/research-orchestrator/calendar", setCalendar)}>Research Calendar</Button>
          <Button data-testid="load-evidence" onClick={() => load("/tg/research-orchestrator/evidence", setEvidence)}>Evidence</Button>
          <Button data-testid="refuse-broker" onClick={() => load("/tg/research-orchestrator/broker/connect", setBrokerBlock, "POST")}>Probe Broker</Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/research-orchestrator/credentials", setCredBlock, "POST", { api_key: "x" })}>Probe Creds</Button>
          <Button data-testid="refuse-orders" onClick={() => load("/tg/research-orchestrator/orders", setOrderBlock, "POST")}>Probe Orders</Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/research-orchestrator/certify", setVerdict, "POST")}>Certify</Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Lab Overview</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="queue-total">Jobs total: {dash.overview?.queue?.total ?? 0}</Text>
            <Text className="mono" data-testid="workers-idle">Workers idle: {dash.overview?.workers?.idle ?? 0}</Text>
            <Text className="mono" data-testid="budget-remaining">Budget remaining: {dash.overview?.budget?.remaining_units}</Text>
            <Text className="mono" data-testid="authority-live-false">LIVE_TRADING_AUTHORIZED={String(dash.LIVE_TRADING_AUTHORIZED)}</Text>
          </Card>
        )}
        {verdict && (
          <Card data-testid="verdict-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="verdict-value">{verdict.verdict}</Text>
            <Text className="mono" data-testid="max-state">{verdict.max_state}</Text>
          </Card>
        )}
        {bootstrap && (
          <Card data-testid="bootstrap-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Bootstrap / Tick</Heading>
            <Text className="mono" data-testid="session-id">Session: {bootstrap.session_id || "n/a"}</Text>
            <Text className="mono" data-testid="ran-count">Ran: {(bootstrap.ran || []).length}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 180 }}>{JSON.stringify(bootstrap.ran || bootstrap.queue, null, 2)}</pre>
          </Card>
        )}
        {jobs && (
          <Card data-testid="jobs-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Experiment Queue</Heading>
            <Text className="mono" data-testid="jobs-count">Count: {jobs.count}</Text>
            <pre className="mono" data-testid="jobs-json" style={{ fontSize: 11, overflow: "auto", maxHeight: 200 }}>{JSON.stringify(jobs.jobs, null, 2)}</pre>
          </Card>
        )}
        {workers && (
          <Card data-testid="workers-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Worker Pool</Heading>
            <Text className="mono" data-testid="max-workers">Max: {workers.max_workers}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>{JSON.stringify(workers.workers, null, 2)}</pre>
          </Card>
        )}
        {budget && (
          <Card data-testid="budget-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Compute Budget</Heading>
            <Text className="mono" data-testid="budget-total">Total: {budget.total_units}</Text>
            <Text className="mono" data-testid="budget-spent">Spent: {budget.spent_units}</Text>
            <Text className="mono" data-testid="budget-state">State: {budget.state}</Text>
          </Card>
        )}
        {templates && (
          <Card data-testid="templates-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Experiment Templates</Heading>
            <Text className="mono" data-testid="templates-count">Count: {templates.count}</Text>
          </Card>
        )}
        {notebook && (
          <Card data-testid="notebook-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Lab Notebook</Heading>
            <Text data-testid="notebook-title">{notebook.title}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 180 }}>{JSON.stringify({ journal: notebook.journal, timeline: (notebook.timeline || []).slice(0, 5) }, null, 2)}</pre>
          </Card>
        )}
        {failures && (
          <Card data-testid="failures-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Failure Analysis</Heading>
            <Text className="mono" data-testid="failed-count">Failed: {failures.failed_count}</Text>
          </Card>
        )}
        {hypotheses && (
          <Card data-testid="hypotheses-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Hypotheses</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify(hypotheses.hypotheses, null, 2)}</pre>
          </Card>
        )}
        {calendar && (
          <Card data-testid="calendar-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Research Calendar</Heading>
            <Text className="mono" data-testid="calendar-note">{calendar.note}</Text>
            <pre className="mono" style={{ fontSize: 11 }}>{JSON.stringify(calendar.slots, null, 2)}</pre>
          </Card>
        )}
        {evidence && (
          <Card data-testid="evidence-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Evidence</Heading>
            <Text className="mono">security ok={String(evidence.security?.ok)}</Text>
          </Card>
        )}
        {(brokerBlock || credBlock || orderBlock) && (
          <Card data-testid="refusal-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Boundary Refusals</Heading>
            <Text className="mono" data-testid="broker-refused">{brokerBlock && `broker=${brokerBlock.refused}`}</Text>
            <Text className="mono" data-testid="cred-refused">{credBlock && `creds=${credBlock.refused}`}</Text>
            <Text className="mono" data-testid="order-refused">{orderBlock && `orders=${orderBlock.refused}`}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return { border: `1px solid ${color}`, color, padding: "2px 8px", borderRadius: 4, fontSize: 11 };
}
