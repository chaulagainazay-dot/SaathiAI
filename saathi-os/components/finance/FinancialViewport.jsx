"use client";
/**
 * Embedded Financial Browser viewport (OWNER_VISUAL + OWNER_INPUT).
 * Polls the owner-only screencast endpoint for JPEG frames and forwards the owner's own
 * mouse/keyboard/scroll/navigation to the SAME provider runtime. Frames are for the owner's
 * eyes — never sent to any model. During OWNER_PRIVATE_INPUT (login/OTP/…) a banner shows and
 * nothing is persisted or observed. This is not an agent surface.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, StatusBadge, Text } from "@/components/ui";

const STREAM_MS = 500;          // ~2 FPS when active (adaptive; conservative for M2/8GB)
const PRIVATE_MS = 800;         // slower cadence on sensitive pages
const MOVE_THROTTLE_MS = 110;

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    ...opts,
  }).then(async (r) => {
    let body = {}; try { body = await r.json(); } catch {}
    return { ok: r.ok, status: r.status, body };
  });
}

export default function FinancialViewport({ provider, runtimeId, onClose }) {
  const [active, setActive] = useState(false);
  const [vpState, setVpState] = useState("OPEN");
  const [privateInput, setPrivateInput] = useState(false);
  const [err, setErr] = useState("");
  const boxRef = useRef(null);
  const imgRef = useRef(null);        // frames written straight to the <img> — no per-frame re-render
  const pollRef = useRef(null);
  const lastMove = useRef(0);
  const aliveRef = useRef(false);
  const activeRef = useRef(false);       // mirrors `active` for the unmount-only cleanup
  const lastB64 = useRef(null);
  const base = `/api/v1/finance/browser/${provider}/viewport`;

  const stopServer = useCallback(() => {
    try {
      fetch(`${API_BASE}${base}/stop`, {
        method: "POST", credentials: "include", keepalive: true,
        headers: { "content-type": "application/json" }, body: "{}",
      });
    } catch {}
  }, [base]);
  const stopServerRef = useRef(stopServer);
  stopServerRef.current = stopServer;

  const stop = useCallback(async () => {
    aliveRef.current = false; activeRef.current = false;
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null; }
    await api(`${base}/stop`, { method: "POST", body: "{}" });
    setActive(false); setVpState("CLOSED");
    onClose?.();
  }, [base, onClose]);

  const poll = useCallback(async () => {
    if (!aliveRef.current) return;
    const r = await api(`${base}/frame`);
    if (!aliveRef.current) return;
    if (r.ok && r.body?.frame_b64) {
      if (r.body.frame_b64 !== lastB64.current) {     // idle suppression — only swap on change
        lastB64.current = r.body.frame_b64;
        if (imgRef.current) imgRef.current.src = `data:image/jpeg;base64,${r.body.frame_b64}`;
      }
      const ns = r.body.state || "STREAMING";
      setVpState((s) => (s === ns ? s : ns));
      setPrivateInput((p) => (p === !!r.body.private_input ? p : !!r.body.private_input));
      if (err) setErr("");
    } else if (r.status === 409) {
      setErr(r.body?.state || "BROWSER_NOT_OPEN"); aliveRef.current = false; setActive(false); return;
    }
    const delay = r.body?.private_input ? PRIVATE_MS : STREAM_MS;
    pollRef.current = setTimeout(poll, delay);
  }, [base, err]);

  const start = useCallback(async () => {
    setErr("");
    const r = await api(`${base}/start`, { method: "POST", body: JSON.stringify({ runtime_id: runtimeId }) });
    if (!r.ok) { setErr(r.body?.state || r.body?.error || "start failed"); return; }
    setActive(true); setVpState(r.body?.state || "STREAMING");
    aliveRef.current = true; activeRef.current = true;
    poll();
  }, [base, runtimeId, poll]);

  // Auto-start on mount so the embedded browser streams immediately (no extra owner click) —
  // this is the "browser inside SaathiOS" experience, not a separate window to open.
  const startRef = useRef(start);
  startRef.current = start;
  useEffect(() => { startRef.current(); }, []);

  // Unmount ONLY (deps []): stop local polling AND tell the backend to stop (free CPU).
  // Must not depend on `active` — a re-run on activation would kill the poll loop.
  useEffect(() => () => {
    aliveRef.current = false;
    if (pollRef.current) clearTimeout(pollRef.current);
    if (activeRef.current) stopServerRef.current();
  }, []);

  const norm = (e) => {
    const el = boxRef.current; if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      nx: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      ny: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    };
  };
  const sendInput = (ev) => { api(`${base}/input`, { method: "POST", body: JSON.stringify(ev) }); };

  const onMove = (e) => {
    const now = Date.now(); if (now - lastMove.current < MOVE_THROTTLE_MS) return; lastMove.current = now;
    const n = norm(e); if (n) sendInput({ type: "mousemove", ...n });
  };
  const onDown = (e) => { const n = norm(e); if (n) sendInput({ type: "mousedown", ...n }); };
  const onUp = (e) => { const n = norm(e); if (n) sendInput({ type: "mouseup", ...n }); };
  const onWheel = (e) => { const n = norm(e); if (n) sendInput({ type: "wheel", ...n, dx: e.deltaX, dy: e.deltaY }); };
  const onKeyDown = (e) => {
    e.preventDefault();
    sendInput({ type: "keydown", key: e.key, text: e.key.length === 1 ? e.key : undefined });
  };
  const onKeyUp = (e) => { e.preventDefault(); sendInput({ type: "keyup", key: e.key }); };

  if (!active) {
    return (
      <div style={{ padding: 16, border: "1px dashed var(--border)", borderRadius: 10, textAlign: "center" }}>
        <Text tone="muted" size="sm" style={{ display: "block", marginBottom: 10 }}>
          {err ? "Could not connect the embedded browser." : "Connecting the embedded browser…"}
        </Text>
        <Button onClick={start}>{err ? "Retry" : "Connect"}</Button>
        {err && <Text tone="muted" size="xs" style={{ display: "block", marginTop: 8 }}>{err}</Text>}
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
        <Button size="sm" variant="ghost" onClick={() => api(`${base}/navigate`, { method: "POST", body: JSON.stringify({ action: "back" }) })}>← Back</Button>
        <Button size="sm" variant="ghost" onClick={() => api(`${base}/navigate`, { method: "POST", body: JSON.stringify({ action: "forward" }) })}>Forward →</Button>
        <Button size="sm" variant="ghost" onClick={() => api(`${base}/navigate`, { method: "POST", body: JSON.stringify({ action: "reload" }) })}>⟳ Reload</Button>
        <StatusBadge status={privateInput ? "warning" : "success"} label={privateInput ? "PRIVATE INPUT — observation paused" : vpState} />
        <div style={{ flex: 1 }} />
        <Button size="sm" variant="danger" onClick={stop}>Close viewport</Button>
      </div>

      {privateInput && (
        <div style={{ padding: "6px 10px", marginBottom: 6, borderRadius: 8, fontSize: 12,
          background: "var(--status-warning-soft, rgba(230,160,60,0.12))", color: "var(--status-warning)" }}>
          Sensitive page — you type directly; SaathiOS records nothing here (no frames/keys stored, no observation).
        </div>
      )}

      <div
        ref={boxRef}
        tabIndex={0}
        onMouseMove={onMove} onMouseDown={onDown} onMouseUp={onUp} onWheel={onWheel}
        onKeyDown={onKeyDown} onKeyUp={onKeyUp}
        style={{ position: "relative", width: "100%", aspectRatio: "16 / 10", background: "#0b0d10",
          borderRadius: 10, overflow: "hidden", outline: "none", cursor: "default",
          border: privateInput ? "2px solid var(--status-warning)" : "1px solid var(--border)" }}
      >
        <img ref={imgRef} alt="" draggable={false}
          style={{ width: "100%", height: "100%", objectFit: "contain", userSelect: "none",
                   display: "block", background: "#0b0d10" }} />
      </div>
      {err && <Text tone="muted" size="xs" style={{ display: "block", marginTop: 6 }}>{err}</Text>}
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>
        You control this window. Saathi reads only approved data when Saathi Read is ON — never the raw page or your keystrokes.
      </Text>
    </div>
  );
}
