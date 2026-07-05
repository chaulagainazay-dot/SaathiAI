"use client";
import { useState, useRef, useEffect } from "react";
import { saathiExamples } from "@/lib/data";
import { Eyebrow } from "@/components/ui";
import { sendChat } from "@/lib/api";

export default function MobileSaathi() {
  const [chat, setChat] = useState([]);   // {role:"you"|"saathi", text}
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, busy]);

  const send = async (text) => {
    text = (text || "").trim();
    if (!text || busy) return;
    setChat((c) => [...c, { role: "you", text }]); setAsk(""); setBusy(true);
    try {
      const r = await sendChat(text, "mobile");
      setChat((c) => [...c, { role: "saathi", text: r.reply || "…" }]);
    } catch (e) {
      setChat((c) => [...c, { role: "saathi",
        text: String(e).includes("unauthorized")
          ? "Please log in on the dashboard first, then chat here."
          : "Sorry — I couldn't reach my brain just now." }]);
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
            {(saathiExamples || []).map((ex) => (
              <button key={ex} onClick={() => send(ex)}
                style={{ textAlign: "left", padding: "13px 15px", borderRadius: 14, cursor: "pointer",
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  color: "var(--color-ink-200)", fontSize: 14 }}>
                “{ex}”
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

      {/* input */}
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
    </div>
  );
}
