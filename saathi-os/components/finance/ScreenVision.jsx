"use client";
/**
 * Screen Analysis — capture the current screen and ask Saathi about it. The frame is sent to
 * Gemini Vision and answered in-place; nothing is stored. Same brain as Ask Saathi chat.
 * Research/observation only.
 */
import { useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

export default function ScreenVision() {
  const [shot, setShot] = useState(null);      // data URL
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const imgRef = useRef(null);

  const capture = async () => {
    setErr(""); setAnswer(null); setBusy("capture");
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 1 }, audio: false });
      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();
      await new Promise((r) => setTimeout(r, 350));
      const w = video.videoWidth || 1280, h = video.videoHeight || 800;
      const scale = Math.min(1, 1600 / w);
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      stream.getTracks().forEach((t) => t.stop());
      setShot(canvas.toDataURL("image/jpeg", 0.7));
    } catch (e) {
      setErr("Screen capture cancelled or blocked.");
    }
    setBusy("");
  };

  const analyze = async () => {
    if (!shot) { setErr("Capture the screen first."); return; }
    setBusy("analyze"); setErr(""); setAnswer(null);
    try {
      const r = await afetch(`${API_BASE}/api/v1/vision/analyze`, {
        method: "POST", cache: "no-store", headers: { "content-type": "application/json" },
        body: JSON.stringify({ image_b64: shot, question: q.trim() }),
      });
      const b = await r.json().catch(() => ({}));
      if (b?.available) setAnswer(b);
      else setErr(b?.note || b?.error || "Vision unavailable.");
    } catch {
      setErr("Request failed.");
    }
    setBusy("");
  };

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <Button size="sm" onClick={capture} disabled={busy === "capture"}>{busy === "capture" ? "Capturing…" : "📷 Capture screen"}</Button>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") analyze(); }}
          placeholder="Ask about the screen (optional)…"
          style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, flexGrow: 1, minWidth: 200, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <Button size="sm" variant="secondary" onClick={analyze} disabled={busy === "analyze" || !shot}>{busy === "analyze" ? "Reading…" : "Ask Saathi"}</Button>
      </div>

      {err && <Text tone="muted" size="xs" style={{ display: "block", marginBottom: 10 }}>{err}</Text>}
      {!shot && !err && <EmptyState title="Let Saathi see your screen" description="Capture the screen, optionally type a question, then Ask Saathi. Uses Gemini Vision · research only." />}

      {shot && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 14, alignItems: "start" }}>
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>CAPTURED</div>
            <img ref={imgRef} src={shot} alt="screen capture" style={{ width: "100%", borderRadius: 8, border: "1px solid rgba(255,64,64,.2)" }} />
          </div>
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>SAATHI READS</div>
            {busy === "analyze" && <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Spinner size={14} /><Text tone="muted" size="sm">Reading the screen…</Text></div>}
            {answer && (
              <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "#dccfd3" }}>{answer.answer}</div>
                <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge variant="soft" label={answer.provider} />
                  <Text tone="disabled" size="xs">{answer.note}</Text>
                </div>
              </div>
            )}
            {!answer && busy !== "analyze" && <Text tone="muted" size="sm">Type a question (or leave blank) and press Ask Saathi.</Text>}
          </div>
        </div>
      )}
    </div>
  );
}
