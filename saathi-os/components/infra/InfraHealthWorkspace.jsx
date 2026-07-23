"use client";
import { useState, useEffect } from "react";
import { Panel, Eyebrow, Ring, StatusBadge, Text, Card, Heading } from "@/components/ui";
import { color } from "@/lib/departments";
import { useInfraHealth } from "@/lib/useInfraHealth";
import { testHumanBrowser, fetchCodeMemory } from "@/lib/api";

const CYAN = color("INFRA");

function CodeMemoryCard() {
  const [d, setD] = useState(null);
  useEffect(() => {
    fetchCodeMemory()
      .then(setD)
      .catch(() => {});
  }, []);
  const installed = d?.installed;
  return (
    <Card className="home-card">
      <Heading level={3} size="md">
        Code Memory
      </Heading>
      <Text tone="muted" size="sm" as="p">
        Local code-intelligence (codebase-memory-mcp) — connector behind the registry.
      </Text>
      <div style={{ marginTop: 10 }}>
        {d == null ? (
          <StatusBadge status="pending" label="Checking" />
        ) : installed ? (
          <StatusBadge
            status="success"
            label={`${d.count} project${d.count === 1 ? "" : "s"} indexed`}
          />
        ) : (
          <StatusBadge status="neutral" label={d.detail || "Not installed on this host"} />
        )}
      </div>
      {installed && d.projects?.length > 0 && (
        <Text tone="disabled" size="xs" mono as="p">
          {d.projects
            .map((p) => (typeof p === "string" ? p : p.name || p.project || p.id))
            .slice(0, 4)
            .join(", ")}
        </Text>
      )}
    </Card>
  );
}

function HumanBrowserTest() {
  const [state, setState] = useState({ status: "idle", msg: "" });
  async function run() {
    let token = typeof window !== "undefined" ? localStorage.getItem("saathi_token") : "";
    if (!token) {
      token = window.prompt("SAATHI_TOKEN (to authorize the test job):") || "";
      if (token) localStorage.setItem("saathi_token", token);
    }
    setState({ status: "running", msg: "enqueuing signed job → waiting for Mac Agent…" });
    try {
      const r = await testHumanBrowser(token);
      if (r.ok) setState({ status: "ok", msg: `Agent drove Chrome → "${r.result?.title || r.result?.url}"` });
      else setState({ status: "err", msg: r.error + (r.hint ? ` — ${r.hint}` : "") });
    } catch (e) {
      setState({ status: "err", msg: String(e) });
    }
  }
  const badge =
    state.status === "ok"
      ? "success"
      : state.status === "err"
        ? "danger"
        : state.status === "running"
          ? "pending"
          : "neutral";
  return (
    <Card className="home-card">
      <Heading level={3} size="md">
        Human Browser Driver
      </Heading>
      <Text tone="muted" size="sm" as="p">
        Signs a job → Mac Agent opens real Chrome → returns the page title. Authorization required.
      </Text>
      <div className="home-section-actions">
        <button
          type="button"
          className="shell-topbar-chip"
          onClick={run}
          disabled={state.status === "running"}
          style={{
            padding: "8px 14px",
            borderRadius: 20,
            border: `1px solid ${CYAN}`,
            background: `${CYAN}18`,
            color: CYAN,
            cursor: state.status === "running" ? "wait" : "pointer",
          }}
        >
          {state.status === "running" ? "Testing…" : "Test a job"}
        </button>
        {state.msg && <StatusBadge status={badge} label={state.status} />}
      </div>
      {state.msg && (
        <Text tone="muted" size="xs" as="p">
          {state.msg}
        </Text>
      )}
    </Card>
  );
}

function Row({ name, light, note }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "7px 2px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <span style={{ display: "flex", gap: 9, alignItems: "center", fontSize: 14 }}>
        <span style={{ fontSize: 12 }}>{light || "○"}</span>
        {name}
      </span>
      {note != null && (
        <span style={{ fontSize: 12, opacity: 0.55 }}>{note}</span>
      )}
    </div>
  );
}

function Section({ title, rows }) {
  return (
    <Panel style={{ padding: 18 }}>
      <Eyebrow style={{ color: CYAN }}>{title}</Eyebrow>
      <div style={{ marginTop: 8 }}>
        {rows.length ? (
          rows
        ) : (
          <div style={{ opacity: 0.4, fontSize: 13, padding: "8px 0" }}>—</div>
        )}
      </div>
    </Panel>
  );
}

/**
 * Shared infrastructure health workspace (M47.5).
 * Canonical home: /monitoring · legacy /infrastructure redirects here.
 */
export default function InfraHealthWorkspace() {
  const { data, live, error } = useInfraHealth();
  const s = data?.score;

  const models = (data?.models || []).map((m) => (
    <Row key={m.id} name={m.id.split("/")[0]} light={m.light} note={m.available ? "ready" : "no key"} />
  ));
  const browser = (data?.browser || []).map((b) => (
    <Row key={b.id} name={b.id} light={b.light} note={b.available ? "up" : "off"} />
  ));
  const connectors = (data?.connectors || []).map((c) => (
    <Row
      key={c.id}
      name={c.display_name || c.id}
      light={c.light}
      note={c.latency_ms != null ? `${c.latency_ms}ms` : c.status}
    />
  ));
  const conv = data?.conversation || {};
  const conversation = [
    <Row key="voice" name="Voice" light={conv.voice?.light} />,
    <Row key="stt" name={`STT (${conv.stt?.driver || "—"})`} light={conv.stt?.light} />,
    <Row key="tts" name={`TTS (${conv.tts?.driver || "—"})`} light={conv.tts?.light} />,
    <Row key="wake" name="Wake Word" light={conv.wakeword?.light} />,
    <Row key="sessions" name="Sessions" light="🟢" note={conv.sessions ?? 0} />,
  ];

  return (
    <div className="infra-workspace">
      <div className="home-section-head">
        <div>
          <Heading level={2} size="md">
            Engine warning light
          </Heading>
          <Text tone="muted" size="sm" as="p">
            {error ? "offline — platform unreachable" : live ? "live health feed" : "connecting…"}
          </Text>
        </div>
        {s && (
          <Ring
            value={s.overall / 100}
            color={CYAN}
            size={120}
            stroke={9}
            label={`${s.overall}%`}
            sub="health"
          />
        )}
      </div>

      {s && (
        <div className="home-metrics" style={{ marginBottom: 16 }}>
          {[
            ["Models", s.models],
            ["Browser", s.browser],
            ["Connectors", s.connectors],
            ["Voice", s.voice],
          ].map(([k, v]) => (
            <div key={k} className="home-metric">
              <Text tone="muted" size="xs" mono>
                {k}
              </Text>
              <div className="home-metric-value" style={{ fontSize: 20 }}>
                {v}%
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="missions-grid">
        <Section title="LLMs" rows={models} />
        <Section title="Browser" rows={browser} />
        <Section title="Connectors" rows={connectors} />
        <Section title="Conversation" rows={conversation} />
      </div>

      <div className="shell-page-grid" style={{ marginTop: 16 }}>
        <HumanBrowserTest />
        <CodeMemoryCard />
      </div>
    </div>
  );
}
