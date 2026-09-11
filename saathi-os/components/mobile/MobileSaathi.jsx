"use client";
import { useState, useRef, useEffect } from "react";
import { Eyebrow } from "@/components/ui";
import { sendChat, login } from "@/lib/api";

const EXAMPLE_PROMPTS = [
  "Today's cafeteria sold 171 Dal Bhat.",
  "Approve the AI Studio campaign.",
  "How much revenue did we make today?",
  "Show today's priorities.",
];

export default function MobileSaathi() {
  const [chat, setChat] = useState([]);   // {role:"you"|"saathi", text}
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [needPw, setNeedPw] = useState(false);
  const [pw, setPw] = useState("");
  const pendingRef = useRef(null);         // message to resend after unlock
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, busy, needPw]);

  const send = async (text) => {
    text = (text || "").trim();
    if (!text || busy) return;
    setChat((c) => [...c, { role: "you", text }]); setAsk(""); setBusy(true);
    try {
      const r = await sendChat(text, "mobile");
      setChat((c) => [...c, { role: "saathi", text: r.reply || "…" }]);
    } catch (e) {
      if (String(e).includes("unauthorized")) {
        pendingRef.current = text; setNeedPw(true);       // show inline unlock, then retry
      } else {
        setChat((c) => [...c, { role: "saathi", text: "Sorry — I couldn't reach my brain just now." }]);
      }
    } finally { setBusy(false); }
  };

  const unlock = async () => {
    if (!pw.trim()) return;
    setBusy(true);
    try {
      const r = await login(pw);
      if (r.ok) {
        setNeedPw(false); setPw("");
        const pending = pendingRef.current; pendingRef.current = null;
        if (pending) await send(pending);
      } else {
        setChat((c) => [...c, { role: "saathi", text: "That password didn't work — try again." }]);
      }
    } catch {
      setChat((c) => [...c, { role: "saathi", text: "Couldn't sign in just now." }]);
    } finally { setBusy(false); }
  };

  return (
    <div className="m-page" style={{ minHeight: "78vh", display: "flex", flexDirection: "column" }}>
      <div className="m-card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="pulse" style={{ width: 9, height: 9, borderRadius: "50%", background: "#8FB4FF", boxShadow: "0 0 12px #8FB4FF" }} />
          <Eyebrow>Saathi</Eyebrow>
        </div>
        <p style={{ fontSize: 14, color: "var(--color-ink-300)", marginTop: 10, lineHeight: 1.5 }}>
          Good morning, Ajay. Ask me anything — today's lesson, revenue, or what needs your attention.
        </p>
      </div>

      {/* conversation */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8, overflowY: "auto", paddingBottom: 8 }}>
        {chat.length === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <Eyebrow style={{ padding: "0 4px 4px" }}>Try asking</Eyebrow>
            {EXAMPLE_PROMPTS.map((ex) => (
              <button key={ex} onClick={() => send(ex)}
                style={{ textAlign: "left", padding: "13px 15px", borderRadius: 14, cursor: "pointer",
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  color: "var(--color-ink-200)", fontSize: 14 }}>
                "{ex}"
              </button>
            ))}
          </div>
        )}
        {chat.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === "you" ? "flex-end" : "flex-start",
            maxWidth: "82%", padding: "9px 14px", borderRadius: 16, fontSize: 14, lineHeight: 1.45,
            background: m.role === "you" ? "rgba(143,180,255,0.18)" : "rgba(255,255,255,0.06)" }}>
            {m.text}
          </div>
        ))}
        {busy && <div style={{ alignSelf: "flex-start", fontSize: 13, color: "var(--color-ink-400)", padding: "4px 14px" }}>Saathi is thinking…</div>}
        <div ref={endRef} />
      </div>

      {/* input / inline unlock */}
      {needPw ? (
        <div style={{ paddingTop: 8 }}>
          <div style={{ fontSize: 12, color: "var(--color-ink-400)", padding: "0 4px 8px" }}>
            🔒 Enter your password once to unlock Saathi on this phone.
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && unlock()} disabled={busy} autoFocus
              placeholder="Password"
              style={{ flex: 1, padding: "13px 16px", borderRadius: 22, fontSize: 15,
                border: "1px solid rgba(143,180,255,0.4)", background: "rgba(255,255,255,0.05)", color: "inherit" }} />
            <button onClick={unlock} disabled={busy || !pw.trim()}
              style={{ padding: "0 18px", borderRadius: 22, border: "none", fontSize: 14, fontWeight: 600, cursor: "pointer",
                background: "radial-gradient(circle at 38% 35%, #ffffff, #9fc0ff)", color: "#0A1120",
                opacity: busy || !pw.trim() ? 0.5 : 1 }}>Unlock</button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, paddingTop: 8 }}>
          <input value={ask} onChange={(e) => setAsk(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(ask)} disabled={busy}
            placeholder="Message Saathi…"
            style={{ flex: 1, padding: "13px 16px", borderRadius: 22, fontSize: 15,
              border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.05)", color: "inherit" }} />
          <button onClick={() => send(ask)} disabled={busy || !ask.trim()}
            style={{ width: 52, borderRadius: 22, border: "none", fontSize: 20, cursor: "pointer",
              background: "radial-gradient(circle at 38% 35%, #ffffff, #9fc0ff)", color: "#0A1120",
              opacity: busy || !ask.trim() ? 0.5 : 1 }}>➤</button>
        </div>
      )}
    </div>
  );
}
