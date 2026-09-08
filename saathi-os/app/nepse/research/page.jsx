"use client";
// US7 — Research. Live web search, scoped to the market.
//
// Everything on this page came off the open web. It is fenced before it renders,
// labelled as untrusted, and deliberately styled apart from SaathiOS's own
// figures: a search snippet that mentions a price is evidence that a page exists,
// not a price. The page says so rather than trusting the reader to remember.

import { useState } from "react";
import { symbolQuery } from "@/lib/web/wigolo";

const PRESETS = [
  { label: "NEPSE today", q: "NEPSE market today gainers losers turnover" },
  { label: "Dividend news", q: "NEPSE dividend announcement book closure 2082/83" },
  { label: "IPO pipeline", q: "NEPSE IPO opening date issue manager Nepal" },
  { label: "Regulation", q: "SEBON NEPSE circular new rule" },
];

export default function ResearchPage() {
  const [query, setQuery] = useState("NEPSE market today gainers losers turnover");
  const [symbol, setSymbol] = useState("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function run(q) {
    const text = String(q ?? query).trim();
    if (!text) return;
    setBusy(true); setData(null); setError(null);
    try {
      const res = await fetch("/api/web/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: text, maxResults: 8 }),
      });
      const d = await res.json();
      if (d?.available) setData(d);
      else setError({ reason: d?.reason || "UNAVAILABLE", message: d?.message || "" });
    } catch {
      setError({ reason: "UNREACHABLE", message: "The search route did not answer." });
    } finally {
      setBusy(false);
    }
  }

  function searchSymbol(e) {
    e.preventDefault();
    const q = symbolQuery(symbol, { extra: "news" });
    if (!q) { setError({ reason: "BAD_SYMBOL", message: "That is not a NEPSE symbol." }); return; }
    setQuery(q);
    run(q);
  }

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Research</div>
        <h1 className="nepse-title">Search the web</h1>
        <p className="nepse-dek">
          Runs on a local search engine on this machine — no API key, and no query
          leaves for a search vendor&apos;s account. Results are third-party pages:
          useful context, never a price and never a reason a stock moved.
        </p>
      </header>

      <form onSubmit={(e) => { e.preventDefault(); run(); }} className="nepse-card" style={{ marginTop: "1rem" }}>
        <div className="nepse-row" style={{ gap: "0.6rem" }}>
          <input className="nepse-input" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the web" aria-label="Search query"
            style={{ flex: "1 1 380px", minWidth: 240 }} />
          <button className="nepse-btn" type="submit" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
        </div>
        <div className="nepse-row" style={{ gap: "0.4rem", marginTop: "0.7rem" }}>
          {PRESETS.map((p) => (
            <button key={p.label} type="button" className="nepse-chip"
              onClick={() => { setQuery(p.q); run(p.q); }}>{p.label}</button>
          ))}
        </div>
      </form>

      <form onSubmit={searchSymbol} className="nepse-card" style={{ marginTop: "0.75rem" }}>
        <span className="tag">Context for one symbol</span>
        <div className="nepse-row" style={{ gap: "0.6rem", marginTop: "0.5rem" }}>
          <input className="nepse-input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="NABIL" aria-label="Symbol" style={{ maxWidth: 160 }} />
          <button className="nepse-btn ghost" type="submit" disabled={busy}>Find news</button>
        </div>
      </form>

      {busy && <div className="nepse-empty" style={{ marginTop: "1rem" }}>Searching the web…</div>}

      {error && (
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          <strong>No results ({error.reason}).</strong>{" "}
          {error.message || "Nothing is shown rather than an empty list, which would read as a web where nothing was written."}
          {error.reason === "DAEMON_UNREACHABLE" && (
            <p style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
              The local search engine is a separate program. Start it with{" "}
              <code className="num">npx wigolo serve --port 3333</code>.
            </p>
          )}
        </div>
      )}

      {data && (
        <>
          <div className="nepse-row" style={{ justifyContent: "space-between", margin: "1.25rem 0 0.6rem" }}>
            <h3 style={{ fontSize: "1rem" }}>{data.results.length} results</h3>
            <span style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
              {data.enginesUsed.join(" + ") || "no engine named"} · {data.tookMs}ms
            </span>
          </div>

          {data.injectionFlagged > 0 && (
            <div className="nepse-callout" style={{ marginBottom: "0.75rem" }}>
              <strong>{data.injectionFlagged} result{data.injectionFlagged === 1 ? "" : "s"} tried to give instructions.</strong>{" "}
              Steering phrases were neutralized before display. Read them as text someone wrote, not as something to act on.
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {data.results.map((r) => (
              <div key={r.url} className="nepse-card" style={{ padding: "0.85rem 1rem" }}>
                <div className="nepse-row" style={{ justifyContent: "space-between", gap: "0.5rem" }}>
                  <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600 }}>{r.title || r.url}</a>
                  {r.evidence?.final !== null && r.evidence?.final !== undefined && (
                    <span className="nepse-badge neutral" title={r.evidence.explanation || ""}>
                      {r.evidence.final.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="num" style={{ color: "var(--text-faint)", fontSize: "0.74rem", marginTop: 2 }}>{r.host}</div>
                {r.snippet && <p style={{ color: "var(--text-dim)", fontSize: "0.88rem", margin: "0.4rem 0 0" }}>{r.snippet}</p>}
                {r.injectionFlagged && <span className="nepse-badge" style={{ marginTop: "0.4rem", background: "var(--gold-soft)", color: "var(--gold)" }}>Contained steering text</span>}
              </div>
            ))}
          </div>

          <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "1rem" }}>
            Source: {data.source.label} · {data.source.license} · runs as a separate
            local program, not part of SaathiOS. Results are {data.source.classification.toLowerCase().replace(/_/g, " ")}.
          </p>
        </>
      )}
    </>
  );
}
