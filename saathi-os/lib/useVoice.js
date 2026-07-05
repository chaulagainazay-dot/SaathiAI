"use client";
import { useRef, useState } from "react";
import { sendVoice } from "./api";

// Push-to-talk hook (ported from the old Baadar voice UI): record mic → send to
// /api/v1/voice/command → returns { transcript, reply } and plays the TTS reply.
export function useVoice(onTurn) {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const recRef = useRef(null);
  const chunksRef = useRef([]);

  const start = async () => {
    if (recording || busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size < 800) { setBusy(false); return; }   // too short / silence
        setBusy(true);
        try {
          const r = await sendVoice(blob);
          onTurn?.(r.transcript || "", r.reply || "…");
          if (r.reply_audio_b64) {
            const a = new Audio(`data:${r.reply_audio_mime || "audio/wav"};base64,${r.reply_audio_b64}`);
            a.play().catch(() => {});
          }
        } catch {
          onTurn?.("", "Sorry — voice didn't reach my brain just now.");
        } finally { setBusy(false); }
      };
      recRef.current = rec; rec.start(); setRecording(true);
    } catch {
      onTurn?.("", "Microphone permission is needed to talk.");
    }
  };
  const stop = () => {
    if (recRef.current && recording) { recRef.current.stop(); setRecording(false); }
  };
  return { recording, busy, start, stop };
}
