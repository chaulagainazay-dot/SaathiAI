"use client";
// Shared NEPSE chrome: scrolling ticker, boundary banner, and tab navigation.
// The boundary banner is mandatory (constitution Article I): this module runs on an
// in-repo SNAPSHOT and must never be mistaken for a live NEPSE feed or accounting truth.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { marketSnapshot, SNAPSHOT_DATE } from "@/lib/nepse/data";
import { useNepseQuotes } from "@/lib/nepse/live";
import { fmtNum, fmtPct, fmtCompactRs } from "@/lib/nepse/format";

const TABS = [
  { href: "/nepse", label: "Portfolio" },
  { href: "/nepse/market", label: "Market" },
  { href: "/nepse/stocks", label: "All Stocks" },
  { href: "/nepse/watchlist", label: "Watchlist" },
  { href: "/nepse/brokers", label: "Brokers" },
];

function Ticker() {
  const m = marketSnapshot();
  const chg = m.index - m.indexPrev;
  const items = [
    { l: "NEPSE", v: `${fmtNum(m.index)} ${fmtPct((chg / m.indexPrev) * 100)}`, dir: chg >= 0 ? "up" : "down" },
    { l: "ADVANCED", v: String(m.advancing), dir: "up" },
    { l: "DECLINED", v: String(m.declining), dir: "down" },
    { l: "TURNOVER", v: fmtCompactRs(m.turnover) },
    { l: "STOCKS", v: String(m.listed) },
    { l: "MARKET", v: "Closed" },
  ];
  const set = items.map((it, i) => (
    <span key={i}>
      <b>{it.l}</b>
      <span className={`num ${it.dir === "up" ? "nepse-up" : it.dir === "down" ? "nepse-down" : ""}`}>{it.v}</span>
    </span>
  ));
  return (
    <div className="nepse-ticker-wrap" aria-hidden="true">
      <div className="nepse-ticker">{set}{set}</div>
    </div>
  );
}

export default function NepseShell({ children }) {
  const pathname = usePathname() || "/nepse";
  const { source, isLive, asOf, reason } = useNepseQuotes();
  const isActive = (href) =>
    href === "/nepse" ? pathname === "/nepse" : pathname.startsWith(href);
  return (
    <div className="nepse-root">
      <Ticker />
      <div className="nepse-wrap">
        <div className="nepse-banner" data-testid="nepse-boundary">
          <span className={`nepse-chip ${isLive ? "live" : "warn"}`} data-testid="nepse-feed-state">
            {isLive ? "Live NEPSE feed" : "Snapshot / seed data — NOT a live NEPSE feed"}
          </span>
          <span className="nepse-chip">No broker login</span>
          <span className="nepse-chip">No OAuth</span>
          <span className="nepse-chip">Not investment advice</span>
          <span className="nepse-chip">As of {isLive && asOf ? new Date(asOf).toLocaleTimeString() : SNAPSHOT_DATE}</span>
          {!isLive && reason ? <span className="nepse-chip">{reason}</span> : null}
        </div>
        <nav className="nepse-tabs">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} className={`nepse-tab ${isActive(t.href) ? "active" : ""}`}>
              {t.label}
            </Link>
          ))}
        </nav>
        {children}
      </div>
    </div>
  );
}
