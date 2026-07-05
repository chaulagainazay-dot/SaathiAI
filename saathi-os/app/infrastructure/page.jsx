"use client";
import { useState } from "react";
import { Panel, Eyebrow, Ring } from "@/components/ui";
import { color } from "@/lib/departments";
import { useInfraHealth } from "@/lib/useInfraHealth";
import { useEffect } from "react";
import { testHumanBrowser, fetchCodeMemory } from "@/lib/api";

const CYAN = color("INFRA");

function CodeMemoryCard() {
  const [d, setD] = useState(null);
  useEffect(() => { fetchCodeMemory().then(setD).catch(() => {}); }, []);
  const installed = d?.installed;
  return (
    <Panel style={{ padding: 18, marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <Eyebrow style={{ color: CYAN }}>🧠 Code Memory (codebase-memory-mcp)</Eyebrow>
          <div style={{ fontSize: 13, opacity: 0.6, marginTop: 4 }}>
            Local code-intelligence engine — 14 tools, tree-sitter knowledge graph. Connector behind the registry.
          </div>
          <div style={{ fontSize: 13, marginTop: 8, color: installed ? "#4FD07A" : "#8FA0C4" }}>
            {d == null ? "checking…"
              : installed
                ? `🟢 ${d.count} project${d.count === 1 ? "" : "s"} indexed${d.projects?.length ? ": " + d.projects.map((p) => (typeof p === "string" ? p : p.name || p.project || p.id)).slice(0, 4).join(", ") : ""}`
                : `⚪ ${d.detail || "not installed on this host (runs Mac-side)"}`}
          </div>
        </div>
      </div>
    </Panel>
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
  const clr = { idle: "#8FA0C4", running: "#E8B84B", ok: "#4FD07A", err: "#FF5A5A" }[state.status];
  return (
    <Panel style={{ padding: 18, marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <Eyebrow style={{ color: CYAN }}>Human Browser Driver</Eyebrow>
          <div style={{ fontSize: 13, opacity: 0.6, marginTop: 4 }}>
            Signs a job on the VM → your Mac Agent opens example.com in real Chrome → returns the title.
          </div>
          {state.msg && <div style={{ fontSize: 13, marginTop: 8, color: clr }}>{state.msg}</div>}
        </div>
        <button onClick={run} disabled={state.status === "running"}
          style={{ padding: "9px 16px", borderRadius: 20, whiteSpace: "nowrap",
            border: `1px solid ${CYAN}`, background: `${CYAN}18`, color: CYAN,
            cursor: state.status === "running" ? "wait" : "pointer" }}>
          {state.status === "running" ? "Testing…" : "Test a job"}
        </button>
      </div>
    </Panel>
  );
}

function Row({ name, light, note }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "7px 2px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
      <span style={{ display: "flex", gap: 9, alignItems: "center", fontSize: 14 }}>
        <span style={{ fontSize: 12 }}>{light || "⚪"}</span>{name}
      </span>
      {note != null && <span style={{ fontSize: 12, opacity: 0.55 }}>{note}</span>}
    </div>
  );
}

function Section({ title, rows }) {
  return (
    <Panel style={{ padding: 18 }}>
      <Eyebrow style={{ color: CYAN }}>{title}</Eyebrow>
      <div style={{ marginTop: 8 }}>
        {rows.length ? rows : <div style={{ opacity: 0.4, fontSize: 13, padding: "8px 0" }}>—</div>}
      </div>
    </Panel>
  );
}

export default function Infrastructure() {
  const { data, live, error } = useInfraHealth();
  const s = data?.score;

  const models = (data?.models || []).map((m) => (
    <Row key={m.id} name={m.id.split("/")[0]} light={m.light} note={m.available ? "ready" : "no key"} />
  ));
  const browser = (data?.browser || []).map((b) => (
    <Row key={b.id} name={b.id} light={b.light} note={b.available ? "up" : "off"} />
  ));
  const connectors = (data?.connectors || []).map((c) => (
    <Row key={c.id} name={c.display_name || c.id} light={c.light}
      note={c.latency_ms != null ? `${c.latency_ms}ms` : c.status} />
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
    <div className="only-desktop" style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 22 }}>
        <div>
          <Eyebrow style={{ color: CYAN }}>Infrastructure</Eyebrow>
          <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>Engine Warning Light</div>
          <div style={{ fontSize: 13, opacity: 0.5, marginTop: 4 }}>
            {error ? "offline — platform unreachable" : live ? "live" : "connecting…"}
          </div>
        </div>
        {s && <Ring value={s.overall / 100} color={CYAN} size={132} stroke={9}
          label={`${s.overall}%`} sub="health" />}
      </div>

      {s && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 18, fontSize: 13 }}>
          {[["Models", s.models], ["Browser", s.browser], ["Connectors", s.connectors], ["Voice", s.voice]]
            .map(([k, v]) => (
              <span key={k} className="glass" style={{ padding: "6px 12px", borderRadius: 20 }}>
                {k} <b style={{ color: CYAN }}>{v}%</b>
              </span>
            ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 14 }}>
        <Section title="LLMs" rows={models} />
        <Section title="Browser" rows={browser} />
        <Section title="Connectors" rows={connectors} />
        <Section title="Conversation" rows={conversation} />
      </div>

      <HumanBrowserTest />
      <CodeMemoryCard />
    </div>
  );
}
