// Market-wide aggregates — breadth, gainers, losers, sector performance. PURE.
//
// Everything here is computed from the daily archive's last two completed sessions,
// so it needs no source SaathiOS does not already have. The honesty constraints:
//
//   - A symbol with no usable prior close is EXCLUDED, never counted as unchanged.
//     Treating "unknown" as "flat" would quietly inflate the unchanged bucket and
//     understate breadth.
//   - Every aggregate reports the universe it actually covered. "12 of 372 listed"
//     is a different claim from "the market", and the difference must be visible.
//   - A sector with too few usable members reports INSUFFICIENT rather than an
//     average of one stock presented as a sector move.

/** A sector needs at least this many usable members before its average means anything. */
export const MIN_SECTOR_MEMBERS = 2;

/**
 * NEPSE's daily circuit limit. A move beyond it cannot be a trade move, so on
 * UNADJUSTED data it almost always means a corporate action — a book closure,
 * bonus or rights issue repricing the stock overnight. Ranking that as the day's
 * top loser would be wrong twice over: the holder lost nothing, and the number is
 * not a return. Flagged, not deleted; the caller decides.
 */
export const CIRCUIT_LIMIT_PCT = 10;

/** The bucket for symbols whose sector we do not actually know. Not a sector. */
export const UNCLASSIFIED = "Unclassified";

/**
 * Per-symbol change across the last two completed sessions.
 * @param entries [{symbol, sector, bars}] — bars are typed archive bars
 */
export function sessionChanges(entries) {
  const rows = [];
  const excluded = [];
  for (const e of entries || []) {
    const usable = (e.bars || []).filter(
      (b) => b?.trusted?.close !== false && typeof b?.close === "number" && b.date,
    );
    if (usable.length < 2) {
      excluded.push({ symbol: e.symbol, reason: "INSUFFICIENT_HISTORY" });
      continue;
    }
    const last = usable[usable.length - 1];
    const prior = usable[usable.length - 2];
    if (!prior.close) {
      excluded.push({ symbol: e.symbol, reason: "ZERO_PRIOR_CLOSE" });
      continue;
    }
    const change = +(last.close - prior.close).toFixed(4);
    const changePct = +((change / prior.close) * 100).toFixed(2);
    rows.push({
      symbol: e.symbol,
      sector: e.sector || UNCLASSIFIED,
      close: last.close,
      priorClose: prior.close,
      change,
      changePct,
      // Beyond the circuit this is a repricing, not a return.
      circuitExceeded: Math.abs(changePct) > CIRCUIT_LIMIT_PCT,
      volume: typeof last.volume === "number" ? last.volume : null,
      turnover: typeof last.turnover === "number" ? last.turnover : null,
      date: last.date,
      priorDate: prior.date,
    });
  }
  return { rows, excluded };
}

/** Advancing / declining / unchanged — over symbols we could actually measure. */
export function breadth(rows) {
  let advancing = 0;
  let declining = 0;
  let unchanged = 0;
  for (const r of rows) {
    if (r.changePct > 0) advancing += 1;
    else if (r.changePct < 0) declining += 1;
    else unchanged += 1;
  }
  const measured = rows.length;
  return {
    advancing,
    declining,
    unchanged,
    measured,
    // Ratio is undefined rather than Infinity when nothing declined.
    advanceDeclineRatio: declining > 0 ? +(advancing / declining).toFixed(2) : null,
    mood: measured === 0 ? "UNKNOWN"
      : advancing > declining * 1.5 ? "BULLISH"
      : declining > advancing * 1.5 ? "BEARISH"
      : "MIXED",
  };
}

/**
 * Top movers. Ties break on turnover so a thin 10% move ranks below a traded one.
 * Circuit-exceeding rows are held back into `repriced` rather than ranked: a
 * bonus-issue adjustment is not the day's biggest loser, and putting it at the top
 * of a losers table states something false about what happened to holders.
 */
export function topMovers(rows, limit = 8) {
  const repriced = rows.filter((r) => r.circuitExceeded);
  const tradeable = rows.filter((r) => !r.circuitExceeded);
  const byPct = (dir) => [...tradeable]
    .filter((r) => (dir > 0 ? r.changePct > 0 : r.changePct < 0))
    .sort((a, b) => (dir > 0 ? b.changePct - a.changePct : a.changePct - b.changePct)
      || (b.turnover ?? 0) - (a.turnover ?? 0))
    .slice(0, limit);
  return { gainers: byPct(1), losers: byPct(-1), repriced };
}

/** Most-traded by turnover, then by volume — only where actually reported. */
export function activityLeaders(rows, limit = 8) {
  return {
    byTurnover: [...rows].filter((r) => r.turnover !== null && r.turnover > 0)
      .sort((a, b) => b.turnover - a.turnover).slice(0, limit),
    byVolume: [...rows].filter((r) => r.volume !== null && r.volume > 0)
      .sort((a, b) => b.volume - a.volume).slice(0, limit),
  };
}

/**
 * Sector performance.
 * Reports BOTH a simple mean and a turnover-weighted mean where turnover exists —
 * a sector's unweighted average can be dominated by an illiquid outlier, and saying
 * which is which is more useful than silently picking one.
 */
export function sectorPerformance(rows, { minMembers = MIN_SECTOR_MEMBERS } = {}) {
  const bySector = new Map();
  for (const r of rows) {
    if (!bySector.has(r.sector)) bySector.set(r.sector, []);
    bySector.get(r.sector).push(r);
  }

  const out = [];
  for (const [sector, members] of bySector) {
    if (members.length < minMembers) {
      out.push({
        sector,
        members: members.length,
        status: "INSUFFICIENT_MEMBERS",
        changePct: null,
        weightedChangePct: null,
        note: `only ${members.length} measurable member(s) — not reported as a sector move`,
      });
      continue;
    }
    const mean = members.reduce((a, m) => a + m.changePct, 0) / members.length;
    const withTurnover = members.filter((m) => m.turnover !== null && m.turnover > 0);
    const totalTurnover = withTurnover.reduce((a, m) => a + m.turnover, 0);
    const weighted = totalTurnover > 0
      ? withTurnover.reduce((a, m) => a + m.changePct * m.turnover, 0) / totalTurnover
      : null;

    out.push({
      sector,
      members: members.length,
      // The unclassified bucket is the rest of the market, not a sector. It keeps
      // its average — it is a real average — but never claims to be a sector move.
      status: sector === UNCLASSIFIED ? "UNCLASSIFIED" : "OK",
      changePct: +mean.toFixed(2),
      weightedChangePct: weighted === null ? null : +weighted.toFixed(2),
      turnover: totalTurnover > 0 ? Math.round(totalTurnover) : null,
      advancing: members.filter((m) => m.changePct > 0).length,
      declining: members.filter((m) => m.changePct < 0).length,
    });
  }
  return out.sort((a, b) => (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity));
}

/** Total reported turnover and volume — sums only what was actually reported. */
export function marketActivity(rows) {
  const withT = rows.filter((r) => r.turnover !== null && r.turnover > 0);
  const withV = rows.filter((r) => r.volume !== null && r.volume > 0);
  return {
    totalTurnover: withT.length ? Math.round(withT.reduce((a, r) => a + r.turnover, 0)) : null,
    totalVolume: withV.length ? Math.round(withV.reduce((a, r) => a + r.volume, 0)) : null,
    turnoverReportedBy: withT.length,
    volumeReportedBy: withV.length,
  };
}

/**
 * One market snapshot from archive entries.
 * `listedTotal` is the size of the real market, so coverage can never be mistaken
 * for completeness.
 */
export function marketSummary(entries, { listedTotal = null, limit = 8 } = {}) {
  const { rows, excluded } = sessionChanges(entries);
  const b = breadth(rows);
  const movers = topMovers(rows, limit);
  const leaders = activityLeaders(rows, limit);
  const sectors = sectorPerformance(rows);
  const activity = marketActivity(rows);
  const asOf = rows.length ? rows[0].date : null;
  const priorDate = rows.length ? rows[0].priorDate : null;

  return {
    asOf,
    priorDate,
    basis: "LAST_COMPLETED_SESSION",
    coverage: {
      measured: rows.length,
      excluded: excluded.length,
      listedTotal,
      // Explicit so a partial universe is never presented as "the market".
      isFullMarket: listedTotal !== null && rows.length >= listedTotal,
    },
    breadth: b,
    gainers: movers.gainers,
    losers: movers.losers,
    // Held out of the rankings above, but shown — an unexplained gap would be worse.
    repriced: movers.repriced,
    circuitLimitPct: CIRCUIT_LIMIT_PCT,
    mostTraded: leaders.byTurnover,
    mostActive: leaders.byVolume,
    sectors,
    activity,
    excluded,
  };
}
