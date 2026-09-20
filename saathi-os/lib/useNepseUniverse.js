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
        const r = await afetch(`${API_BASE}/api/v1/market/free/nepse`, { cache: "no-store" });
        const b = await r.json().catch(() => ({}));
        if (alive && b?.available && Array.isArray(b.rows) && b.rows.length) {
          const rows = b.rows.map((q) => {
            const s = getStock(q.symbol) || {};
            return {
              symbol: q.symbol, name: s.name || q.symbol, sector: s.sector || "—",
              ltp: q.ltp, prevClose: q.prev_close ?? s.prevClose,
              high: q.high, low: q.low, volume: q.volume, percentChange: q.percent_change,
              high52: s.high52 ?? null, low52: s.low52 ?? null,
              eps: s.eps ?? null, bookValue: s.bookValue ?? null, paidUp: s.paidUp ?? null,
              rsi: s.rsi ?? null, pe: s.pe ?? null, pb: s.pb ?? null, marketCap: s.marketCap ?? null,
            };
          });
          setState({ rows, source: b.source || "free public source", live: true, loading: false, count: b.count || rows.length, stale: b.stale });
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
