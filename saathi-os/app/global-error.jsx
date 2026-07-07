"use client";

export default function GlobalError({ error, reset }) {
  return (
    <html>
      <body style={{ background: "#0a0a0f", color: "#F4F6FB", margin: 0, fontFamily: "system-ui" }}>
        <div style={{ padding: "40px 20px", maxWidth: 680, margin: "40px auto" }}>
          <div style={{ fontSize: 20, fontWeight: 600 }}>SaathiOS failed to load</div>
          <div style={{ fontSize: 13, opacity: 0.6, margin: "8px 0 16px" }}>
            Actual error below — share this so it can be fixed.
          </div>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#FF9B9B", fontSize: 13,
            background: "rgba(255,90,90,0.08)", padding: 14, borderRadius: 10 }}>
            {String(error?.message || error) || "Unknown error"}
          </pre>
          {error?.stack && (
            <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", opacity: 0.45, fontSize: 10.5,
              marginTop: 10, maxHeight: 240, overflow: "auto" }}>{error.stack.slice(0, 1000)}</pre>
          )}
          <button onClick={() => reset()} style={{ marginTop: 16, padding: "10px 20px", borderRadius: 10,
            border: "none", cursor: "pointer", fontWeight: 600, color: "#fff", background: "#9B6BFF" }}>
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
