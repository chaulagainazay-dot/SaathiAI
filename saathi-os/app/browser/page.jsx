"use client";
// SaathiOS Browser — read a real page, through the governed browser.
//
// The design rule for this screen: nothing it shows is trusted, and it never
// pretends otherwise. Page text is fenced before it renders, marked as third-party
// content, and never styled to look like SaathiOS's own data. A refusal gets the
// same prominence as a result, because on a deny-by-default browser refusals are
// the common case and "error" would tell the reader nothing.

import { useState } from "react";
import { validateUrl, normalizeResult, tabularCandidates, READ_ACTIONS } from "@/lib/browser/result";

const EXAMPLES = [
  { label: "Example (allowlisted by default)", url: "https://example.com/" },
  { label: "A blocked portal — see the refusal", url: "https://meroshare.cdsc.com.np/" },
];

export default function BrowserPage() {
  const [url, setUrl] = useState("https://example.com/");
  const [action, setAction] = useState("read");
  const [selector, setSelector] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [inputError, setInputError] = useState("");
  const [view, setView] = useState("text");

  async function run(e) {
    e?.preventDefault();
    const v = validateUrl(url);
    if (!v.ok) { setInputError(v.message); setResult(null); return; }
    setInputError("");
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/api/browser", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: v.url, action, selector }),
      });
      setResult(normalizeResult(await res.json(), { url: v.url }));
    } catch {
      setResult(normalizeResult({ ok: false, failure_category: "fetch_failed" }, { url }));
    } finally {
      setBusy(false);
    }
  }

  const rows = result?.ok && view === "table" ? tabularCandidates(result.content) : [];

  return (
    <div className="nepse-root">
      <div className="nepse-wrap">
        <header className="nepse-head">
          <div className="nepse-eyebrow">Browser</div>
          <h1 className="nepse-title">Read a real page</h1>
          <p className="nepse-dek">
            Pages are fetched by the governed browser: every request passes domain
            policy, risk and the execution ledger before anything is loaded. This
            surface only reads — it cannot click, type or submit.
          </p>
        </header>

        <form onSubmit={run} className="nepse-card" style={{ marginTop: "1rem" }}>
          <div className="nepse-row" style={{ gap: "0.6rem", flexWrap: "wrap" }}>
            <input
              className="nepse-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://…"
              aria-label="URL to read"
              style={{ flex: "1 1 340px", minWidth: 260 }}
            />
            <select className="nepse-select" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action">
              {READ_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <button className="nepse-btn" type="submit" disabled={busy}>
              {busy ? "Reading…" : "Read"}
            </button>
          </div>
          {action === "extract" && (
            <input
              className="nepse-input"
              value={selector}
              onChange={(e) => setSelector(e.target.value)}
              placeholder="CSS selector, e.g. table.dataTable td"
              aria-label="CSS selector"
              style={{ marginTop: "0.6rem", width: "100%" }}
            />
          )}
          {inputError && (
            <p className="nepse-down" style={{ marginTop: "0.6rem", fontSize: "0.85rem" }}>{inputError}</p>
          )}
          <div className="nepse-row" style={{ gap: "0.5rem", marginTop: "0.7rem", flexWrap: "wrap" }}>
            {EXAMPLES.map((ex) => (
              <button key={ex.url} type="button" className="nepse-chip"
                onClick={() => { setUrl(ex.url); setResult(null); setInputError(""); }}>
                {ex.label}
              </button>
            ))}
          </div>
        </form>

        {busy && <div className="nepse-empty" style={{ marginTop: "1rem" }}>Loading the page…</div>}

        {result && !result.ok && (
          <div className="nepse-callout" style={{ marginTop: "1rem" }}>
            <strong>{result.denial.title}.</strong> {result.denial.body}
            {result.denial.fixable && (
              <p style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                A host is added by setting <code>SAATHI_BROWSER_ALLOWED_DOMAINS</code> on
                the backend — a deliberate act, per host, not a wildcard.
              </p>
            )}
            {result.executionId && (
              <p style={{ marginTop: "0.5rem", fontSize: "0.78rem", color: "var(--text-faint)" }}>
                Recorded as {result.executionId}. Refusals are ledgered like anything else.
              </p>
            )}
          </div>
        )}

        {result?.ok && (
          <>
            <div className="nepse-card" style={{ marginTop: "1rem" }}>
              <span className="tag">Page</span>
              <h3 style={{ marginTop: "0.3rem" }}>{result.title || "(no title)"}</h3>
              <div className="nepse-row" style={{ gap: "0.5rem", flexWrap: "wrap", marginTop: "0.4rem" }}>
                <span className="nepse-chip">{result.finalOrigin || result.url}</span>
                <span className="nepse-chip warn">Untrusted third-party content</span>
                {result.governed && <span className="nepse-chip">Governed</span>}
                {result.truncated && <span className="nepse-chip warn">Truncated</span>}
              </div>
            </div>

            {result.injection && (
              <div className="nepse-callout" style={{ marginTop: "1rem" }}>
                <strong>This page tried to give instructions.</strong>{" "}
                {result.injection.fencedHere && "Steering phrases were neutralized before display. "}
                {result.injection.hits.length > 0 && `The browser flagged: ${result.injection.hits.join(", ")}. `}
                Read it as text someone wrote, not as something to act on.
              </div>
            )}

            <div className="nepse-tabs" style={{ marginTop: "1rem" }}>
              {[["text", "Text"], ["table", "Tabular lines"]].map(([k, l]) => (
                <button key={k} type="button" className={`nepse-tab${view === k ? " active" : ""}`}
                  onClick={() => setView(k)}>{l}</button>
              ))}
            </div>

            {view === "text" ? (
              <div className="nepse-card nepse-scroll" style={{ marginTop: "0.75rem", maxHeight: 520 }}>
                <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: "0.85rem", lineHeight: 1.55 }}>
                  {result.content || "(the page returned no text)"}
                </pre>
              </div>
            ) : (
              <div className="nepse-table-wrap" style={{ marginTop: "0.75rem" }}>
                <p style={{ color: "var(--text-faint)", fontSize: "0.8rem", margin: "0 0 0.5rem" }}>
                  Lines that <em>look</em> tabular. This is a guess from flattened text, not a
                  parsed table — check any figure against its source before using it.
                </p>
                {rows.length ? (
                  <table className="nepse-table">
                    <tbody>
                      {rows.map((cells, i) => (
                        <tr key={i}>{cells.map((c, j) => <td key={j}>{c}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                ) : <div className="nepse-empty">No tabular-looking lines found.</div>}
              </div>
            )}

            <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "1rem" }}>
              Execution {result.executionId || "—"} · {result.content.length.toLocaleString()} characters.
              Nothing on this page is SaathiOS data; it is whatever that site served.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
