"use client";
// Shared NEPSE chrome: scrolling ticker, boundary banner, and tab navigation.
// The boundary banner is mandatory (constitution Article I): this module runs on an
// in-repo SNAPSHOT and must never be mistaken for a live NEPSE feed or accounting truth.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SNAPSHOT_DATE } from "@/lib/nepse/data";
import { useNepseQuotes } from "@/lib/nepse/live";
import { useMarketAggregates, useIndices } from "@/lib/nepse/use-market";
import { fmtNum, fmtPct, fmtCompactRs } from "@/lib/nepse/format";

const TABS = [
  { href: "/nepse", label: "Portfolio" },
  { href: "/nepse/market", label: "Market" },
  { href: "/nepse/stocks", label: "All Stocks" },
  { href: "/nepse/watchlist", label: "Watchlist" },
  { href: "/nepse/brokers", label: "Brokers" },
];

function Ticker() {
  // The ticker used to lead with a hardcoded NEPSE index and a hardcoded turnover.
  // It now carries only figures computed from the last completed session, and shows
  // nothing at all when they cannot be computed — a ticker of invented numbers is
  // the most persuasive lie in a trading UI, because it sits on every page.
  const { data } = useMarketAggregates();
  const ix = useIndices();
  if (!data) return null;
  const b = data.breadth;
  const top = data.gainers[0];
  const idx = ix.data?.index;
  const items = [
    // The index is back — but as the PUBLISHED figure, never the hardcoded one
    // this ticker used to carry. Omitted entirely when the source is unavailable.
    ...(idx ? [{
      l: "NEPSE",
      v: `${fmtNum(idx.close)} ${idx.changePct === null ? "" : fmtPct(idx.changePct)}`.trim(),
      dir: (idx.changePct ?? 0) >= 0 ? "up" : "down",
    }] : []),
    { l: `SESSION ${data.asOf}`, v: b.mood },
    { l: "ADVANCED", v: String(b.advancing), dir: "up" },
    { l: "DECLINED", v: String(b.declining), dir: "down" },
    { l: "UNCHANGED", v: String(b.unchanged) },
    ...(ix.data?.turnover ? [{ l: "TURNOVER", v: fmtCompactRs(ix.data.turnover) }] : []),
    { l: "VOLUME", v: fmtNum(data.activity.totalVolume, 0) },
    ...(top ? [{ l: `TOP ${top.symbol}`, v: fmtPct(top.changePct), dir: "up" }] : []),
    { l: "MEASURED", v: `${b.measured}/${data.coverage.listedTotal}` },
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
            {/* Names what the chip actually covers. Pages such as Market render no
                live prices at all, and an unqualified "Live NEPSE feed" sitting above
                a settled-session table reads as a claim about that table. */}
            {isLive ? "Live price feed — quotes only" : "Snapshot / seed data — NOT a live NEPSE feed"}
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
