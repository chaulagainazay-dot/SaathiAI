"use client";
// Sector heatmap — the drawing half. All geometry and bucketing comes from
// lib/nepse/heatmap.js; this file decides pixels and colours and nothing else.
//
// Two rules it exists to keep:
//   - A tile that could not be SIZED is not drawn as a small tile. It is listed
//     below the map by name, because a 2px rectangle and "we have no turnover for
//     this symbol" look identical and mean opposite things.
//   - A tile whose CHANGE is unknown is drawn at its true size with no colour.
//     Its area is a fact about turnover and does not depend on the change.

import { useMemo, useState } from "react";
import { HEATMAP_BUCKET, heatmapModel, squarify } from "@/lib/nepse/heatmap";
import { INDICATOR_STATUS } from "@/lib/nepse/indicators";
import { fmtNum, fmtPct, fmtCompactRs } from "@/lib/nepse/format";

const W = 960;
const H = 520;
const GAP = 2;
const LABEL = 16;

const FILL = {
  [HEATMAP_BUCKET.STRONG_UP]: "#186f42",
  [HEATMAP_BUCKET.UP]: "#2f9c63",
  [HEATMAP_BUCKET.SLIGHT_UP]: "#8fc8a9",
  [HEATMAP_BUCKET.NEUTRAL]: "#9aa79f",
  [HEATMAP_BUCKET.SLIGHT_DOWN]: "#e0a49b",
  [HEATMAP_BUCKET.DOWN]: "#c4584a",
  [HEATMAP_BUCKET.STRONG_DOWN]: "#8f2f24",
};
// Not a colour in the scale: an unknown change is hatched, so it reads as
// "we don't know" rather than as a very small move.
const UNKNOWN_FILL = "url(#nepse-hm-unknown)";

const inset = (r) => ({
  x: r.x + GAP / 2, y: r.y + GAP / 2,
  w: Math.max(0, r.w - GAP), h: Math.max(0, r.h - GAP),
});

export default function Heatmap({ rows, weightBy = "turnover", onSelect }) {
  const [hover, setHover] = useState(null);
  const model = useMemo(() => heatmapModel(rows, { weightBy }), [rows, weightBy]);

  const laid = useMemo(() => {
    const sizeable = model.sectors.filter((s) => s.weight !== null);
    const blocks = squarify(sizeable, W, H);
    return blocks.filter((b) => b.placed).map((b) => {
      const box = inset(b);
      const inner = { x: box.x, y: box.y + LABEL, w: box.w, h: Math.max(0, box.h - LABEL) };
      const tiles = squarify(b.tiles, inner.w, inner.h)
        .filter((t) => t.placed)
        .map((t) => ({ ...t, x: t.x + inner.x, y: t.y + inner.y }));
      return { ...b, box, tiles };
    });
  }, [model]);

  if (model.status === INDICATOR_STATUS.INSUFFICIENT_HISTORY) {
    return <div className="nepse-empty">No session rows to lay out yet.</div>;
  }
  if (model.status === INDICATOR_STATUS.FIELD_UNAVAILABLE) {
    return (
      <div className="nepse-callout">
        <strong>The map cannot be drawn.</strong> {model.note} — every tile&apos;s
        area is a claim about how much a symbol traded, and none of them can be made.
      </div>
    );
  }

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label={`Sector heatmap of ${model.observations} symbols sized by ${weightBy}`}
           style={{ display: "block", borderRadius: 8, background: "var(--surface-2)" }}>
        <defs>
          <pattern id="nepse-hm-unknown" width="6" height="6" patternUnits="userSpaceOnUse"
                   patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--surface-2)" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--text-faint)" strokeWidth="2" />
          </pattern>
        </defs>
        {laid.map((s) => (
          <g key={s.sector}>
            <text x={s.box.x + 3} y={s.box.y + 11} fontSize="10" fill="var(--text-dim)"
                  fontFamily="'IBM Plex Mono', monospace">
              {/* Share of market turnover, NOT a price move. fmtPct signs it, and
                  "+56.22%" beside a sector name in a trading UI reads as a rally. */}
              {s.box.w > 90
                ? `${s.sector} · ${fmtNum((s.share ?? 0) * 100, 1)}% of turnover`
                : ""}
            </text>
            {s.tiles.map((t) => (
              <g key={t.symbol}
                 onMouseEnter={() => setHover({ ...t, sector: s.sector })}
                 onMouseLeave={() => setHover(null)}
                 onClick={() => onSelect?.(t.symbol)}
                 style={{ cursor: onSelect ? "pointer" : "default" }}>
                <rect x={t.x} y={t.y} width={Math.max(0, t.w - 1)} height={Math.max(0, t.h - 1)}
                      fill={t.bucket ? FILL[t.bucket] : UNKNOWN_FILL} rx="2">
                  <title>
                    {`${t.symbol} · ${t.changePct === null ? "change unknown" : fmtPct(t.changePct)} · ${weightBy} ${fmtCompactRs(t.weight)}`}
                  </title>
                </rect>
                {t.w > 42 && t.h > 18 ? (
                  <text x={t.x + 4} y={t.y + 13} fontSize="10" fill="#fff"
                        fontFamily="'IBM Plex Mono', monospace" pointerEvents="none">
                    {t.symbol}
                  </text>
                ) : null}
              </g>
            ))}
          </g>
        ))}
      </svg>

      <div className="nepse-row" style={{ justifyContent: "space-between", marginTop: "0.5rem",
                                          fontSize: "0.75rem", color: "var(--text-faint)" }}>
        <span>
          {hover
            ? `${hover.symbol} · ${hover.sector} · ${hover.changePct === null ? "change unknown" : fmtPct(hover.changePct)}`
            : `${model.observations} sized by ${weightBy}`}
        </span>
        <span className="nepse-row" style={{ gap: "0.3rem", alignItems: "center" }}>
          <span>−5%</span>
          {[HEATMAP_BUCKET.STRONG_DOWN, HEATMAP_BUCKET.DOWN, HEATMAP_BUCKET.SLIGHT_DOWN,
            HEATMAP_BUCKET.NEUTRAL, HEATMAP_BUCKET.SLIGHT_UP, HEATMAP_BUCKET.UP,
            HEATMAP_BUCKET.STRONG_UP].map((b) => (
            <i key={b} style={{ width: 16, height: 10, background: FILL[b], display: "inline-block" }} />
          ))}
          <span>+5%</span>
        </span>
      </div>

      {model.unweighted.length > 0 && (
        <p style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "0.5rem" }}>
          {model.unweighted.length} symbol{model.unweighted.length === 1 ? "" : "s"} could
          not be sized and {model.unweighted.length === 1 ? "is" : "are"} not on the map:{" "}
          {model.unweighted.slice(0, 12).map((u) => u.symbol).join(", ")}
          {model.unweighted.length > 12 ? ` and ${model.unweighted.length - 12} more` : ""}.
          A zero-area tile would be indistinguishable from a symbol that is not listed.
        </p>
      )}
    </>
  );
}
