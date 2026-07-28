"use client";
// Saathi Chat (M8) — the central intelligence interface.
// Sidebar: search, pinned, recent, folders, project selector, new chat.
// Main: streamed messages, agent/model selector, citations + execution
// timeline panel, memory indicator, composer with attachments.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import AgentRunPanel from "./AgentRunPanel";
import VoiceControl from "./VoiceControl";
import { useVoiceOutput } from "../voice/VoiceOutputProvider";

const AGENTS = ["", "planner", "researcher", "coder", "reviewer", "architect", "writer", "ceo"];

const S = {
  wrap: { display: "flex", height: "calc(100vh - 60px)", gap: 0, color: "#e8ecf5" },
  side: {
    width: 272, minWidth: 220, borderRight: "1px solid rgba(255,255,255,.08)",
    padding: "14px 10px", overflowY: "auto", background: "rgba(255,255,255,.02)",
    backdropFilter: "blur(12px)", display: "flex", flexDirection: "column", gap: 8,
  },
  main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },
  panel: {
    width: 280, borderLeft: "1px solid rgba(255,255,255,.08)", padding: 14,
    overflowY: "auto", background: "rgba(255,255,255,.02)", fontSize: 12,
  },
  input: {
    width: "100%", background: "rgba(255,255,255,.05)", color: "#e8ecf5",
    border: "1px solid rgba(255,255,255,.1)", borderRadius: 10, padding: "8px 10px",
    fontSize: 13, outline: "none",
  },
  btn: {
    background: "rgba(0,191,165,.14)", color: "#4fe3cb", border: "1px solid rgba(0,191,165,.35)",
    borderRadius: 10, padding: "8px 12px", fontSize: 13, cursor: "pointer",
  },
  convo: (active) => ({
    padding: "8px 10px", borderRadius: 10, cursor: "pointer", fontSize: 13,
    background: active ? "rgba(0,191,165,.12)" : "transparent",
    border: active ? "1px solid rgba(0,191,165,.3)" : "1px solid transparent",
    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
  }),
  bubble: (role) => ({
    alignSelf: role === "user" ? "flex-end" : "flex-start",
    maxWidth: "78%", padding: "10px 14px", borderRadius: 14, fontSize: 14,
    lineHeight: 1.55, whiteSpace: "pre-wrap", wordBreak: "break-word",
    background: role === "user" ? "rgba(108,63,207,.25)" : "rgba(255,255,255,.05)",
    border: "1px solid rgba(255,255,255,.08)",
  }),
  tag: {
    display: "inline-block", padding: "1px 8px", borderRadius: 999, fontSize: 10,
    letterSpacing: ".08em", background: "rgba(255,255,255,.07)", marginRight: 6,
  },
};

/**
 * @param {{ compact?: boolean }} props
 * compact=true → Ask Saathi panel mode: same transport, reduced chrome.
 */
export default function ChatWorkspace({ compact = false } = {}) {
  const [convs, setConvs] = useState([]);
  const [active, setActive] = useState(null);
  const [detail, setDetail] = useState(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [agent, setAgent] = useState("");
  const [project, setProject] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState("");
  const [teamMode, setTeamMode] = useState(false);
  const [teamRunId, setTeamRunId] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);
  const voiceOutput = useVoiceOutput();

  const loadConvs = useCallback(async () => {
    try {
      const url = query
        ? `${API_BASE}/api/v1/chat/search?q=${encodeURIComponent(query)}`
        : `${API_BASE}/api/v1/chat/conversations${project ? `?project_id=${project}` : ""}`;
      const r = await afetch(url, { cache: "no-store" });
      const j = await r.json();
      setConvs(j.conversations || j.results || []);
      setError("");
    } catch { setError("Backend unreachable — is the SaathiAI server running?"); }
  }, [query, project]);

  const loadDetail = useCallback(async (cid) => {
    if (!cid) return;
    try {
      const r = await afetch(`${API_BASE}/api/v1/chat/conversations/${cid}?limit=200`, { cache: "no-store" });
      setDetail(await r.json());
    } catch { /* keep last */ }
  }, []);

  const loadLatestTeamRun = useCallback(async (cid) => {
    if (!cid) { setTeamRunId(null); return; }
    try {
      const r = await afetch(
        `${API_BASE}/api/v1/agents/runs?conversation_id=${cid}&limit=1`,
        { cache: "no-store" });
      const j = await r.json();
      setTeamRunId(j.runs?.[0]?.id || null);
    } catch { setTeamRunId(null); }
  }, []);

  useEffect(() => { loadConvs(); }, [loadConvs]);
  useEffect(() => { loadDetail(active); loadLatestTeamRun(active); }, [active, loadDetail, loadLatestTeamRun]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); },
    [detail?.messages?.length, streamText]);

  async function newConversation() {
    const r = await afetch(`${API_BASE}/api/v1/chat/conversations`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "", project_id: project }),
    });
    const c = await r.json();
    await loadConvs();
    setActive(c.id);
  }

  function stopStream() {
    try {
      abortRef.current?.abort();
    } catch {
      /* ignore */
    }
    abortRef.current = null;
    setBusy(false);
    setStreamText("");
  }

  async function send() {
    const t = text.trim();
    if (!t || busy) return;
    let cid = active;
    if (!cid) {
      const r = await afetch(`${API_BASE}/api/v1/chat/conversations`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "", project_id: project }),
      });
      if (!r.ok) {
        setError(`Create conversation failed (${r.status})`);
        return;
      }
      cid = (await r.json()).id;
      setActive(cid);
    }
    setText(""); setBusy(true); setStreamText(""); setError("");
    setDetail((d) => d ? { ...d, messages: [...(d.messages || []),
      { id: "tmp", role: "user", content: t, status: "complete" }] } : d);

    if (teamMode && !compact) {
      // Real M10 orchestration — multi-agent, task graph, approvals.
      try {
        const r = await afetch(`${API_BASE}/api/v1/chat/conversations/${cid}/team-run`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ objective: t, execute: true }),
        });
        const j = await r.json();
        if (j.error) setError(j.error);
        else setTeamRunId(j.run_id);
      } catch { setError("Team run failed — network or auth."); }
      setBusy(false);
      await loadDetail(cid); await loadConvs();
      return;
    }

    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const r = await afetch(`${API_BASE}/api/v1/chat/conversations/${cid}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: t, agent: compact ? "" : agent, stream: true }),
        signal: ac.signal,
      });
      if (!r.ok) {
        setError(`Send failed (${r.status}) — not shown as success.`);
        setBusy(false);
        return;
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n"); buf = frames.pop();
        for (const f of frames) {
          if (!f.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(f.slice(6));
            if (ev.event === "delta") setStreamText((s) => s + ev.text);
            if (ev.event === "error") setError(ev.detail || "stream error");
          } catch {
            /* ignore partial JSON */
          }
        }
      }
    } catch (e) {
      if (e?.name === "AbortError") setError("Stream stopped.");
      else setError("Send failed — network or auth.");
    }
    abortRef.current = null;
    setStreamText(""); setBusy(false);
    await loadDetail(cid); await loadConvs();
  }

  async function togglePin(c, e) {
    e.stopPropagation();
    await afetch(`${API_BASE}/api/v1/chat/conversations/${c.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned: !c.pinned }),
    });
    loadConvs();
  }

  const pinned = useMemo(() => convs.filter((c) => c.pinned), [convs]);
  const recent = useMemo(() => convs.filter((c) => !c.pinned), [convs]);
  const conv = detail?.conversation;

  const wrapStyle = compact
    ? { display: "flex", flexDirection: "column", height: "100%", minHeight: 320, color: "var(--text-primary, #e8ecf5)" }
    : S.wrap;

  return (
    <div style={wrapStyle} data-chat-mode={compact ? "compact" : "full"}>
      {/* ── sidebar (full workspace only) ── */}
      {!compact && (
      <aside style={S.side}>
        <button style={S.btn} onClick={newConversation}>＋ New chat</button>
        <input style={S.input} placeholder="Search conversations…" value={query}
               onChange={(e) => setQuery(e.target.value)} />
        <input style={S.input} placeholder="Project (optional)" value={project}
               onChange={(e) => setProject(e.target.value)} />
        {pinned.length > 0 && <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em" }}>PINNED</div>}
        {pinned.map((c) => (
          <div key={c.id} style={S.convo(c.id === active)} onClick={() => setActive(c.id)}>
            <span onClick={(e) => togglePin(c, e)} title="unpin" style={{ marginRight: 6 }}>📌</span>
            {c.title || "Untitled"}
          </div>))}
        <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em" }}>RECENT</div>
        {recent.map((c) => (
          <div key={c.id} style={S.convo(c.id === active)} onClick={() => setActive(c.id)}>
            <span onClick={(e) => togglePin(c, e)} title="pin" style={{ marginRight: 6, opacity: .35 }}>📌</span>
            {c.title || "Untitled"}{c.folder ? <span style={{ ...S.tag, marginLeft: 6 }}>{c.folder}</span> : null}
          </div>))}
        {convs.length === 0 && <div style={{ fontSize: 12, opacity: .5 }}>No conversations yet.</div>}
      </aside>
      )}

      {/* ── main ── */}
      <main style={compact ? { ...S.main, minHeight: 280 } : S.main}>
        <header style={{ display: "flex", gap: 10, alignItems: "center",
                         padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,.08)" }}>
          <strong style={{ fontSize: 14, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {compact ? "Ask Saathi" : (conv?.title || "Saathi Chat")}
          </strong>
          {!compact && conv && <span style={S.tag}>{(detail?.memory_links?.length || 0)} memories</span>}
          {!compact && conv && <span style={S.tag}>{conv.tokens_in + conv.tokens_out} tok</span>}
          {!compact && (
            <>
          <select value={agent} onChange={(e) => setAgent(e.target.value)}
                  disabled={teamMode}
                  style={{ ...S.input, width: 130, opacity: teamMode ? .4 : 1 }}>
            {AGENTS.map((a) => <option key={a} value={a}>{a ? `@${a}` : "saathi"}</option>)}
          </select>
          <button
            onClick={() => setTeamMode((v) => !v)}
            title="Multi-agent orchestration: planner/builder/reviewer team with approvals"
            style={{
              ...S.btn, background: teamMode ? "rgba(108,63,207,.25)" : S.btn.background,
              borderColor: teamMode ? "rgba(108,63,207,.5)" : undefined,
              color: teamMode ? "#c9b6ff" : S.btn.color,
            }}>
            {teamMode ? "☰ Team" : "☰ Solo"}
          </button>
          <button
            onClick={() => setVoiceOpen((v) => !v)}
            title="Voice mode (browser microphone + speech)"
            aria-pressed={voiceOpen}
            style={{
              ...S.btn, background: voiceOpen ? "rgba(0,191,165,.2)" : S.btn.background,
              borderColor: voiceOpen ? "rgba(0,191,165,.5)" : undefined,
            }}>
            🎙
          </button>
            </>
          )}
          {compact && (
            <button type="button" style={S.btn} onClick={newConversation} title="New conversation">
              New
            </button>
          )}
        </header>

        <section style={{ flex: 1, overflowY: "auto", display: "flex",
                          flexDirection: "column", gap: 10, padding: 18 }}>
          {!conv && (
            <div style={{ margin: "auto", textAlign: "center", opacity: .6, fontSize: 14 }}>
              <div style={{ fontSize: 34, marginBottom: 10 }}>◍</div>
              Start a conversation. Every reply routes through the ExecutionGateway —<br />
              memory, knowledge and project context load automatically.
            </div>)}
          {(detail?.messages || []).map((m) => (
            <div key={m.id} style={S.bubble(m.role)}>
              {m.role !== "user" && (
                <div style={{ fontSize: 10, opacity: .55, marginBottom: 4 }}>
                  {m.model ? `⚡ ${m.model}` : "saathi"}{m.status === "error" ? " · error" : ""}
                </div>)}
              {m.content}
              {m.role !== "user" && m.status !== "error" && m.content ? (
                <div className="voice-message-actions">
                  <button
                    type="button"
                    className="voice-message-speak"
                    onClick={() =>
                      voiceOutput.speak(m.content, {
                        source: "assistant",
                        language: "en-US",
                      })
                    }
                    disabled={!voiceOutput.enabled || voiceOutput.busy}
                    aria-label="Speak assistant response"
                  >
                    Speak
                  </button>
                </div>
              ) : null}
            </div>))}
          {busy && (
            <div style={S.bubble("assistant")}>
              {streamText || <span style={{ opacity: .6 }}>Saathi is thinking…</span>}
              <span style={{ opacity: .5 }}>▍</span>
            </div>)}
          <div ref={bottomRef} />
        </section>

        {error && <div role="alert" style={{ padding: "6px 16px", color: "#ff8c8c", fontSize: 12 }}>{error}</div>}

        {!compact && voiceOpen && (
          <div style={{ padding: "0 14px 10px" }}>
            <VoiceControl
              conversationId={active}
              chatMode={teamMode ? "team" : "solo"}
              agent={agent}
              onTurn={async (turn) => {
                if (turn.command) return; // command turns don't touch chat history
                await loadDetail(active); await loadConvs();
                if (teamMode && turn.agent_run_id) setTeamRunId(turn.agent_run_id);
              }} />
          </div>
        )}

        <footer style={{ display: "flex", gap: 8, padding: 14,
                         borderTop: "1px solid rgba(255,255,255,.08)" }}>
          <textarea style={{ ...S.input, resize: "none", height: compact ? 48 : 56 }} value={text}
            placeholder={teamMode && !compact ? "Describe the objective for the agent team…"
                        : agent && !compact ? `Message @${agent}…` : "Message Saathi…"}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            aria-label="Message Saathi" />
          {busy ? (
            <button type="button" style={{ ...S.btn, alignSelf: "stretch", background: "rgba(255,90,90,.15)", color: "#ff8c8c" }}
              onClick={stopStream} aria-label="Stop streaming">
              Stop
            </button>
          ) : (
            <button type="button" style={{ ...S.btn, alignSelf: "stretch" }} onClick={send}>
              {teamMode && !compact ? "Run team" : "Send"}
            </button>
          )}
        </footer>
      </main>

      {/* ── context panel (full workspace only) ── */}
      {!compact && conv && (
        <aside style={S.panel} className="only-desktop">
          {teamRunId && (
            <>
              <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em", marginBottom: 8 }}>
                AGENT TEAM RUN
              </div>
              <AgentRunPanel runId={teamRunId} onClose={() => setTeamRunId(null)} />
              <div style={{ borderTop: "1px solid rgba(255,255,255,.08)", margin: "14px 0" }} />
            </>
          )}
          <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em", marginBottom: 8 }}>EXECUTION TIMELINE</div>
          {(detail?.executions || []).slice(-6).reverse().map((x) => (
            <div key={x.id} style={{ marginBottom: 8, padding: 8, borderRadius: 8,
                                     background: "rgba(255,255,255,.04)" }}>
              <div>{x.status === "success" ? "🟢" : "🔴"} {x.provider || "gateway"}</div>
              <div style={{ opacity: .5 }}>{x.intent_id?.slice(0, 18)} · {x.duration_sec}s</div>
            </div>))}
          {(detail?.executions || []).length === 0 && <div style={{ opacity: .5 }}>No executions yet.</div>}

          <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em", margin: "14px 0 8px" }}>MEMORY LINKS</div>
          {(detail?.memory_links || []).slice(0, 6).map((l) => (
            <div key={l.id} style={{ marginBottom: 6, opacity: .8 }}>
              <span style={S.tag}>{l.memory_kind}</span>{l.memory_ref.slice(0, 20)}
            </div>))}
          {(detail?.memory_links || []).length === 0 && <div style={{ opacity: .5 }}>None linked yet.</div>}

          <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em", margin: "14px 0 8px" }}>AGENT RUNS</div>
          {(detail?.agent_runs || []).slice(-5).reverse().map((a) => (
            <div key={a.id} style={{ marginBottom: 6 }}>
              @{a.agent} {a.delegated_by ? `← @${a.delegated_by}` : ""} · {a.status}
            </div>))}
          {(detail?.agent_runs || []).length === 0 && <div style={{ opacity: .5 }}>No agent runs.</div>}

          <div style={{ fontSize: 10, opacity: .5, letterSpacing: ".14em", margin: "14px 0 8px" }}>CHECKPOINTS</div>
          {(detail?.checkpoints || []).slice(0, 4).map((k) => (
            <div key={k.id} style={{ marginBottom: 6, opacity: .8 }}>⎌ {k.label || k.id.slice(0, 8)}</div>))}
        </aside>)}
    </div>
  );
}
