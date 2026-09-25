"use client";
import { useEffect } from "react";

export default function Error({ error, reset }) {
  useEffect(() => { try { console.error("SaathiOS page error:", error); } catch {} }, [error]);
  return (
    <div style={{ padding: "40px 20px", maxWidth: 680, margin: "40px auto", fontFamily: "system-ui" }}>
      <div style={{ fontSize: 20, fontWeight: 600, color: "#F4F6FB" }}>This page hit an error</div>
      <div style={{ fontSize: 13, opacity: 0.6, margin: "8px 0 16px" }}>
        The rest of SaathiOS is fine — this screen shows the actual message so it can be fixed.
      </div>
      <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#FF9B9B", fontSize: 13,
        background: "rgba(255,90,90,0.08)", padding: 14, borderRadius: 10 }}>
        {String(error?.message || error) || "Unknown error"}
      </pre>
      {error?.stack && (
        <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", opacity: 0.45, fontSize: 10.5,
          marginTop: 10, maxHeight: 220, overflow: "auto" }}>{error.stack.slice(0, 900)}</pre>
      )}
      <button onClick={() => reset()} style={{ marginTop: 16, padding: "10px 20px", borderRadius: 10,
        border: "none", cursor: "pointer", fontWeight: 600, color: "#fff", background: "var(--accent)" }}>
        Retry
      </button>
    </div>
  );
}
