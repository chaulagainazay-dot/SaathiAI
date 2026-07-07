"use client";
import { useEffect, useRef, useState } from "react";
import { sendChat } from "@/lib/api";

// Mobile-friendly voice: uses the PHONE's built-in speech recognition (Web Speech
// API) for STT and speechSynthesis for TTS — so it works on the phone without
// reaching the Mac's local Whisper. Transcript → Gemini via /agent/chat → spoken reply.
export default function MobileMic() {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const recRef = useRef(null);

  useEffect(() => {
    const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
    if (!SR) return;
    setSupported(true);
    const rec = new SR();
    rec.lang = "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (e) => { const t = e.results[0][0].transcript; setHeard(t); ask(t); };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
  }, []);

  const speak = (msg) => {
    try {
      const synth = window.speechSynthesis;
      if (!synth) return;
      synth.cancel();
      synth.resume();                       // iOS pauses the queue; wake it
      const u = new SpeechSynthesisUtterance(msg);
      u.lang = "en-US"; u.rate = 1.0; u.pitch = 1.0;
      const voices = synth.getVoices();
      const v = voices.find((x) => /en[-_]/i.test(x.lang) && /female|Samantha|Google US/i.test(x.name))
        || voices.find((x) => /en[-_]/i.test(x.lang));
      if (v) u.voice = v;
      synth.speak(u);
    } catch {}
  };

  const ask = async (text) => {
    if (!text) return;
    setBusy(true); setReply("");
    try {
      const r = await sendChat(text);
      const msg = r.reply || "…";
      setReply(msg);
      speak(msg);
    } catch (e) { setReply("Couldn't reach the brain just now."); }
    finally { setBusy(false); }
  };

  const toggle = () => {
    if (!recRef.current) return;
    // iOS Safari only allows speech that starts from a user gesture — prime the
    // synthesizer on this tap so the later (post-fetch) reply is allowed to speak.
    try {
      const synth = window.speechSynthesis;
      if (synth) { synth.getVoices(); synth.resume(); synth.speak(new SpeechSynthesisUtterance("")); }
    } catch {}
    if (listening) { recRef.current.stop(); setListening(false); return; }
    setHeard(""); setReply("");
    try { recRef.current.start(); setListening(true); } catch {}
  };

  if (!supported) return null;

  return (
    <>
      {(heard || reply) && (
        <div style={{ position: "fixed", left: 12, right: 12, bottom: 92, zIndex: 60,
          background: "rgba(16,16,26,0.94)", border: "1px solid rgba(155,107,255,0.35)",
          borderRadius: 14, padding: 12, backdropFilter: "blur(8px)" }}>
          {heard && <div style={{ fontSize: 12.5, opacity: 0.6 }}>🎙 {heard}</div>}
          {reply && <div style={{ fontSize: 13.5, marginTop: 4 }}>{busy ? "…" : reply}</div>}
        </div>
      )}
      <button onClick={toggle} aria-label="Talk to Saathi"
        style={{ position: "fixed", right: 18, bottom: 24, zIndex: 61, width: 60, height: 60,
          borderRadius: "50%", border: "none", cursor: "pointer", fontSize: 24,
          color: "#fff", boxShadow: "0 6px 20px rgba(0,0,0,0.4)",
          background: listening ? "#FF5A5A" : busy ? "#E8B84B" : "#9B6BFF",
          animation: listening ? "pulse 1.2s infinite" : "none" }}>
        {busy ? "…" : listening ? "◼" : "🎤"}
      </button>
      <style>{`@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,90,90,.5)}70%{box-shadow:0 0 0 14px rgba(255,90,90,0)}100%{box-shadow:0 0 0 0 rgba(255,90,90,0)}}`}</style>
    </>
  );
}
