"use client";
// Alerts — standing rules, evaluated against the current quote, delivered once.
//
// TWO SEPARATE HONESTY PROBLEMS LIVE ON THIS PAGE.
//
// 1. WHETHER THE CONDITION IS TRUE. A rule whose quote is missing or stale is
//    NOT_EVALUABLE, never "did not fire". Firing a price alert against snapshot
//    data would tell someone a level was crossed today when the number is from
//    the last completed session — so when the feed is not live, every quote is
//    handed to the evaluator marked stale and the rules refuse rather than lie.
//
// 2. WHETHER TO SAY SO. A true condition is not automatically a notification.
//    An alert that was already firing has not become true again, and one that
//    fired four minutes ago is not news. Suppression is a decision WITH A REASON,
//    shown on the row, so silence is explained rather than mysterious.

import { useCallback, useEffect, useMemo, useState } from "react";
import { STOCKS } from "@/lib/nepse/data";
import { useNepseQuotes } from "@/lib/nepse/live";
import {
  ALERT_KIND, ALERT_STATUS, evaluateRules, validateRule,
} from "@/lib/alerts/rules";
import {
  CHANNEL, DEFAULT_COOLDOWN_MS, DEFAULT_MAX_PER_HOUR, DELIVERY,
  advance, channelAvailability, composeNotification, decide,
} from "@/lib/alerts/delivery";
import { fmtNum } from "@/lib/nepse/format";
import * as store from "@/lib/nepse/store";

const KIND_LABEL = {
  [ALERT_KIND.PRICE_ABOVE]: "Price rises above",
  [ALERT_KIND.PRICE_BELOW]: "Price falls below",
  [ALERT_KIND.PERCENT_CHANGE_ABOVE]: "Day change rises above (%)",
  [ALERT_KIND.PERCENT_CHANGE_BELOW]: "Day change falls below (%)",
  [ALERT_KIND.VOLUME_RATIO_ABOVE]: "Volume ratio above",
};

const DELIVERY_TEXT = {
  // SEND is a PERMISSION, not a receipt. The row rendered "sent" the moment a
  // rule went true, before "Check now" had run — telling the user a notification
  // had gone out when none had.
  [DELIVERY.SEND]: "clear to send",
  [DELIVERY.SUPPRESSED_UNCHANGED]: "already firing — not news again",
  [DELIVERY.SUPPRESSED_COOLDOWN]: "held: fired recently",
  [DELIVERY.SUPPRESSED_RATE_LIMIT]: "held: hourly cap reached",
  [DELIVERY.SUPPRESSED_MUTED]: "muted",
  [DELIVERY.CHANNEL_UNAVAILABLE]: "browser notifications not permitted",
};

export default function AlertsPage() {
  const { stocks, isLive, asOf, source } = useNepseQuotes();
  const [rules, setRules] = useState([]);
  const [history, setHistory] = useState({});
  const [muted, setMuted] = useState(false);
  const [channel, setChannel] = useState(CHANNEL.IN_APP);
  const [perm, setPerm] = useState({ available: false, reason: "NOT_SUPPORTED", permission: null });
  const [form, setForm] = useState({ symbol: "NABIL", kind: ALERT_KIND.PRICE_ABOVE, threshold: "" });
  const [err, setErr] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setRules(store.listAlerts());
    setHistory(store.loadAlertHistory());
    setPerm(channelAvailability());
    setMounted(true);
  }, []);

  // The evaluator is handed a quote map, and a NON-LIVE feed is marked stale on
  // every symbol. This is the whole reason a snapshot cannot trigger an alert.
  const quotes = useMemo(() => Object.fromEntries(stocks.map((s) => [s.symbol, {
    price: s.ltp,
    previousClose: s.prevClose ?? null,
    volume: s.volume ?? null,
    averageVolume: s.averageVolume ?? null,
    stale: !isLive,
    asOf: asOf || null,
  }])), [stocks, isLive, asOf]);

  const results = useMemo(
    () => evaluateRules(rules, { quotes, now: Date.now() }),
    [rules, quotes],
  );

  const decisions = useMemo(() => results.map((r) => {
    const rule = rules.find((x) => x.id === r.ruleId || x.id === r.id) || null;
    return {
      result: r,
      rule,
      decision: decide(r, history[r.ruleId ?? r.id] || {}, {
        muted,
        channel,
        channelAvailable: perm.permission === "granted",
        cooldownMs: rule?.cooldownMs ?? DEFAULT_COOLDOWN_MS,
      }),
    };
  }), [results, rules, history, muted, channel, perm]);

  // Deliver, then record. Recording is what makes the second evaluation of the
  // same standing condition a suppression instead of a repeat notification.
  const deliver = useCallback(() => {
    let next = { ...history };
    let sent = 0;
    for (const { result, rule, decision } of decisions) {
      const id = result.ruleId ?? result.id;
      if (!id) continue;
      if (decision.deliver && channel === CHANNEL.BROWSER_NOTIFICATION && perm.permission === "granted") {
        const n = composeNotification(rule || {}, result);
        try { new window.Notification(n.title, { body: n.body, tag: n.tag }); } catch { /* refused */ }
      }
      if (decision.deliver) sent += 1;
      next[id] = advance(next[id] || {}, decision);
    }
    setHistory(next);
    store.saveAlertHistory(next);
    return sent;
  }, [decisions, history, channel, perm]);

  const add = () => {
    const threshold = form.threshold === "" ? null : Number(form.threshold);
    // Parsed HERE, in the form. The comparator must never receive a string:
    // "9" > "70" is true, and that misfire is invisible.
    const rule = { id: `a_${Date.now().toString(36)}`, symbol: form.symbol, kind: form.kind, threshold };
    const v = validateRule(rule);
    if (!v.valid) { setErr(v.errors.map((e) => e.message).join("; ")); return; }
    setErr("");
    store.saveAlert(rule);
    setRules(store.listAlerts());
    setForm({ ...form, threshold: "" });
  };

  const remove = (id) => {
    store.deleteAlert(id);
    setRules(store.listAlerts());
    setHistory(store.loadAlertHistory());
  };

  const askPermission = async () => {
    try {
      await window.Notification.requestPermission();
      setPerm(channelAvailability());
    } catch { setPerm(channelAvailability()); }
  };

  if (!mounted) return <div className="nepse-empty">Loading…</div>;

  const undecided = results.filter((r) => r.status === ALERT_STATUS.NOT_EVALUABLE).length;

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Alerts</div>
        <h1 className="nepse-title">Standing rules</h1>
        <p className="nepse-dek">
          Rules live in this browser only. Nothing is sent to a server, and nothing
          fires while the tab is closed.
        </p>
      </header>

      {!isLive && (
        <div className="nepse-callout gold" style={{ marginTop: "1rem" }}>
          <strong>The feed is not live ({source}).</strong> Every quote is handed to
          the evaluator marked stale, so no rule can fire. A price alert triggered
          by settled-session data would tell you a level was crossed today.
        </div>
      )}

      <div className="nepse-card" style={{ marginTop: "1rem" }}>
        <h3>New rule</h3>
        <div className="nepse-row" style={{ marginTop: "0.6rem", flexWrap: "wrap" }}>
          <select className="nepse-select" aria-label="Symbol" value={form.symbol}
                  onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
            {STOCKS.map((s) => <option key={s.symbol}>{s.symbol}</option>)}
          </select>
          <select className="nepse-select" aria-label="Condition" value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input className="nepse-input" style={{ width: "8rem" }} inputMode="decimal"
                 aria-label="Threshold" placeholder="Threshold" value={form.threshold}
                 onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
          <button className="nepse-btn" type="button" onClick={add}>Add rule</button>
        </div>
        {err && <p style={{ color: "var(--down)", fontSize: "0.82rem", marginTop: "0.5rem" }}>{err}</p>}
      </div>

      <div className="nepse-card" style={{ marginTop: "1rem" }}>
        <h3>Delivery</h3>
        <div className="nepse-row" style={{ marginTop: "0.6rem", flexWrap: "wrap" }}>
          <select className="nepse-select" aria-label="Channel" value={channel}
                  onChange={(e) => setChannel(e.target.value)}>
            <option value={CHANNEL.IN_APP}>In-app only</option>
            <option value={CHANNEL.BROWSER_NOTIFICATION}>Browser notification</option>
          </select>
          <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={muted} onChange={(e) => setMuted(e.target.checked)} />
            Mute
          </label>
          <button className="nepse-btn" type="button" onClick={() => deliver()}>Check now</button>
          {channel === CHANNEL.BROWSER_NOTIFICATION && perm.permission !== "granted" && (
            <button className="nepse-btn ghost" type="button" onClick={askPermission}
                    disabled={!perm.available && perm.reason === "NOT_SUPPORTED"}>
              {perm.reason === "NOT_SUPPORTED" ? "This browser has no notifications" : "Allow notifications"}
            </button>
          )}
        </div>
        <p style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
          A rule is held for {fmtNum(DEFAULT_COOLDOWN_MS / 60000, 0)} minutes after it
          fires, and at most {DEFAULT_MAX_PER_HOUR} notifications go out in an hour.
          Both limits exist so a stock oscillating around your threshold does not
          teach you to ignore the alerts entirely.
        </p>
      </div>

      <div className="nepse-table-wrap" style={{ marginTop: "1.25rem" }}>
        <table className="nepse-table">
          <thead>
            <tr><th>Symbol</th><th>Condition</th><th className="rt">Threshold</th>
              <th className="rt">Observed</th><th>State</th><th>Delivery</th><th></th></tr>
          </thead>
          <tbody>
            {decisions.length === 0 && (
              <tr><td colSpan={7} className="nepse-empty">No rules yet.</td></tr>
            )}
            {decisions.map(({ result, rule, decision }) => {
              const id = result.ruleId ?? result.id;
              return (
                <tr key={id}>
                  <td className="strong">{rule?.symbol ?? result.symbol ?? "—"}</td>
                  <td style={{ fontSize: "0.84rem" }}>{KIND_LABEL[rule?.kind] ?? rule?.kind ?? "—"}</td>
                  <td className="rt num">{rule?.threshold ?? "—"}</td>
                  <td className="rt num">
                    {/* An unevaluable rule shows a dash, never a stale number that
                        would look like the value the decision was made on. */}
                    {result.observedValue === null || result.observedValue === undefined
                      ? "—" : fmtNum(result.observedValue)}
                  </td>
                  <td>
                    <span className={`nepse-badge ${result.fired ? "up" : result.status === ALERT_STATUS.NOT_EVALUABLE ? "down" : "neutral"}`}>
                      {result.status === ALERT_STATUS.NOT_EVALUABLE ? "undecided"
                        : result.fired ? "firing" : "quiet"}
                    </span>
                    {result.reason && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-faint)" }}>{result.reason}</div>
                    )}
                  </td>
                  <td style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>
                    {decision.reason ? DELIVERY_TEXT[decision.reason] ?? decision.reason
                      : decision.deliver ? "clear to send" : "nothing to say"}
                    {decision.retryAfterMs
                      ? ` (${fmtNum(decision.retryAfterMs / 60000, 0)} min)` : ""}
                    {/* What actually went out, read from the delivery history —
                        the only record of a notification having happened. */}
                    {history[id]?.lastFiredAt && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-faint)" }}>
                        last sent {new Date(history[id].lastFiredAt).toLocaleTimeString()}
                      </div>
                    )}
                  </td>
                  <td className="rt">
                    <button className="nepse-btn ghost" type="button" onClick={() => remove(id)}>Delete</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {undecided > 0 && (
        <p style={{ fontSize: "0.8rem", color: "var(--gold)", marginTop: "0.6rem" }}>
          {undecided} rule{undecided === 1 ? "" : "s"} could not be decided. That is
          not the same as &ldquo;did not fire&rdquo; — the condition may well be true
          and we cannot tell.
        </p>
      )}
    </>
  );
}
