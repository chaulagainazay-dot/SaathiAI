"use client";
// US3 — Market. Exchange-wide state: index + breadth + turnover, an advance/decline
// sentiment gauge, an index area chart, and a per-sector performance grid.
import { useMemo } from "react";
import { marketSnapshot, indexHistory } from "@/lib/nepse/data";
import { fmtNum, fmtPct, fmtCompactRs } from "@/lib/nepse/format";

function sentiment(adv, dec) {
  const total = adv + dec;
  const ratio = total ? adv / total : 0.5; // 0..1
  const needle = Math.round(ratio * 100);
  const mood = needle >= 60 ? "Bullish" : needle <= 40 ? "Bearish" : "Neutral";
  return { needle, mood, adRatio: dec ? +(adv / dec).toFixed(2) : adv };
}

function IndexChart({ data }) {
  const w = 640; const h = 160; const pad = 6;
  const vs = data.map((d) => d.v);
  const min = Math.min(...vs); const max = Math.max(...vs);
  const span = max - min || 1;
  const pts = data.map((d, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (d.v - min) / span) * (h - pad * 2);
    return [x, y];
  });
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${h} L${pts[0][0].toFixed(1)},${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="NEPSE index history">
      <path d={area} fill="var(--accent-soft)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" />
    </svg>
  );
}

export default function MarketPage() {
  const m = useMemo(() => marketSnapshot(), []);
  const hist = useMemo(() => indexHistory(90, m.index), [m.index]);
  const s = sentiment(m.advancing, m.declining);
  const chg = m.index - m.indexPrev;

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Market</div>
        <h1 className="nepse-title">Exchange-wide state</h1>
        <p className="nepse-dek">Nothing here is scoped to your holdings — this is the whole market.</p>
      </header>

      <div className="nepse-grid-4" style={{ marginTop: "1rem" }}>
        <div className="nepse-card"><span className="tag">Index</span>
          <div className="nepse-stat num">{fmtNum(m.index)}</div>
          <div className={chg >= 0 ? "nepse-up" : "nepse-down"}>{fmtPct((chg / m.indexPrev) * 100)}</div>
        </div>
        <div className="nepse-card"><span className="tag">Turnover</span><div className="nepse-stat num">{fmtCompactRs(m.turnover)}</div></div>
        <div className="nepse-card"><span className="tag">Volume</span><div className="nepse-stat num">{fmtNum(m.volume, 0)}</div></div>
        <div className="nepse-card"><span className="tag">Total market cap</span><div className="nepse-stat num">{fmtCompactRs(m.totalMarketCap)}</div></div>
      </div>

      <div className="nepse-grid-2" style={{ marginTop: "1rem" }}>
        <div className="nepse-card">
          <span className="tag">Sentiment</span>
          <h3>{s.mood} · A/D {s.adRatio}</h3>
          <div className="nepse-gauge" style={{ marginTop: "1rem" }}>
            <div className="needle" style={{ left: `${s.needle}%` }} />
          </div>
          <div className="nepse-row" style={{ marginTop: "0.9rem", gap: "1.5rem", fontSize: "0.9rem" }}>
            <span className="nepse-up">Advancing {m.advancing}</span>
            <span className="nepse-down">Declining {m.declining}</span>
            <span style={{ color: "var(--text-faint)" }}>Unchanged {m.unchanged}</span>
          </div>
        </div>
        <div className="nepse-card">
          <span className="tag">History · index</span>
          <IndexChart data={hist} />
        </div>
      </div>

      <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Sector performance</h3>
      <div className="nepse-grid-3">
        {m.sectors.map((sec) => (
          <div key={sec.name} className="nepse-card">
            <div className="strong">{sec.name}</div>
            <div className="nepse-row" style={{ justifyContent: "space-between", marginTop: 4 }}>
              <span style={{ color: "var(--text-faint)", fontSize: "0.8rem" }}>{sec.count} listed</span>
              <span className={`nepse-badge ${sec.dayChange >= 0 ? "up" : "down"}`}>{fmtPct(sec.dayChange)}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
