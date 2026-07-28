"use client";
import { useCallback, useEffect, useState } from "react";
import { getToken, plat, PLATFORM_CONTEXT_EVENT } from "./platform-client.js";

export const IELTS_NOTICE = {
  scoring: "Practice estimates only — never official IELTS scores.",
  availability: "Availability uses labelled local fixtures, not live test-center data.",
  payment: "Manual verification only — no payment settlement is performed.",
};

export async function ielts(path, { method = "GET", body, token, signal } = {}) {
  return plat(`/ielts${path}`, { method, body, token: token || getToken(), signal });
}

export const ieltsActions = {
  profile: (body, token) => ielts("/profile", { method: "POST", body, token }),
  goal: (body, token) => ielts("/goals", { method: "POST", body, token }),
  practice: (body, token) => ielts("/practice", { method: "POST", body, token }),
  alert: (body, token) => ielts("/alerts", { method: "POST", body, token }),
  evaluateAlerts: (token) => ielts("/alerts/evaluate", { method: "POST", token }),
  payment: (body, token) => ielts("/payments", { method: "POST", body, token }),
  reviewPayment: (id, body, token) => ielts(`/payments/${encodeURIComponent(id)}/review`, { method: "POST", body, token }),
};

const EMPTY = { dashboard: null, records: [], evidence: [], permissions: [], userId: "" };

export function useIELTSData({ allOwners = false } = {}) {
  const [token, setToken] = useState("");
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async (explicitToken) => {
    const active = explicitToken ?? getToken();
    setToken(active);
    if (!active) {
      setData(EMPTY); setLoading(false); setError(null); return;
    }
    setLoading(true); setError(null);
    try {
      const suffix = allOwners ? "?all_owners=true" : "";
      const [me, dashboard, records, evidence] = await Promise.all([
        plat("/me", { token: active }),
        ielts("/dashboard", { token: active }),
        ielts(`/records${suffix}`, { token: active }),
        ielts(`/evidence${suffix}`, { token: active }),
      ]);
      setData({
        dashboard: dashboard.dashboard || null,
        records: records.records || [],
        evidence: evidence.evidence || [],
        permissions: me.permissions || [],
        userId: me.user?.user_id || "",
      });
    } catch (e) {
      setData(EMPTY);
      setError({ status: e?.status || 0, message: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  }, [allOwners]);

  useEffect(() => {
    refresh();
    const onContext = (event) => {
      setData(EMPTY); setLoading(true);
      refresh(event?.detail?.token ?? getToken());
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
  }, [refresh]);

  return { token, loading, error, refresh, ...data };
}
