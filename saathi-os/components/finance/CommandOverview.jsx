"use client";
/**
 * Command Overview — one-glance dashboard aggregating every deck module (portfolio, NEPSE
 * movers, signals, paper-agent stats, news) by calling their existing endpoints in parallel.
 * Observation-only. Each card links to its full page.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE, afetch } from "@/lib/api";
import { Panel, Badge, Text, Spinner } from "@/components/ui";

const get = (p) => afetch(`${API_BASE}${p}`, { cache: "no-store" }).then(async (r) => { try { return await r.json(); } catch { return {}; } }).catch(() => ({}));
const post = (p, b) => afetch(`${API_BASE}${p}`, { method: "POST", cache: "no-store", headers: { "content-type": "application/json" }, body: JSON.stringify(b) }).then(async (r) => { try { return await r.json(); } catch { return {}; } }).catch(() => ({}));

function Card({ title, href, children }) {
  return (
    <Panel style={{ padding: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderBottom: "1px solid rgba(255,64,64,.12)" }}>
        <span style={{ fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>{title}</span>
        {href && <Link href={href} style={{ color: "#ff5757", fontSize: 11, textDecoration: "none" }}>open →</Link>}
      </div>
      <div style={{ padding: 14 }}>{children}</div>
    </Panel>
  );
}

export default function CommandOverview() {
  const [d, setD] = useState({ loading: true });

  useEffect(() => {
    let alive = true;
    (async () => {
      const [pf, mv, jr, nw, nep] = await Promise.all([
        get("/api/v1/finance/portfolio/analysis"),
        get("/api/v1/market/free/movers?top=4"),
        get("/api/v1/trading/paper/journal?limit=1"),
        get("/api/v1/research/events?limit=5"),
        get("/api/v1/market/nepse/live/full"),
      ]);
      if (!alive) return;
      setD({ loading: false, pf, mv, jr, nw, nep });
    })();
    return () => { alive = false; };
  }, []);

  if (d.loading) return <div style={{ display: "flex", justifyContent: "center", padding: 28 }}><Spinner size={18} /></div>;

  const t = d.pf?.totals || {};
  const st = d.jr?.stats || {};
  const idx = d.nep?.nepse_index, idxPct = d.nep?.index_change_percent;
  const gain = d.mv?.gainers || [], lose = d.mv?.losers || [];
  const events = d.nw?.events || [];

  return (
    <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12, marginTop: 16 }}>
      {/* Portfolio */}
      <Card title="Portfolio" href="/command-deck/portfolio">
        {d.pf?.empty ? <Text tone="muted" size="sm">No holdings yet — add positions.</Text> : d.pf?.available ? (
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{t.value != null ? "NPR " + Math.round(t.value).toLocaleString("en-IN") : "—"}</div>
              <span style={{ color: (t.pl_pct ?? 0) >= 0 ? "#2ee27a" : "#ff4d4d", fontWeight: 600 }}>{t.pl_pct != null ? `${t.pl_pct >= 0 ? "+" : ""}${t.pl_pct}%` : ""}</span>
            </div>
            <Text tone="muted" size="xs" style={{ display: "block", marginTop: 4 }}>{t.positions} positions · top {t.top_name} {t.concentration}%{t.max_drawdown_pct != null ? ` · DD ${t.max_drawdown_pct}%` : ""}</Text>
          </div>
        ) : <Text tone="muted" size="sm">Sign in to load your portfolio.</Text>}
      </Card>

      {/* NEPSE */}
      <Card title="NEPSE" href="/command-deck/nepse">
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
          <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{idx != null ? Number(idx).toLocaleString("en-IN") : "—"}</div>
          <span style={{ color: (Number(idxPct) || 0) >= 0 ? "#2ee27a" : "#ff4d4d", fontWeight: 600 }}>{idxPct != null ? `${Number(idxPct) >= 0 ? "+" : ""}${idxPct}%` : ""}</span>
        </div>
        <div style={{ fontSize: 12 }}>
          {gain.slice(0, 3).map((g) => <span key={g.symbol} style={{ marginRight: 10, color: "#2ee27a" }}>{g.symbol} +{g.percent_change}%</span>)}
        </div>
        <div style={{ fontSize: 12, marginTop: 3 }}>
          {lose.slice(0, 2).map((g) => <span key={g.symbol} style={{ marginRight: 10, color: "#ff4d4d" }}>{g.symbol} {g.percent_change}%</span>)}
        </div>
      </Card>

      {/* Paper agent */}
      <Card title="Paper Agent" href="/command-deck/guardian">
        <div style={{ display: "flex", gap: 16 }}>
          <div><div style={{ fontSize: 10, color: "#8f8288" }}>WIN RATE</div><div style={{ fontSize: 20, fontWeight: 700, color: st.win_rate == null ? "#8f8288" : st.win_rate >= 50 ? "#2ee27a" : "#ff4d4d" }}>{st.win_rate != null ? `${st.win_rate}%` : "—"}</div></div>
          <div><div style={{ fontSize: 10, color: "#8f8288" }}>W / L</div><div style={{ fontSize: 20, fontWeight: 700 }}>{st.won ?? 0}/{st.lost ?? 0}</div></div>
          <div><div style={{ fontSize: 10, color: "#8f8288" }}>OPEN</div><div style={{ fontSize: 20, fontWeight: 700 }}>{st.open ?? 0}</div></div>
        </div>
      </Card>

      {/* News */}
      <Card title="Market News" href="/command-deck/news">
        {events.length === 0 ? <Text tone="muted" size="sm">No research events.</Text> : events.slice(0, 4).map((e, i) => (
          <div key={i} style={{ fontSize: 12, color: "#dccfd3", padding: "3px 0", borderBottom: i < 3 ? "1px solid rgba(255,64,64,.06)" : "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.headline || e.title || "(event)"}</div>
        ))}
      </Card>
    </section>
  );
}
