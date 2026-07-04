"use client";
import { Panel, Eyebrow, Ring } from "@/components/ui";
import { color } from "@/lib/departments";
import { useInfraHealth } from "@/lib/useInfraHealth";

const CYAN = color("INFRA");

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
    </div>
  );
}
