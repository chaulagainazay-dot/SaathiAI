"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CORE_NOTICE, coreActions } from "@/lib/core-os";
import { getToken } from "@/lib/platform-client.js";

const card = {
  background: "rgba(18,28,48,0.92)",
  border: "1px solid rgba(120,150,200,0.18)",
  borderRadius: 12,
  padding: 14,
};
const btn = {
  background: "#2B6CFF",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 600,
};
const btnGhost = {
  ...btn,
  background: "transparent",
  border: "1px solid rgba(120,150,200,0.35)",
  color: "#D7E2F5",
};

export default function OperatorHome() {
  const [token, setToken] = useState("");
  const [home, setHome] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [searchHits, setSearchHits] = useState([]);
  const [yetiQ, setYetiQ] = useState("What should I do first today?");
  const [yetiA, setYetiA] = useState(null);
  const [status, setStatus] = useState("");
  const [automations, setAutomations] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    setToken(getToken() || "");
  }, []);

  const refresh = useCallback(async () => {
    const t = getToken() || token;
    if (!t) return;
    setError("");
    try {
      const [h, a, w, n] = await Promise.all([
        coreActions.home(t),
        coreActions.automations(t),
        coreActions.listWorkflows(t),
        coreActions.notifications(t),
      ]);
      setHome(h.home || null);
      setAutomations(a.automations || []);
      setWorkflows(w.graphs || []);
      setNotifications(n.notifications || []);
    } catch (e) {
      setError(e.message || "Load failed");
    }
  }, [token]);

  useEffect(() => {
    if (token) refresh();
  }, [token, refresh]);

  async function run(fn) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <main style={{ padding: 24, color: "#E8EEF9" }} aria-label="Operator Home">
        <h1>Operator Home</h1>
        <p>Sign in required.</p>
        <Link href="/security">Go to Security</Link>
      </main>
    );
  }

  const apps = home?.applications || {};
  const work = home?.todays_work || [];

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg,#0B1220,#121C30)",
        color: "#E8EEF9",
        padding: "16px 16px 48px",
      }}
      aria-label="Operator Home"
      data-core-home="true"
    >
      <header style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>SaathiOS Operator Home</h1>
          <p style={{ margin: "4px 0 0", color: "#8B98B4", fontSize: 13 }}>
            {CORE_NOTICE.unification}
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link href="/apps" style={{ color: "#9EC1FF" }}>
            Apps
          </Link>
          <Link href="/platform/search" style={{ color: "#9EC1FF" }}>
            Search
          </Link>
          <Link href="/platform/approvals" style={{ color: "#9EC1FF" }}>
            Approvals
          </Link>
          <button type="button" style={btnGhost} onClick={() => refresh()} disabled={busy}>
            Refresh
          </button>
        </div>
      </header>

      <div aria-live="polite" style={{ minHeight: 22, color: error ? "#FF8A8A" : "#10C98A", marginBottom: 10 }}>
        {error || status}
      </div>

      {/* Universal search */}
      <section style={{ ...card, marginBottom: 14 }} data-core-search="true">
        <h2 style={{ marginTop: 0, fontSize: 15 }}>Universal Search</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                run(async () => {
                  const r = await coreActions.search(token, q);
                  setSearchHits(r.results || []);
                  setStatus(`${r.count || 0} results`);
                });
              }
            }}
            placeholder="Search apps, missions, HCG, IELTS, approvals…"
            aria-label="Universal search"
            style={{ flex: 1, padding: 10, borderRadius: 8 }}
          />
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await coreActions.search(token, q);
                setSearchHits(r.results || []);
                setStatus(`${r.count || 0} results · ${r.scope}`);
              })
            }
          >
            Search
          </button>
        </div>
        {!!searchHits.length && (
          <ul style={{ marginTop: 10 }}>
            {searchHits.slice(0, 12).map((h) => (
              <li key={`${h.source}-${h.id}-${h.label}`}>
                <Link href={h.href || "/platform/home"} style={{ color: "#9EC1FF" }}>
                  [{h.source}] {h.label}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Dashboard grid */}
      <section
        style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", marginBottom: 14 }}
        data-core-dashboard="true"
      >
        <div style={card}>
          <div style={{ color: "#8B98B4", fontSize: 12 }}>Applications</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>
            {apps.enabled ?? "—"} enabled / {apps.running ?? "—"} running
          </div>
          <ul style={{ marginTop: 8, paddingLeft: 18 }}>
            {(apps.apps || []).map((a) => (
              <li key={a.app_id}>
                <Link href={a.href || "/apps"} style={{ color: "#9EC1FF" }}>
                  {a.display_name}
                </Link>{" "}
                <span style={{ color: "#8B98B4" }}>{a.state}</span>
              </li>
            ))}
          </ul>
        </div>
        <div style={card}>
          <div style={{ color: "#8B98B4", fontSize: 12 }}>HCG today</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            sales {home?.hcg?.sales_today_minor ?? "—"} · orders {home?.hcg?.order_count ?? "—"}
          </div>
          <Link href="/apps/hcg" style={{ color: "#9EC1FF", fontSize: 13 }}>
            Open HCG
          </Link>
        </div>
        <div style={card}>
          <div style={{ color: "#8B98B4", fontSize: 12 }}>IELTS readiness</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{home?.ielts?.readiness ?? "—"}</div>
          <div style={{ fontSize: 13, color: "#8B98B4" }}>
            practices {home?.ielts?.practice_count ?? "—"} · estimate {home?.ielts?.overall_estimate ?? "—"}
          </div>
          <Link href="/apps/ielts" style={{ color: "#9EC1FF", fontSize: 13 }}>
            Open IELTSAlert
          </Link>
        </div>
        <div style={card}>
          <div style={{ color: "#8B98B4", fontSize: 12 }}>Approvals</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{home?.approvals_count ?? 0} pending</div>
          <Link href="/platform/approvals" style={{ color: "#9EC1FF", fontSize: 13 }}>
            Approval Center
          </Link>
        </div>
      </section>

      <section style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr", marginBottom: 14 }}>
        <div style={card} data-core-work="true">
          <h2 style={{ marginTop: 0, fontSize: 15 }}>Today&apos;s work</h2>
          <ul>
            {work.map((w) => (
              <li key={w.label}>
                <Link href={w.href || "/platform/home"} style={{ color: "#9EC1FF" }}>
                  {w.label}
                </Link>
              </li>
            ))}
          </ul>
          <h3 style={{ fontSize: 13, color: "#8B98B4" }}>Quick actions</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(home?.quick_actions || []).map((a) => (
              <Link key={a.id} href={a.href} style={{ ...btnGhost, textDecoration: "none", fontSize: 12, padding: "6px 10px" }}>
                {a.label}
              </Link>
            ))}
          </div>
        </div>

        <div style={card} data-core-yeti="true">
          <h2 style={{ marginTop: 0, fontSize: 15 }}>Unified Yeti</h2>
          <p style={{ fontSize: 12, color: "#8B98B4" }}>{CORE_NOTICE.yeti}</p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={yetiQ}
              onChange={(e) => setYetiQ(e.target.value)}
              aria-label="Ask Yeti"
              style={{ flex: 1, padding: 8, borderRadius: 8 }}
            />
            <button
              type="button"
              style={btn}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const a = await coreActions.yeti(token, yetiQ);
                  setYetiA(a);
                })
              }
            >
              Ask
            </button>
          </div>
          {yetiA && (
            <div style={{ marginTop: 10 }}>
              <p>{yetiA.answer}</p>
              <p style={{ fontSize: 12, color: "#8B98B4" }}>
                can_mutate={String(yetiA.can_mutate)} · domains=
                {(yetiA.domains || []).map((d) => d.domain).join(", ")}
              </p>
            </div>
          )}
        </div>
      </section>

      <section style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr", marginBottom: 14 }}>
        <div style={card} data-core-notifications="true">
          <h2 style={{ marginTop: 0, fontSize: 15 }}>Notification Center</h2>
          <ul>
            {notifications.slice(0, 8).map((n) => (
              <li key={n.notification_id || n.title}>
                [{n.source_app || n.channel || "platform"}] {n.title}
              </li>
            ))}
          </ul>
          {!notifications.length && <p style={{ color: "#8B98B4" }}>No notifications</p>}
          <Link href="/platform/notifications" style={{ color: "#9EC1FF", fontSize: 13 }}>
            Full center
          </Link>
        </div>

        <div style={card} data-core-automation="true">
          <h2 style={{ marginTop: 0, fontSize: 15 }}>Automations & workflows</h2>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                await coreActions.createAutomation(token, {
                  name: "Morning HCG+IELTS summary",
                  schedule: "daily_morning",
                  action: "summarize",
                  app_scope: "all",
                  requires_approval: true,
                });
                setStatus("Automation created (dry-run only until Mission/Gateway path)");
              })
            }
          >
            Create morning summary automation
          </button>
          <button
            type="button"
            style={{ ...btnGhost, marginLeft: 8 }}
            disabled={busy}
            onClick={() =>
              run(async () => {
                await coreActions.saveWorkflow(token, {
                  name: "Approval-gated report",
                  nodes: [
                    { id: "t1", type: "trigger", label: "Schedule" },
                    { id: "c1", type: "condition", label: "Weekday" },
                    { id: "a1", type: "agent", label: "Summarize" },
                    { id: "ap1", type: "approval", label: "Manager" },
                    { id: "e1", type: "execution", label: "Gateway" },
                    { id: "ev1", type: "evidence", label: "Record" },
                    { id: "n1", type: "notification", label: "Notify" },
                    { id: "f1", type: "finish", label: "Done" },
                  ],
                  edges: [
                    { from: "t1", to: "c1" },
                    { from: "c1", to: "a1" },
                    { from: "a1", to: "ap1" },
                    { from: "ap1", to: "e1" },
                    { from: "e1", to: "ev1" },
                    { from: "ev1", to: "n1" },
                    { from: "n1", to: "f1" },
                  ],
                });
                setStatus("Workflow graph saved (metadata; executes via Gateway)");
              })
            }
          >
            Save sample workflow graph
          </button>
          <ul style={{ marginTop: 10 }}>
            {automations.map((a) => (
              <li key={a.automation_id}>
                {a.name}{" "}
                <button
                  type="button"
                  style={{ ...btnGhost, padding: "2px 8px", fontSize: 11 }}
                  onClick={() =>
                    run(async () => {
                      const d = await coreActions.dryRunAutomation(token, a.automation_id);
                      setStatus(`Dry-run: ${d.proposal?.summary}`);
                    })
                  }
                >
                  Dry-run
                </button>
              </li>
            ))}
          </ul>
          <p style={{ fontSize: 12, color: "#8B98B4" }}>
            Workflows: {workflows.length} · execution always via Mission/Agent/ExecutionGateway
          </p>
        </div>
      </section>

      <section style={card} data-core-activity="true">
        <h2 style={{ marginTop: 0, fontSize: 15 }}>Recent activity</h2>
        <ul>
          {(home?.activity || []).slice(0, 10).map((e) => (
            <li key={e.id || e.summary}>
              {e.kind}: {e.summary}
            </li>
          ))}
        </ul>
        {!home?.activity?.length && <p style={{ color: "#8B98B4" }}>Activity appears as you search and ask Yeti.</p>}
      </section>

      <p style={{ marginTop: 16, fontSize: 12, color: "#8B98B4" }}>{CORE_NOTICE.production}</p>
    </main>
  );
}
