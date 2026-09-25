"use client";
// Scanners — run a built-in scan, or one you saved, across the archive.
//
// THREE OUTCOMES, NOT TWO. A symbol either matched, failed, or could not be
// decided — an RSI that has not been computed is not a failure to match. The
// third count is shown on every result, because a scanner that silently drops
// what it could not read presents part of the exchange as all of it.
//
// Matching happens server-side through the same evaluator a saved strategy uses,
// so a built-in scan and a fork of it can never disagree.

import { useEffect, useMemo, useState } from "react";
import { SCAN_LIBRARY, scanById } from "@/lib/nepse/scanners";
import { describeStrategy } from "@/lib/strategy/conditions";
import { fmtNum } from "@/lib/nepse/format";
import * as store from "@/lib/nepse/store";

function Counts({ counts, complete }) {
  return (
    <div className="nepse-row" style={{ gap: "0.75rem", flexWrap: "wrap", fontSize: "0.8rem" }}>
      <span className="nepse-badge up">{counts.matched} matched</span>
      <span className="nepse-badge neutral">{counts.rejected} did not</span>
      <span className={`nepse-badge ${counts.unknown ? "down" : "neutral"}`}>
        {counts.unknown} undecided
      </span>
      <span style={{ color: "var(--text-faint)" }}>
        of {fmtNum(counts.scanned, 0)} scanned
        {complete ? "" : " — the scan has no answer for the undecided ones"}
      </span>
    </div>
  );
}

export default function ScannersPage() {
  const [selected, setSelected] = useState("oversold");
  const [custom, setCustom] = useState(null);   // a saved strategy record, or null
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ loading: false, error: "" });
  const [saved, setSaved] = useState([]);
  const [note, setNote] = useState("");

  useEffect(() => { setSaved(store.listStrategies()); }, []);

  const active = custom || scanById(selected);
  const description = useMemo(
    () => (active ? describeStrategy(active) : null), [active],
  );

  const run = async () => {
    if (!active) return;
    setState({ loading: true, error: "" });
    setResult(null);
    try {
      const res = custom
        ? await fetch("/api/nepse/scan", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ name: custom.name, root: custom.root, id: custom.id }),
          })
        : await fetch(`/api/nepse/scan?id=${encodeURIComponent(selected)}`, { cache: "no-store" });
      const d = await res.json();
      if (!d?.available) {
        setState({ loading: false, error: d?.reason || "UNAVAILABLE" });
        return;
      }
      setResult(d);
      setState({ loading: false, error: "" });
    } catch {
      setState({ loading: false, error: "UNREACHABLE" });
    }
  };

  const fork = () => {
    const scan = scanById(selected);
    if (!scan) return;
    const rec = store.forkScan(scan);
    setSaved(store.listStrategies());
    setCustom(rec);
    setNote(`Saved as “${rec.name}”. It is yours now — editing it will not change the built-in scan.`);
  };

  const remove = (id) => {
    store.deleteStrategy(id);
    setSaved(store.listStrategies());
    if (custom?.id === id) setCustom(null);
  };

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Scanners</div>
        <h1 className="nepse-title">Screen the archive</h1>
        <p className="nepse-dek">
          Nine prebuilt scans, each an ordinary strategy you can fork and edit.
          Results are counted three ways — matched, rejected, and undecided.
        </p>
      </header>

      <div className="nepse-grid-2" style={{ marginTop: "1.25rem" }}>
        <div className="nepse-card">
          <h3>Built-in scans</h3>
          <select className="nepse-select" style={{ width: "100%", marginTop: "0.5rem" }}
                  aria-label="Choose a scan" value={selected}
                  onChange={(e) => { setSelected(e.target.value); setCustom(null); setResult(null); setNote(""); }}>
            {SCAN_LIBRARY.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {!custom && scanById(selected)?.description && (
            <p style={{ fontSize: "0.82rem", color: "var(--text-dim)", marginTop: "0.5rem" }}>
              {scanById(selected).description}
            </p>
          )}
          <div className="nepse-row" style={{ marginTop: "0.75rem" }}>
            <button className="nepse-btn" type="button" onClick={run} disabled={state.loading}>
              {state.loading ? "Scanning…" : "Run scan"}
            </button>
            <button className="nepse-btn ghost" type="button" onClick={fork} disabled={!!custom}>
              Fork &amp; save
            </button>
          </div>
          {note && <p style={{ fontSize: "0.8rem", color: "var(--accent)", marginTop: "0.5rem" }}>{note}</p>}
        </div>

        <div className="nepse-card">
          <h3>Your saved strategies</h3>
          {saved.length === 0 ? (
            <p style={{ fontSize: "0.84rem", color: "var(--text-faint)", marginTop: "0.5rem" }}>
              None yet. Fork a built-in scan to start from something that already runs.
            </p>
          ) : saved.map((s) => (
            <div key={s.id} className="nepse-row" style={{ marginTop: "0.5rem", justifyContent: "space-between" }}>
              <button type="button" className="nepse-btn ghost"
                      style={{ borderColor: custom?.id === s.id ? "var(--accent)" : undefined }}
                      onClick={() => { setCustom(s); setResult(null); setNote(""); }}>
                {s.name}
              </button>
              <button type="button" className="nepse-btn ghost" onClick={() => remove(s.id)}>Delete</button>
            </div>
          ))}
          {custom && (
            <p style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginTop: "0.75rem" }}>
              Running <strong>{custom.name}</strong>
              {custom.forkedFrom ? ` (forked from ${custom.forkedFrom})` : ""}.{" "}
              <button type="button" className="nepse-btn ghost"
                      onClick={() => { setCustom(null); setResult(null); }}>
                Back to built-ins
              </button>
            </p>
          )}
        </div>
      </div>

      {description && (
        <p className="mono" style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "1rem" }}>
          {description}
        </p>
      )}

      {state.error && (
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          <strong>Scan not run ({state.error}).</strong> No result is shown rather
          than an empty table, which would read as &ldquo;nothing matched&rdquo;.
        </div>
      )}

      {result && (
        <section style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
            {result.strategy || "Result"}
          </h2>
          <Counts counts={result.counts} complete={result.complete} />

          {!result.coverage.isFullUniverse && (
            <p style={{ fontSize: "0.78rem", color: "var(--gold)", marginTop: "0.5rem" }}>
              {result.coverage.universeKind === "LISTED"
                ? `The archive answered for ${result.coverage.archived} of ${result.coverage.requested} listed companies.`
                : result.coverage.universeKind === "TRADED"
                  ? `Scanned the ${result.coverage.archived} companies that traded in the last session, not every listing.`
                  : `Scanned this build's own ${result.coverage.archived}-symbol list — no listing source answered.`}
              {" "}This is a scan of what could be read, not of the exchange.
            </p>
          )}

          <div className="nepse-table-wrap" style={{ marginTop: "0.75rem" }}>
            <table className="nepse-table">
              <thead><tr><th>Symbol</th><th>Sector</th><th className="rt">Sessions behind it</th></tr></thead>
              <tbody>
                {result.matched.length === 0 ? (
                  <tr><td colSpan={3} style={{ color: "var(--text-faint)" }}>
                    Nothing matched. {result.counts.unknown > 0
                      ? `${result.counts.unknown} symbols were undecided, so this is not the same as "no such stock exists".`
                      : "Every scanned symbol was decided and none matched."}
                  </td></tr>
                ) : result.matched.map((m) => (
                  <tr key={m.symbol}>
                    <td className="strong"><a href={`/nepse/stocks/${m.symbol}`}>{m.symbol}</a></td>
                    <td>{m.sector ?? "—"}</td>
                    {/* The shortest reading the decision leaned on. A match on
                        fifty sessions is a weaker statement than one on a thousand. */}
                    <td className="rt num">{m.sessions === null ? "—" : fmtNum(m.sessions, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.unknown.length > 0 && (
            <details style={{ marginTop: "1rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.85rem", color: "var(--text-dim)" }}>
                {result.unknown.length} undecided — why
              </summary>
              <div className="nepse-table-wrap" style={{ marginTop: "0.5rem" }}>
                <table className="nepse-table">
                  <thead><tr><th>Symbol</th><th>Status</th><th>Blocker</th></tr></thead>
                  <tbody>
                    {result.unknown.slice(0, 60).map((u) => (
                      <tr key={u.symbol}>
                        <td className="strong">{u.symbol}</td>
                        <td className="mono" style={{ fontSize: "0.76rem" }}>{u.status}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-dim)" }}>{u.reason ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.unknown.length > 60 && (
                <p style={{ fontSize: "0.76rem", color: "var(--text-faint)" }}>
                  Showing the first 60 of {result.unknown.length}.
                </p>
              )}
            </details>
          )}

          {result.sectorDirectory && result.matched.some((m) => !m.sector) && (
            <p style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
              Sector is blank for{" "}
              {result.matched.filter((m) => !m.sector).length} of {result.matched.length}{" "}
              matches: the sector directory is{" "}
              <span className="mono">{result.sectorDirectory.state}</span> and this
              build could only map {result.sectorDirectory.mapped} symbols from{" "}
              {result.sectorDirectory.source}. A dash there means &ldquo;not looked
              up&rdquo;, not &ldquo;this company has no sector&rdquo;.
            </p>
          )}

          <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "1rem" }}>
            Source <span className="mono">{result.source}</span> · {result.adjustment} ·
            computed {new Date(result.computedAt).toLocaleString()}. Not investment advice.
          </p>
        </section>
      )}
    </>
  );
}
