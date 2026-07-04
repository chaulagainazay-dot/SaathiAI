"use client";
import { finance } from "@/lib/data";
import { color } from "@/lib/departments";
import { Eyebrow, Counter } from "@/components/ui";

const usd = (n) => "$" + n.toLocaleString("en-US");

function Stat({ label, value, accent }) {
  return (
    <div className="m-card" style={{ padding: 16 }}>
      <Eyebrow>{label}</Eyebrow>
      <div className="display" style={{ fontSize: 26, marginTop: 6, color: accent || "var(--color-ink-100)" }}>{value}</div>
    </div>
  );
}

export default function MobileFinance() {
  return (
    <div className="m-page">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Stat label="Portfolio Health" value={<Counter to={finance.health} />} accent={color("FINANCE")} />
        <Stat label="Today's Change" value={`▲ ${finance.valueDelta}%`} accent="#4FD07A" />
      </div>

      <div className="m-card">
        <Eyebrow>Awaiting Approval</Eyebrow>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
          {finance.approvals.map((a) => (
            <div key={a.title} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{a.title}</div>
                <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-400)", marginTop: 2 }}>{a.verdict} · {a.meta}</div>
              </div>
              <button style={{ padding: "8px 16px", borderRadius: 999, fontSize: 11, cursor: "pointer",
                color: color("FINANCE"), background: `${color("FINANCE")}22`, border: `1px solid ${color("FINANCE")}55` }}>Approve</button>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Stat label="Cash" value={usd(8200)} />
        <Stat label="Top Opportunity" value="Bittensor" accent={color("OPPORTUNITY")} />
      </div>

      <div className="m-card" style={{ borderColor: `${color("FINANCE")}44` }}>
        <Eyebrow style={{ color: color("FINANCE") }}>Rebalance Recommendation</Eyebrow>
        <p style={{ fontSize: 14, color: "var(--color-ink-200)", marginTop: 10, lineHeight: 1.5 }}>
          Reduce crypto by 8% — allocation is over target and concentration is rising.
        </p>
        <div className="mono" style={{ fontSize: 10, color: "var(--color-ink-500)", marginTop: 10 }}>
          recommendation only · L4 approval required to execute
        </div>
      </div>
    </div>
  );
}
