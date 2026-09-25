"use client";
/**
 * Financial Browser controls, embeddable inside the Command Deck (ported from the standalone
 * /finance/browser page so the deck is self-contained). Owner opens a provider, logs in in the
 * embedded browser, enables Saathi Read, then observes read-only portfolio data. No trading.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, StatusBadge, Text, Divider, EmptyState } from "@/components/ui";
import FinancialViewport from "@/components/finance/FinancialViewport";

const PROVIDER_ORDER = ["TMS", "BINANCE", "NEPSE", "PORTFOLIO_TRACKER"];

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    ...opts,
  }).then(async (r) => {
    let body = {};
    try { body = await r.json(); } catch { body = {}; }
    return { ok: r.ok, status: r.status, body };
  });
}

export default function FinancialBrowserPanel({ onPortfolio }) {
  const [providers, setProviders] = useState(null);
  const [runtimes, setRuntimes] = useState([]);
  const [busy, setBusy] = useState("");
  const [obs, setObs] = useState({});

  const refresh = useCallback(async () => {
    const [p, rt] = await Promise.all([
      api("/api/v1/finance/providers"),
      api("/api/v1/finance/browser/runtimes"),
    ]);
    if (p.ok) setProviders(p.body.providers || p.body);
    if (rt.ok) setRuntimes(rt.body.runtimes || []);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const openProvider = async (prov) => {
    setBusy(`open:${prov}`);
    await api("/api/v1/finance/browser/open", { method: "POST", body: JSON.stringify({ provider: prov }) });
    await refresh(); setBusy("");
  };
  const markAuth = async (id) => {
    setBusy(`auth:${id}`);
    await api("/api/v1/finance/browser/mark-authenticated", { method: "POST", body: JSON.stringify({ runtime_id: id }) });
    await refresh(); setBusy("");
  };
  const toggleRead = async (id, on) => {
    setBusy(`read:${id}`);
    await api("/api/v1/finance/browser/saathi-read", { method: "POST", body: JSON.stringify({ runtime_id: id, on }) });
    await refresh(); setBusy("");
  };
  const readPortfolio = async (prov, id) => {
    setBusy(`obs:${id}`);
    const r = await api(`/api/v1/finance/browser/${prov}/observe-portfolio`, { method: "POST", body: JSON.stringify({ runtime_id: id }) });
    setObs((o) => ({ ...o, [id]: r.body }));
    onPortfolio?.(r.body);
    setBusy("");
  };
  const closeRuntime = async (id) => {
    setBusy(`close:${id}`);
    await api("/api/v1/finance/browser/close", { method: "POST", body: JSON.stringify({ runtime_id: id }) });
    setObs((o) => { const n = { ...o }; delete n[id]; return n; });
    await refresh(); setBusy("");
  };

  const provKeys = providers
    ? [...PROVIDER_ORDER.filter((k) => k in providers), ...Object.keys(providers).filter((k) => !PROVIDER_ORDER.includes(k) && k !== "policies" && k !== "components")]
    : [];
  const openRuntimes = runtimes.filter((r) => r.runtime_state !== "CLOSED");

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {provKeys.map((name) => {
          const running = runtimes.find((r) => r.provider === name && r.runtime_state !== "CLOSED");
          return (
            <button key={name} onClick={() => openProvider(name)} disabled={busy === `open:${name}` || !!running}
              style={{ fontFamily: "inherit", fontSize: 11, padding: "6px 10px", borderRadius: 8, cursor: running ? "default" : "pointer",
                border: "1px solid rgba(255,64,64,.25)", background: running ? "rgba(46,226,122,.1)" : "transparent",
                color: running ? "#2ee27a" : "#b7a8ad", fontWeight: 600 }}>
              {busy === `open:${name}` ? "Opening…" : running ? `${name} ●` : `Open ${name}`}
            </button>
          );
        })}
      </div>

      {openRuntimes.length === 0 ? (
        <EmptyState title="No embedded browser open" description="Open a provider above — its site loads inside SaathiOS (no external Chrome). You log in yourself." />
      ) : (
        openRuntimes.map((r) => {
          const authed = r.auth_state === "OWNER_AUTHENTICATED";
          const readOn = r.agent_read === true || r.observation_state === "SAATHI_READ_ON";
          const id = r.runtime_id;
          return (
            <div key={id} style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{r.provider}</span>
                <Badge variant="soft" label={r.runtime_state} />
                <StatusBadge status={readOn ? "success" : "neutral"} label={readOn ? "SAATHI READ ON" : "Read OFF"} />
                <div style={{ flexGrow: 1 }} />
                {!authed && <Button size="sm" onClick={() => markAuth(id)} disabled={busy === `auth:${id}`}>I've logged in</Button>}
                {authed && !readOn && <Button size="sm" onClick={() => toggleRead(id, true)} disabled={busy === `read:${id}`}>Enable Saathi Read</Button>}
                {authed && readOn && (
                  <>
                    <Button size="sm" onClick={() => readPortfolio(r.provider, id)} disabled={busy === `obs:${id}`}>{busy === `obs:${id}` ? "Reading…" : "Read Portfolio"}</Button>
                    <Button size="sm" variant="ghost" onClick={() => toggleRead(id, false)} disabled={busy === `read:${id}`}>Disable</Button>
                  </>
                )}
                <Button size="sm" variant="danger" onClick={() => closeRuntime(id)} disabled={busy === `close:${id}`}>Close</Button>
              </div>
              {r.runtime_state === "OPEN_OWNER_CONTROL" && <FinancialViewport provider={r.provider} runtimeId={id} />}
              {r.runtime_state === "PROVIDER_ACCESS_UNAVAILABLE" && (
                <Text tone="muted" size="xs">Embedded browser could not start{r.launch_error ? `: ${r.launch_error}` : "."}</Text>
              )}
              {obs[id] && (
                <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>
                  {obs[id].available ? `Observed ${obs[id].holding_count} holdings.` : `Observation: ${obs[id].state || "unavailable"}`}
                </Text>
              )}
            </div>
          );
        })
      )}
      <Divider style={{ margin: "8px 0" }} />
      <Text tone="disabled" size="xs">You enter every credential yourself · read-only when Saathi Read is ON · no trades/transfers.</Text>
    </div>
  );
}
