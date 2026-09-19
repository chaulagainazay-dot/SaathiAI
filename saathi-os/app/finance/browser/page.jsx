"use client";
/**
 * Canonical Financial Browser — owner-controlled provider browser surface.
 * The owner launches a provider site, logs in themselves (SaathiOS never enters
 * credentials/OTP), and explicitly enables "Saathi Read" to permit deterministic
 * read-only portfolio observation through the certified Observation Bridge.
 * No trading / withdrawal / transfer / order controls exist here.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import {
  Panel, Card, Button, Badge, StatusBadge, Heading, Text, Divider, Spinner,
  EmptyState, BlockedState, ErrorState, Pill, Eyebrow,
} from "@/components/ui";
import FinancialViewport from "@/components/finance/FinancialViewport";
import MarketTape from "@/components/finance/MarketTape";

const PROVIDER_ORDER = ["TMS", "BINANCE", "NEPSE", "PORTFOLIO_TRACKER"];

const STATE_COPY = {
  OWNER_FINANCIAL_LOGIN_REQUIRED: "Log in to the provider in the opened browser, then confirm below.",
  OWNER_TMS_LOGIN_REQUIRED: "Log in to TMS in the opened browser, then confirm below.",
  OWNER_FINANCIAL_PORTFOLIO_PAGE_REQUIRED: "Open your Holdings / Portfolio page in the provider browser.",
  OWNER_TMS_PORTFOLIO_PAGE_REQUIRED: "Open your TMS Holdings page in the provider browser.",
  SAATHI_READ_DISABLED: "Saathi Read is OFF. Enable it to allow a read-only observation.",
  SAATHI_READ_OFF: "Saathi Read is OFF. Enable it to allow a read-only observation.",
  SENSITIVE_PAGE_OBSERVATION_BLOCKED: "You are on a sensitive page (login/OTP/order/settings). Observation is paused.",
  PROVIDER_DOMAIN_OUT_OF_SCOPE: "Current page is outside the provider's allowed domain. Observation blocked.",
  SCHEMA_CHANGED_OR_UNVERIFIED: "The provider page structure did not match verified selectors.",
  TMS_AUTH_STATE_UNKNOWN: "Could not confirm an authenticated surface. Open your account page.",
  EMPTY_PORTFOLIO: "No holdings detected on the current page.",
  FINANCIAL_BROWSER_RUNTIME_NOT_FOUND: "No runtime. Open the provider browser first.",
  OWNER_REAUTHENTICATION_REQUIRED: "Session expired — log in again in the provider browser.",
  PROVIDER_RUNTIME_MISMATCH: "Provider/runtime mismatch.",
  NO_OBSERVER: "No observer configured for this provider.",
};

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

function capColor(v) {
  if (!v) return "var(--status-neutral)";
  const s = String(v).toUpperCase();
  if (s.includes("PROHIBITED") || s.includes("UNSUPPORTED")) return "var(--status-danger)";
  if (s.includes("OWNER") || s.includes("MCP") || s.includes("UNKNOWN")) return "var(--status-warning)";
  return "var(--status-success)";
}

export default function FinancialBrowserPage() {
  const [providers, setProviders] = useState(null);
  const [runtimes, setRuntimes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [obs, setObs] = useState({});          // runtime_id -> observation envelope

  const refresh = useCallback(async () => {
    const [p, rt] = await Promise.all([
      api("/api/v1/finance/providers"),
      api("/api/v1/finance/browser/runtimes"),
    ]);
    if (p.ok) setProviders(p.body.providers || p.body);
    if (rt.ok) setRuntimes(rt.body.runtimes || []);
    if (!p.ok && !rt.ok) setErr(`Backend unreachable (HTTP ${p.status}/${rt.status}).`);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const openProvider = async (prov) => {
    setBusy(`open:${prov}`);
    await api("/api/v1/finance/browser/open", { method: "POST", body: JSON.stringify({ provider: prov }) });
    await refresh();
    setBusy("");
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
    setBusy("");
  };
  const closeRuntime = async (id) => {
    setBusy(`close:${id}`);
    await api("/api/v1/finance/browser/close", { method: "POST", body: JSON.stringify({ runtime_id: id }) });
    setObs((o) => { const n = { ...o }; delete n[id]; return n; });
    await refresh(); setBusy("");
  };

  const provKeys = providers
    ? [...PROVIDER_ORDER.filter((k) => k in providers), ...Object.keys(providers).filter((k) => !PROVIDER_ORDER.includes(k))]
    : [];

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "32px 20px 64px" }}>
      <Eyebrow>Finance · Owner-controlled</Eyebrow>
      <Heading level={1} size="xl" style={{ marginTop: 6 }}>Financial Browser</Heading>
      <Text tone="muted" size="sm" style={{ maxWidth: 720, marginTop: 8, display: "block" }}>
        You open a provider site and enter every credential yourself. SaathiOS reads only approved,
        normalized portfolio data — and only after you enable Saathi Read. It never sees your
        password, OTP, cookies, or raw page, and cannot place trades or move funds here.
      </Text>

      {/* Privacy boundary */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        <Pill color="#4FB0C6">Owner enters credentials privately</Pill>
        <Pill color="#7CF5E4">Read-only when Saathi Read = ON</Pill>
        <Pill color="#FF5A5A">No BUY · SELL · TRANSFER · WITHDRAW</Pill>
      </div>

      <Divider style={{ margin: "24px 0" }} />

      <MarketTape />

      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={22} /></div>}
      {err && !loading && <ErrorState title="Cannot reach the Financial Browser API" detail={err} action={<Button onClick={refresh}>Retry</Button>} />}

      {/* Provider cards */}
      {!loading && !err && providers && (
        <>
          <Heading level={2} size="md">Providers</Heading>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 14, marginTop: 12 }}>
            {provKeys.map((name) => {
              const c = providers[name] || {};
              const running = runtimes.find((r) => r.provider === name && r.runtime_state !== "CLOSED");
              return (
                <Card key={name} style={{ padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Heading level={3} size="sm">{name}</Heading>
                    {running ? <StatusBadge status="success" label="Runtime open" /> : <StatusBadge status="neutral" label="Not open" />}
                  </div>
                  <div style={{ marginTop: 10, display: "grid", gap: 4 }}>
                    <CapRow k="Account data" v={c.account_data} />
                    <CapRow k="Agent read" v={c.agent_read} />
                    <CapRow k="Agent actions" v={c.agent_actions} />
                    <CapRow k="Embed" v={c.embed} />
                  </div>
                  {c.note && <Text tone="disabled" size="xs" style={{ marginTop: 8, display: "block" }}>{c.note}</Text>}
                  <div style={{ marginTop: 12 }}>
                    <Button onClick={() => openProvider(name)} disabled={busy === `open:${name}` || !!running}>
                      {busy === `open:${name}` ? "Opening…" : running ? "Opened" : `Open ${name} Browser`}
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {/* Active runtimes */}
      {!loading && !err && (
        <>
          <Heading level={2} size="md" style={{ marginTop: 32 }}>Active sessions</Heading>
          {runtimes.filter((r) => r.runtime_state !== "CLOSED").length === 0 ? (
            <EmptyState title="No open financial browser" description="Open a provider above. SaathiOS launches the owner-controlled window; you log in yourself." style={{ marginTop: 8 }} />
          ) : (
            <div style={{ display: "grid", gap: 14, marginTop: 12 }}>
              {runtimes.filter((r) => r.runtime_state !== "CLOSED").map((r) => (
                <RuntimePanel
                  key={r.runtime_id} rt={r} obs={obs[r.runtime_id]} busy={busy}
                  onAuth={markAuth} onToggleRead={toggleRead} onRead={readPortfolio} onClose={closeRuntime}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CapRow({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13 }}>
      <Text tone="muted" size="sm">{k}</Text>
      <Badge color={capColor(v)} variant="soft" label={String(v ?? "UNKNOWN")} />
    </div>
  );
}

function RuntimePanel({ rt, obs, busy, onAuth, onToggleRead, onRead, onClose }) {
  const authed = rt.auth_state === "OWNER_AUTHENTICATED";
  const readOn = rt.agent_read === true || rt.observation_state === "SAATHI_READ_ON";
  const id = rt.runtime_id;
  return (
    <Panel style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div>
          <Heading level={3} size="sm">{rt.provider}</Heading>
          <Text tone="disabled" size="xs" mono style={{ display: "block", marginTop: 2 }}>{id}</Text>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <Badge variant="soft" label={rt.runtime_state} />
          <Badge color={authed ? "var(--status-ok)" : "var(--status-warning)"} variant="soft" label={rt.auth_state} />
          <StatusBadge status={readOn ? "ok" : "neutral"} label={readOn ? "SAATHI READ-ONLY ACTIVE" : "Saathi Read OFF"} />
        </div>
      </div>

      {rt.runtime_state === "DISPLAY_UNAVAILABLE" && (
        <Text tone="muted" size="xs" style={{ display: "block", marginTop: 8 }}>
          No desktop display on the backend host — the window opens on the owner's Mac session.
        </Text>
      )}

      <Divider style={{ margin: "14px 0" }} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {!authed && (
          <Button onClick={() => onAuth(id)} disabled={busy === `auth:${id}`}>
            {busy === `auth:${id}` ? "…" : "I've logged in"}
          </Button>
        )}
        {authed && !readOn && (
          <Button onClick={() => onToggleRead(id, true)} disabled={busy === `read:${id}`}>
            {busy === `read:${id}` ? "…" : "Enable Saathi Read"}
          </Button>
        )}
        {authed && readOn && (
          <>
            <Button onClick={() => onRead(rt.provider, id)} disabled={busy === `obs:${id}`}>
              {busy === `obs:${id}` ? "Reading…" : "Read Portfolio"}
            </Button>
            <Button variant="ghost" onClick={() => onToggleRead(id, false)} disabled={busy === `read:${id}`}>
              Disable Saathi Read
            </Button>
          </>
        )}
        <Button variant="danger" onClick={() => onClose(id)} disabled={busy === `close:${id}`}>
          {busy === `close:${id}` ? "…" : "Close Browser"}
        </Button>
      </div>

      {rt.runtime_state === "OPEN_OWNER_CONTROL" && (
        <div style={{ marginTop: 16 }}>
          <FinancialViewport provider={rt.provider} runtimeId={id} />
        </div>
      )}
      {rt.runtime_state === "DISPLAY_UNAVAILABLE" && (
        <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 12 }}>
          Live viewport needs the backend on your Mac desktop session (SAATHI_FINANCE_HEADED=1).
        </Text>
      )}

      {obs && <ObservationResult env={obs} />}
    </Panel>
  );
}

function ObservationResult({ env }) {
  const st = env.state;
  if (env.available && env.view) {
    const v = env.view;
    return (
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <StatusBadge status="success" label="OK" />
          <Text size="sm"><strong>{env.holding_count}</strong> holdings</Text>
          {v.total_value != null && <Text size="sm" tone="muted">≈ {v.total_value} {v.currency}</Text>}
          {env.freshness && <Badge variant="soft" label={env.freshness} />}
        </div>
        <div style={{ marginTop: 10, display: "grid", gap: 4 }}>
          {(v.positions || []).slice(0, 8).map((p, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <Text size="sm" mono>{p.symbol}</Text>
              <Text size="sm" tone="muted">{p.quantity} · {p.market_value ?? "—"} {v.currency}</Text>
            </div>
          ))}
        </div>
        <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
          Source: owner-authenticated browser (read-only). Cost basis / P·L shown only when the page exposes them.
        </Text>
      </div>
    );
  }
  const copy = STATE_COPY[st] || "Observation unavailable.";
  const blocked = ["SAATHI_READ_DISABLED", "SAATHI_READ_OFF", "SENSITIVE_PAGE_OBSERVATION_BLOCKED", "PROVIDER_DOMAIN_OUT_OF_SCOPE", "PROVIDER_RUNTIME_MISMATCH"].includes(st);
  return (
    <div style={{ marginTop: 16 }}>
      {blocked
        ? <BlockedState title="Observation paused" reason={st} description={copy} />
        : <EmptyState title={st || "Unavailable"} description={copy} />}
    </div>
  );
}
