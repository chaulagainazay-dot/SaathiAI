"use client";
// Full NEPSE universe from the free public source (/api/v1/market/free/nepse), enriched with
// the built-in reference fundamentals where a symbol matches. Falls back to the 24-symbol
// reference set when the free source is unreachable. No API key.
import { useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { STOCKS, getStock } from "@/lib/nepse/data";

export function useNepseUniverse() {
  const [state, setState] = useState({ rows: STOCKS, source: "reference set", live: false, loading: true, count: STOCKS.length });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [mr, rr] = await Promise.all([
          afetch(`${API_BASE}/api/v1/market/free/nepse`, { cache: "no-store" }),
          afetch(`${API_BASE}/api/v1/market/free/ranges?start=1`, { cache: "no-store" }),
        ]);
        const b = await mr.json().catch(() => ({}));
        const rj = await rr.json().catch(() => ({}));
        const ranges = (rj && rj.ranges) || {};
        if (alive && b?.available && Array.isArray(b.rows) && b.rows.length) {
          const rows = b.rows.map((q) => {
            const s = getStock(q.symbol) || {};
            const rg = ranges[q.symbol] || {};
            return {
              symbol: q.symbol, name: s.name || q.symbol, sector: s.sector || "—",
              ltp: q.ltp, prevClose: q.prev_close ?? s.prevClose,
              high: q.high, low: q.low, volume: q.volume, percentChange: q.percent_change,
              high52: rg.high ?? s.high52 ?? null, low52: rg.low ?? s.low52 ?? null,
              eps: s.eps ?? null, bookValue: s.bookValue ?? null, paidUp: s.paidUp ?? null,
              rsi: s.rsi ?? null, pe: s.pe ?? null, pb: s.pb ?? null, marketCap: s.marketCap ?? null,
            };
          });
          setState({ rows, source: b.source || "free public source", live: true, loading: false, count: b.count || rows.length, stale: b.stale, rangesFilled: Object.keys(ranges).length });
        } else if (alive) {
          setState((st) => ({ ...st, loading: false }));
        }
      } catch {
        if (alive) setState((st) => ({ ...st, loading: false }));
      }
    })();
    return () => { alive = false; };
  }, []);

  return state;
}
