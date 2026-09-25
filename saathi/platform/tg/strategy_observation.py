"""STRATEGY-OBSERVATION-1 — the canonical shadow → attribution → monitoring bridge.

Three certified layers already exist and none of them is duplicated here:

  SHADOW-TRADING-1            durable session, fills, counterfactuals, reconciliation
  PERFORMANCE-ATTRIBUTION-V2  gross/net, cost decomposition, turnover, drawdown
  STRATEGY-MONITORING-1       the Observation type and every threshold

This module is the wiring between the last two and nothing more. It computes no
performance number that attribution already computes, holds no threshold, and
reaches no store it does not read.

THE LINE THIS FILE MUST NOT CROSS: an adapter supplies EVIDENCE; the monitoring
policy supplies INTERPRETATION. Nothing here decides whether a number is good.

MISSING DATA IS PRESERVED, NEVER FILLED. If attribution says the benchmark is
unavailable, the Observation carries None — not zero. A zero would be read by the
monitor as a real measurement of a benchmark that returned nothing, which is a
different and false claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from saathi.platform.tg.attribution_source import (
    counterfactuals_from_session,
    records_from_session,
)
from saathi.platform.tg.attribution_v2 import (
    AttributionStatus,
    performance_attribution_report,
)
from saathi.platform.tg.strategy_monitor import Observation
from saathi.platform.trading_models import D

ADAPTER_VERSION = "strategy-observation/v1.0.0"


class AdapterStatus(str, Enum):
    """How much of the Observation the sources could actually support."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_SOURCE_DATA = "INSUFFICIENT_SOURCE_DATA"
    AMBIGUOUS_PROVENANCE = "AMBIGUOUS_PROVENANCE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"


@dataclass(frozen=True)
class AdapterResult:
    """The Observation plus an honest account of what could not be filled."""

    observation: Observation
    status: str
    #: ONE field, because the session records one. The qualification envelope
    #: separates strategy_id from strategy_version; a shadow session does not,
    #: and emitting both from a single column would imply a distinction the
    #: source cannot support.
    strategy_version: str | None
    unavailable_fields: tuple = ()
    detail: str | None = None
    adapter_version: str = ADAPTER_VERSION
    attribution_report_id: str | None = None
    #: Permanent: this adapter reads. It never acts.
    authorizes_execution: bool = False


def resolve_cutoff_seq(store, session_id: str, *, as_of: str | None = None) -> int | None:
    """Translate a time cutoff into this session's canonical sequence bound.

    Seq is the ordering the session actually guarantees; `observed_at` is metadata
    on events. An event with no `observed_at` cannot be proven to precede the
    cutoff, so it is EXCLUDED — failing closed, because including it would be a
    guess that leaks a possibly-future record into a point-in-time read.
    """
    if as_of is None:
        return None
    highest = None
    for e in store.events(session_id):  # events() is unbounded by design
        observed = e.get("observed_at")
        if observed is None:
            continue
        if str(observed) <= str(as_of):
            highest = e["seq"] if highest is None else max(highest, e["seq"])
    # No qualifying event means nothing was known by then — not "everything".
    return -1 if highest is None else highest


def observation_from_shadow(
    store,
    session_id: str,
    *,
    as_of: str | None = None,
    max_seq: int | None = None,
    mark_prices: dict | None = None,
    average_portfolio_value=None,
    equity_path=None,
    benchmark_return=None,
    current_regime: str | None = None,
    regimes_seen: tuple = (),
    data_stale: bool = False,
    data_gap: bool = False,
    strategy_id: str | None = None,
) -> AdapterResult:
    """Build a monitoring Observation from one shadow session.

    Deterministic: no clock is read here. The caller supplies the cutoff, either
    as a sequence bound or as a timestamp resolved against the session's own
    recorded events. Called twice on unchanged data it returns the same thing.
    """
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"unknown shadow session: {session_id}")

    # MODE IS CARRIED, NEVER DEFAULTED. A session whose mode could not be read
    # must not arrive at the monitor labelled SHADOW: that would present replayed
    # or paper evidence as live observation.
    mode = session.get("mode")
    if not mode:
        raise ValueError(f"shadow session {session_id} has no mode; refusing to assume one")

    if max_seq is not None and as_of is not None:
        raise ValueError("pass a sequence bound or a timestamp, not both")
    cutoff = max_seq if max_seq is not None else resolve_cutoff_seq(store, session_id, as_of=as_of)

    # Reconciliation first: an unreconciled book cannot support a performance
    # claim, and the monitor must be told that rather than shown numbers.
    #
    # THE ONE SIDE EFFECT IN THIS MODULE, AND IT IS NOT THE ADAPTER'S DECISION:
    # `reconcile` is the certified check, and on finding a broken book it flips
    # the session to RECONCILIATION_REQUIRED itself. That is SHADOW-TRADING-1
    # failing closed on its own history. Recomputed from that history every time,
    # so repeated reads converge rather than accumulate; a test pins that.
    recon = store.reconcile(session_id)
    reconciliation_ok = bool(recon.get("ok"))

    if recon.get("state") is None:
        # The book could not be rebuilt from its own history at all — an oversell,
        # say. Every downstream layer would raise on the same derivation, so this
        # returns the failure as a STATUS rather than an exception: a monitoring
        # caller must be able to record "this session is unreadable" without
        # crashing, and must not receive performance numbers derived from a book
        # that does not add up.
        return AdapterResult(
            observation=Observation(
                mode=mode,
                window_start=session.get("started_at"),
                window_end=session.get("ended_at"),
                reconciliation_ok=False,
            ),
            status=AdapterStatus.RECONCILIATION_REQUIRED.value,
            strategy_version=strategy_id or session.get("strategy_version"),
            unavailable_fields=("net_return", "cost_drag", "turnover_ratio",
                                "max_drawdown", "benchmark_return"),
            detail="; ".join(recon.get("problems") or ()) or "portfolio not derivable",
        )

    fills = store.fills(session_id, max_seq=cutoff)
    events = [e for e in store.events(session_id)
              if cutoff is None or e["seq"] <= cutoff]

    # The window is settled BEFORE the report so the report's period and the
    # Observation's window describe the same span. A sequence-bounded read has no
    # `as_of`, and a report labelled with an open period would misdescribe it.
    window_start = session.get("started_at")
    window_end = as_of or _last_observed_at(events) or session.get("ended_at")

    records = records_from_session(
        store, session_id, strategy_id=strategy_id,
        mark_prices=mark_prices, max_seq=cutoff,
    )
    cfs = counterfactuals_from_session(
        store, session_id, strategy_id=strategy_id, max_seq=cutoff,
    )

    report = performance_attribution_report(
        records,
        counterfactuals=cfs,
        equity_path=equity_path,
        average_portfolio_value=average_portfolio_value,
        period_start=window_start,
        period_end=window_end,
        benchmark_version=session.get("benchmark"),
        policy_versions=session.get("policy_versions") or {},
        mode=mode,
    )

    unavailable: list[str] = []

    # ── net return ──────────────────────────────────────────────────────────
    # ACCOUNTING evidence only. Counterfactual estimates of what a blocked trade
    # would have earned are never folded into an observed performance number.
    net_return = None
    totals = (report.get("accounting") or {}).get("totals") or {}
    opening = session.get("opening_cash")
    if totals.get("net_pnl") is not None and opening not in (None, ""):
        opening_cash = D(opening)
        if opening_cash > 0:
            net_return = D(totals["net_pnl"]) / opening_cash
    if net_return is None:
        unavailable.append("net_return")

    # ── costs ───────────────────────────────────────────────────────────────
    # `total_cost` survives a DATA_INSUFFICIENT split, so the drag can be known
    # while its fee/spread/slippage breakdown is not. Two separate claims.
    costs = report.get("costs") or {}
    cost_ok = costs.get("status") == AttributionStatus.OK.value
    cost_drag = costs.get("total_cost")
    if cost_drag is None:
        unavailable.append("cost_drag")
    if not cost_ok:
        unavailable.append("cost_detail")

    # ── turnover ────────────────────────────────────────────────────────────
    turn = report.get("turnover") or {}
    turnover_ratio = (turn.get("turnover_ratio")
                      if turn.get("status") == AttributionStatus.OK.value else None)
    if turnover_ratio is None:
        unavailable.append("turnover_ratio")

    # ── drawdown ────────────────────────────────────────────────────────────
    # Attribution reports drawdown only from an equity path. The session persists
    # no valuation series, so without a caller-supplied path it stays absent
    # rather than being approximated from cost basis — marking open positions at
    # cost would describe a flat equity curve the portfolio never had.
    risk = report.get("risk") or {}
    max_drawdown = risk.get("max_drawdown")
    if max_drawdown is None:
        unavailable.append("max_drawdown")

    # BENCHMARK_UNAVAILABLE STAYS None. Zero would read to the monitor as a real
    # measurement of a flat benchmark, and underperformance would be scored
    # against a number nobody observed.
    if benchmark_return is None:
        unavailable.append("benchmark_return")

    # ── provenance ──────────────────────────────────────────────────────────
    by_strategy = report.get("by_strategy") or {}
    ambiguous = by_strategy.get("status") == AttributionStatus.AMBIGUOUS_PROVENANCE.value
    resolved_strategy = strategy_id or session.get("strategy_version")

    # ── counts and window ───────────────────────────────────────────────────
    closed_trades = _closed_trades(fills)
    signals = sum(1 for e in events if str(e.get("kind", "")).upper() == "SIGNAL")
    observed_seconds = _elapsed_seconds(window_start, window_end)

    observation = Observation(
        mode=mode,
        window_start=window_start,
        window_end=window_end,
        observed_seconds=observed_seconds,
        closed_trades=closed_trades,
        signals=signals,
        max_drawdown=max_drawdown,
        net_return=net_return,
        benchmark_return=None if benchmark_return is None else D(benchmark_return),
        cost_drag=cost_drag,
        cost_detail_available=cost_ok,
        turnover_ratio=turnover_ratio,
        regimes_seen=tuple(regimes_seen),
        current_regime=current_regime,
        data_stale=bool(data_stale),
        data_gap=bool(data_gap),
        reconciliation_ok=reconciliation_ok,
        attribution_report_id=report.get("report_id"),
    )

    status = _status(reconciliation_ok, data_stale or data_gap, ambiguous,
                     unavailable, len(fills))
    return AdapterResult(
        observation=observation,
        status=status,
        strategy_version=resolved_strategy,
        unavailable_fields=tuple(dict.fromkeys(unavailable)),
        detail=by_strategy.get("detail"),
        attribution_report_id=report.get("report_id"),
    )


def _status(recon_ok, data_bad, ambiguous, unavailable, fills) -> str:
    # Order matters: an untrustworthy observation outranks an incomplete one.
    # A partial-but-sound reading and a complete-but-wrong one are not the same
    # problem, and the monitor treats them differently.
    if not recon_ok:
        return AdapterStatus.RECONCILIATION_REQUIRED.value
    if data_bad:
        return AdapterStatus.DATA_QUALITY_BLOCKED.value
    if ambiguous:
        return AdapterStatus.AMBIGUOUS_PROVENANCE.value
    if fills == 0:
        return AdapterStatus.INSUFFICIENT_SOURCE_DATA.value
    return AdapterStatus.PARTIAL.value if unavailable else AdapterStatus.COMPLETE.value


def _closed_trades(fills) -> int:
    """A closed trade is a round trip, not a fill.

    Counting fills would report a single unclosed buy as a completed trade and
    let a strategy look sufficiently observed after one purchase — the exact
    reading STRATEGY-MONITORING-1 uses to decide it has enough evidence.
    """
    held: dict[str, Decimal] = {}
    closed = 0
    for f in fills:
        sym = f["symbol"]
        qty = D(f["quantity"])
        signed = -qty if str(f["side"]).upper() == "SELL" else qty
        before = held.get(sym, Decimal("0"))
        after = before + signed
        # A position returning to flat, or crossing through it, closes a trade.
        if before != 0 and (after == 0 or (before > 0) != (after > 0)):
            closed += 1
        held[sym] = after
    return closed


def _last_observed_at(events) -> str | None:
    stamps = [e.get("observed_at") for e in events if e.get("observed_at")]
    return max(stamps) if stamps else None


def _elapsed_seconds(start: str | None, end: str | None) -> int:
    """Elapsed ISO-8601 seconds without importing a clock.

    Parsed arithmetically rather than with `datetime` so this module holds no
    time source at all — the same structural guarantee STRATEGY-MONITORING-1
    makes, and a test asserts the import is absent.
    """
    a, b = _epoch(start), _epoch(end)
    if a is None or b is None or b < a:
        return 0
    return int(b - a)


def _epoch(stamp: str | None) -> int | None:
    if not stamp or not isinstance(stamp, str) or len(stamp) < 19:
        return None
    try:
        y, mo, d = int(stamp[0:4]), int(stamp[5:7]), int(stamp[8:10])
        h, mi, se = int(stamp[11:13]), int(stamp[14:16]), int(stamp[17:19])
    except ValueError:
        return None
    # Days from a fixed civil epoch (Howard Hinnant's algorithm) — pure arithmetic.
    yy = y - (1 if mo <= 2 else 0)
    era = (yy if yy >= 0 else yy - 399) // 400
    yoe = yy - era * 400
    doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400 + h * 3600 + mi * 60 + se
