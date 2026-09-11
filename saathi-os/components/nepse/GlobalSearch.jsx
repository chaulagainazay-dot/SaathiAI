"use client";
// Global instrument search, present on every NEPSE page.
//
// Ranking lives in lib/nepse/search.js and is the whole point: on an exchange
// carrying both NABIL and NABILP, a plain substring filter puts them in whatever
// order the array happened to be in. This component only renders the ranking and
// moves the selection.

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { STOCKS } from "@/lib/nepse/data";
import { MATCH, search } from "@/lib/nepse/search";
import { UNCLASSIFIED } from "@/lib/nepse/market";
import { useMarketAggregates } from "@/lib/nepse/use-market";

const HINT = {
  [MATCH.EXACT_SYMBOL]: "exact symbol",
  [MATCH.SYMBOL_PREFIX]: "symbol",
  [MATCH.NAME_PREFIX]: "company",
  [MATCH.SYMBOL_CONTAINS]: "symbol contains",
  [MATCH.NAME_CONTAINS]: "company contains",
  [MATCH.SECTOR]: "sector",
};

export default function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);

  // The built-in list carries 24 companies WITH names; the market route answers
  // for the whole measured universe but only knows symbol and sector. Searching
  // either one alone is wrong in a different way — the first cannot find most of
  // the exchange, the second cannot match a company name — so they are merged,
  // names winning where both have an entry.
  const { data } = useMarketAggregates();
  const universe = useMemo(() => {
    const byS = new Map();
    for (const r of data?.rows || []) byS.set(r.symbol, { symbol: r.symbol, sector: r.sector });
    for (const s of STOCKS) byS.set(s.symbol, { ...byS.get(s.symbol), ...s });
    return [...byS.values()];
  }, [data]);

  const hits = useMemo(() => search(universe, q, { limit: 8 }), [universe, q]);

  useEffect(() => { setCursor(0); }, [q]);

  // "/" focuses the box, the way every screener on the internet behaves — but
  // never while the user is already typing into some other field.
  useEffect(() => {
    const onKey = (e) => {
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault();
        boxRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onClick = (e) => {
      if (!e.target.closest?.("[data-nepse-search]")) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const go = (symbol) => {
    setOpen(false);
    setQ("");
    router.push(`/nepse/stocks/${symbol}`);
  };

  const onKeyDown = (e) => {
    if (!hits.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => (c + 1) % hits.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => (c - 1 + hits.length) % hits.length); }
    else if (e.key === "Enter") { e.preventDefault(); go(hits[cursor].symbol); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  return (
    <div data-nepse-search style={{ position: "relative", marginLeft: "auto" }}>
      <input
        ref={boxRef}
        className="nepse-input"
        style={{ width: "13rem" }}
        type="search"
        value={q}
        placeholder="Search symbol or company  /"
        aria-label="Search instruments"
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls="nepse-search-results"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && q.trim() !== "" && (
        <div id="nepse-search-results" role="listbox"
             style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 40,
                      width: "22rem", maxWidth: "80vw", background: "var(--surface)",
                      border: "1px solid var(--border)", borderRadius: 8,
                      boxShadow: "var(--shadow)", overflow: "hidden" }}>
          {hits.length === 0 ? (
            // Says which universe was searched. "No results" on its own reads as
            // "this stock does not exist", which is a claim about the exchange.
            <div style={{ padding: "0.7rem 0.8rem", fontSize: "0.82rem", color: "var(--text-faint)" }}>
              Nothing among the {universe.length} instrument{universe.length === 1 ? "" : "s"} this
              build can see matches “{q}”.
            </div>
          ) : hits.map((h, i) => (
            <button key={h.symbol} type="button" role="option" aria-selected={i === cursor}
                    onMouseEnter={() => setCursor(i)} onClick={() => go(h.symbol)}
                    style={{ display: "flex", gap: "0.6rem", alignItems: "baseline", width: "100%",
                             textAlign: "left", padding: "0.5rem 0.8rem", border: 0, cursor: "pointer",
                             background: i === cursor ? "var(--surface-2)" : "transparent",
                             color: "var(--text)", font: "inherit" }}>
              <span className="mono" style={{ fontWeight: 600 }}>{h.symbol}</span>
              <span style={{ flex: 1, fontSize: "0.82rem", color: "var(--text-dim)",
                             overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {/* "Unclassified" is the aggregate's grouping label, not a
                    description of the company. Printed here it reads as a fact
                    about the business rather than a gap in our directory. */}
                {h.name || h.company || (h.sector === UNCLASSIFIED ? "" : h.sector) || ""}
              </span>
              <span style={{ fontSize: "0.68rem", color: "var(--text-faint)" }}>{HINT[h.match]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
