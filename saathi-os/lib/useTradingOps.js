"use client";

import { useCallback, useEffect, useState } from "react";
import { plat, getToken } from "@/lib/platform-client";

/**
 * Fetch the canonical trading-operations snapshot.
 *
 * ONE request to ONE route. The five health producers are never called from
 * React, and no subsystem authority is reachable from the browser — the whole
 * point of the backend chain is that health is decided in one place, and a
 * frontend that assembled it from parts would quietly become a second one.
 *
 * The refresh interval is deliberately slow. Collection is already coalesced
 * server-side, health is not a millisecond signal, and freshness is carried in
 * the payload — so polling harder would buy nothing an operator can use.
 */
export const TRADING_OPS_REFRESH_MS = 60_000;

export function useTradingOps({ refreshMs = TRADING_OPS_REFRESH_MS } = {}) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal) => {
    const token = getToken();
    if (!token) {
      // No operator session: report nothing rather than an empty green panel.
      setStatus(null);
      setError("NOT_SIGNED_IN");
      setLoading(false);
      return;
    }
    try {
      const data = await plat("/tg/operations/trading-ops", { token, signal });
      setStatus(data || null);
      setError(null);
    } catch (e) {
      // A failed fetch leaves `status` null, which the view renders as UNKNOWN.
      // It must never leave the previous snapshot on screen looking current.
      setStatus(null);
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    const id = setInterval(() => load(ac.signal), refreshMs);
    return () => {
      ac.abort();
      clearInterval(id);
    };
  }, [load, refreshMs]);

  return { status, error, loading, reload: load };
}
