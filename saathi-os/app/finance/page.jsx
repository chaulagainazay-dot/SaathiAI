"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { finance } from "@/lib/data";
import { color } from "@/lib/departments";
import { Panel, Eyebrow, Pill, Bar, Ring, Counter, Dot } from "@/components/ui";
import MobileFinance from "@/components/mobile/MobileFinance";

const GOLD = color("FINANCE");
const usd = (n) => "$" + n.toLocaleString("en-US");

function Sparkline({ data, w = 640, h = 150, stroke = GOLD }) {
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, h - v * h]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = `${line} L ${w} ${h} L 0 ${h} Z`;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#fill)" />
      <motion.path d={line} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: "easeInOut" }}
        style={{ filter: `drop-shadow(0 0 6px ${stroke}66)` }} />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3.5" fill={stroke} />
    </svg>
  );
}

export default function Finance() {
  const [tab, setTab] = useState("Portfolio");
  return (
    <>
    <div className="only-mobile"><MobileFinance /></div>
    <div className="only-desktop" style={{ maxWidth: 1620, margin: "0 auto" }}>
      {/* tabs */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 26 }}>
        {finance.tabs.map((t) => (
          <button key={t} onClick={() => setTab(t)}>
            {t === tab
              ? <Pill color={GOLD} filled={0.18}>{t}</Pill>
              : <span className="mono" style={{ fontSize: 10, letterSpacing: "0.1em", padding: "6px 10px",
                  color: "var(--color-ink-400)", textTransform: "uppercase", cursor: "pointer" }}>{t}</span>}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "440px 1fr 330px", gap: 28 }}>
        {/* left: health + allocation */}
        <Panel style={{ padding: 32, display: "flex", flexDirection: "column", alignItems: "center" }}>
          <Ring value={0.91} color={GOLD} size={210} label={finance.health} sub="Portfolio Health" />
          <div style={{ width: "100%", marginTop: 28 }}>
            <Eyebrow>Allocation</Eyebrow>
            <div style={{ marginTop: 14 }}>
              {finance.allocation.map((a) => (
                <Bar key={a.name} frac={a.frac} color={color(a.dept)} label={a.name} value={`${Math.round(a.frac * 100)}%`} />
              ))}
            </div>
          </div>
        </Panel>

        {/* center: equity + KPIs */}
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <Panel style={{ padding: 28 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
              <Eyebrow>Portfolio Value · 90D</Eyebrow>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, margin: "8px 0 18px" }}>
              <span className="display" style={{ fontSize: 34 }}>
                <Counter to={finance.value} format={(v) => usd(Math.round(v))} />
              </span>
              <span className="mono" style={{ color: "#4FD07A", fontSize: 12 }}>▲ {finance.valueDelta}%</span>
            </div>
            <Sparkline data={finance.curve} />
          </Panel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 18 }}>
            {finance.kpis.map((k, i) => (
              <Panel key={k.k} delay={0.05 * i} style={{ padding: 22 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <Eyebrow>{k.k}</Eyebrow><Dot color={color(k.dept)} size={7} ring={false} />
                </div>
                <div className="display" style={{ fontSize: 30, marginTop: 10 }}>{k.v}</div>
              </Panel>
            ))}
          </div>
        </div>

        {/* right: approvals + governance + research */}
        <Panel style={{ padding: 28 }}>
          <Eyebrow>Awaiting Your Approval</Eyebrow>
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            {finance.approvals.map((a) => (
              <div key={a.title} className="glass-soft" style={{ padding: 16 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: "var(--color-ink-100)" }}>{a.title}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
                  <Pill color="#4FD07A" filled={0.18}>{a.verdict}</Pill>
                  <span className="mono" style={{ fontSize: 10, color: "var(--color-ink-400)" }}>{a.meta}</span>
                  <span style={{ marginLeft: "auto" }}><Pill color={GOLD} filled={0.16}>Approve</Pill></span>
                </div>
              </div>
            ))}
          </div>
          <div style={{ height: 1, background: "var(--color-line)", margin: "22px 0" }} />
          <Eyebrow>Governance</Eyebrow>
          <p style={{ fontSize: 12.5, color: "var(--color-ink-200)", margin: "10px 0 12px" }}>
            All trades require human approval.
          </p>
          <Pill color={color("MISSION")} filled={0.12}>L4 · Enforced</Pill>
          <div style={{ height: 1, background: "var(--color-line)", margin: "22px 0" }} />
          <Eyebrow>Research Accuracy</Eyebrow>
          <div style={{ marginTop: 14 }}>
            {finance.research.map((r) => (
              <Bar key={r.name} frac={r.value} color={color(r.dept)} label={r.name} value={`${Math.round(r.value * 100)}%`} />
            ))}
          </div>
        </Panel>
      </div>
    </div>
    </>
  );
}
