"""M62.4 — deterministic backtest engine (simulation only).

Ties the pieces together into ONE reproducible run:

    validate (structural) → data-quality gate → feature generation → per-bar
    decision (look-ahead-guarded) → next-bar fill → accounting → metrics → manifest

Determinism: for a fixed (strategy hash, dataset hash, engine version, config, seed)
the ``result_hash`` is identical. No wall-clock, no RNG (the seed only varies labels),
no network, no filesystem, no broker. A ``SimulatedOrder`` never becomes a platform
``OrderIntent`` and never reaches ExecutionGateway.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from saathi.platform.market_data.models import MDBar, MarketDataQuality
from saathi.platform.market_data.quality import classify_series
from saathi.platform.strategy.models import (
    StrategyDefinition, DatasetReference, CostModel, REALISTIC_COST, EquityPoint,
    ENGINE_VERSION, FEATURE_VERSION, SimOrderStatus, D, q2, _canonical,
)
from saathi.platform.strategy.features import BacktestContext, compute_all, LookAheadViolation
from saathi.platform.strategy.signals import evaluate_signals
from saathi.platform.strategy.sizing import target_quantity, SizingError
from saathi.platform.strategy.execution_model import simulate_fill
from saathi.platform.strategy.accounting import PortfolioAccountant
from saathi.platform.strategy import metrics as metrics_mod
from saathi.platform.strategy.validation import is_runnable


# quality classes that BLOCK a run entirely (structurally invalid data)
BLOCKING_QUALITY = frozenset({
    MarketDataQuality.INVALID_PRICE, MarketDataQuality.INVALID_TIMESTAMP,
    MarketDataQuality.OUT_OF_ORDER, MarketDataQuality.DUPLICATE,
})


@dataclass
class BacktestResult:
    status: str                       # COMPLETE | FAILED | REJECTED
    reason: str
    equity_curve: list[EquityPoint]
    fills: list[Any]
    metrics: dict[str, Any]
    quality_summary: dict[str, Any]
    invariant_errors: list[str]
    result_hash: str
    manifest: dict[str, Any]
    max_accessed_epoch: float = -1.0
    look_ahead_ok: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "status": self.status, "reason": self.reason,
            "equity_points": len(self.equity_curve), "fills": len(self.fills),
            "metrics": {k: v.to_public() for k, v in self.metrics.items()},
            "quality_summary": self.quality_summary, "invariant_errors": self.invariant_errors,
            "result_hash": self.result_hash, "manifest": self.manifest,
            "look_ahead_ok": self.look_ahead_ok,
        }


def _dataset_hash(bars: list[MDBar]) -> str:
    # quality-INDEPENDENT projection: classifying a dataset must not change its hash
    proj = [{"i": b.instrument, "tf": b.timeframe.value, "s": b.start_time.timestamp(),
             "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close), "v": str(b.volume)}
            for b in bars]
    return hashlib.sha256(_canonical(proj).encode()).hexdigest()


def quality_summary(bars: list[MDBar], *, now_epoch: float) -> dict[str, Any]:
    from datetime import datetime, timezone
    now = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    summ = classify_series(bars, now=now)
    counts: dict[str, int] = {}
    blocking = 0
    for b in bars:
        counts[b.quality.value] = counts.get(b.quality.value, 0) + 1
        if b.quality in BLOCKING_QUALITY:
            blocking += 1
    return {"counts": counts, "blocking": blocking, "series": summ}


def run_backtest(
    defn: StrategyDefinition,
    bars: list[MDBar],
    *,
    starting_cash: Decimal = Decimal("100000"),
    cost: CostModel | None = None,
    seed: int = 0,
    benchmark_bars: list[MDBar] | None = None,
    parameters: dict[str, Any] | None = None,
    quantity_precision: int = 4,
    probe: Callable[[BacktestContext], None] | None = None,
    calendar: str = "DEFAULT_24_5",
    strict_quality: bool = True,
) -> BacktestResult:
    import copy as _copy
    cost = cost or defn.cost_model or REALISTIC_COST
    parameters = parameters or {}
    # copy so quality classification never mutates the caller's bars (determinism)
    as_received = _copy.deepcopy(bars)
    # classify quality on the AS-RECEIVED order so out-of-order / duplicate defects
    # are surfaced; then sort for the deterministic run.
    now_epoch = (max(b.start_time.timestamp() for b in as_received) + 86400) if as_received else 0.0
    qsumm = quality_summary(as_received, now_epoch=now_epoch) if as_received else {"counts": {}, "blocking": 0}
    bars = sorted(_copy.deepcopy(bars), key=lambda b: b.start_time.timestamp())
    instrument = defn.instrument_universe[0] if defn.instrument_universe else (bars[0].instrument if bars else "")

    from saathi.platform.strategy.models import strategy_hash
    shash = strategy_hash(defn, parameters)
    dhash = _dataset_hash(bars)

    def _manifest(result_hash: str = "") -> dict[str, Any]:
        return {
            "strategy_hash": shash, "dataset_hash": dhash, "engine_version": ENGINE_VERSION,
            "feature_version": FEATURE_VERSION, "cost_model": cost.to_public(),
            "slippage_model": {"slippage_bps": str(cost.slippage_bps), "spread": cost.spread_slippage},
            "calendar": calendar, "seed": seed, "parameters": parameters,
            "starting_cash": str(starting_cash), "timeframe": defn.timeframe.value,
            "instrument": instrument, "bar_count": len(bars), "result_hash": result_hash,
        }

    def _fail(reason: str, status: str = "FAILED", metrics=None, curve=None, fills=None, inv=None, la_ok=True) -> BacktestResult:
        payload = {"status": status, "reason": reason, "manifest": _manifest()}
        rhash = hashlib.sha256(_canonical(payload).encode()).hexdigest()
        return BacktestResult(status=status, reason=reason, equity_curve=curve or [], fills=fills or [],
                              metrics=metrics or {}, quality_summary=qsumm, invariant_errors=inv or [],
                              result_hash=rhash, manifest=_manifest(rhash), look_ahead_ok=la_ok)

    # 1. structural validation (fail-closed)
    runnable, findings = is_runnable(defn)
    if not runnable:
        return _fail("structural: " + "; ".join(f.code for f in findings if f.severity == "critical"), status="REJECTED")
    if not bars:
        return _fail("empty dataset", status="REJECTED")

    # 2. data-quality gate — invalid datasets block runs
    if strict_quality and qsumm["blocking"] > 0:
        return _fail(f"data quality blocking={qsumm['blocking']}", status="REJECTED")

    # 3. run loop
    ctx = BacktestContext(bars)
    acct = PortfolioAccountant(starting_cash=starting_cash, instruments=[instrument])
    warmup = defn.required_warmup()
    n = len(bars)
    seq = 0
    prev_features: dict[str, Decimal | None] = {}
    look_ahead_ok = True

    try:
        for i in range(n):
            ctx._set_cursor(i)
            ctx.portfolio = acct
            feats = compute_all(defn.features, ctx)
            ctx.prev_features = prev_features
            ctx.last_features = feats
            if probe is not None:
                probe(ctx)   # adversarial hook: may touch the future via ctx.future_peek

            # look-ahead instrumentation: nothing touched may post-date the decision bar
            if ctx.max_accessed_epoch > ctx.decision_epoch + 1e-6:
                look_ahead_ok = False
                return _fail(
                    f"look-ahead: accessed ts {ctx.max_accessed_epoch} > decision ts {ctx.decision_epoch}",
                    status="REJECTED", la_ok=False)

            # decisions allowed only after warm-up and only if a NEXT bar exists to fill
            if i >= warmup and i < n - 1:
                action, sref = evaluate_signals(defn.signals, feats, prev_features)
                if action is not None:
                    fill_bar = bars[i + 1]
                    marks = {instrument: bars[i].close}
                    equity = acct.equity(marks)
                    pos = acct.positions.get(instrument)
                    held = pos.quantity if pos else Decimal("0")
                    if action.value == "ENTER_LONG" and held == 0:
                        try:
                            qty = target_quantity(defn.sizing, equity=equity, price=bars[i].close,
                                                  quantity_precision=quantity_precision,
                                                  risk_max_fraction=defn.risk_max_position_fraction)
                        except SizingError as e:
                            return _fail(f"sizing: {e}", status="REJECTED")
                        # buying-power guard (no leverage): notional must fit cash
                        if qty > 0 and qty * fill_bar.open <= acct.cash:
                            seq += 1
                            order = simulate_fill(seq=seq, side="BUY", order_type="MARKET", quantity=qty,
                                                  decision_bar=bars[i], fill_bar=fill_bar, cost=cost, signal_ref=sref)
                            acct.apply(order)
                    elif action.value == "EXIT" and held > 0:
                        seq += 1
                        order = simulate_fill(seq=seq, side="SELL", order_type="MARKET", quantity=held,
                                              decision_bar=bars[i], fill_bar=fill_bar, cost=cost, signal_ref=sref)
                        acct.apply(order)

            # mark equity at every bar's close
            acct.mark(bars[i].start_time.timestamp(), {instrument: bars[i].close})
            prev_features = feats
    except LookAheadViolation as e:
        return _fail(f"look-ahead-violation: {e}", status="REJECTED", la_ok=False)

    # 4. liquidate at final close for a clean terminal equity
    final_bar = bars[-1]
    pos = acct.positions.get(instrument)
    if pos and pos.quantity > 0:
        seq += 1
        liq = simulate_fill(seq=seq, side="SELL", order_type="MARKET", quantity=pos.quantity,
                            decision_bar=final_bar, fill_bar=final_bar, cost=cost, signal_ref="final_liquidation")
        acct.apply(liq)
        acct.equity_curve[-1] = acct.mark(final_bar.start_time.timestamp(), {instrument: final_bar.close})

    marks = {instrument: final_bar.close}
    inv_errors = acct.check_invariants(marks)

    # 5. metrics
    bench_ret = None
    if benchmark_bars:
        bb = sorted(benchmark_bars, key=lambda b: b.start_time.timestamp())
        if len(bb) >= 2 and bb[0].close != 0:
            bench_ret = (bb[-1].close - bb[0].close) / bb[0].close
    total_slip = sum((D(f.slippage) * D(f.quantity) for f in acct.fills), Decimal("0"))
    m = metrics_mod.compute_metrics(
        acct.equity_curve, acct.fills, timeframe=defn.timeframe.value,
        starting_cash=starting_cash, total_fees=acct.total_fees, total_slippage_cost=total_slip,
        turnover=acct.turnover(marks), benchmark_return=bench_ret)

    # 6. deterministic result hash over the canonical evidence
    canon = {
        "manifest": _manifest(), "equity": [p.to_public() for p in acct.equity_curve],
        "fills": [f.to_public() for f in acct.fills],
        "metrics": {k: v.to_public() for k, v in m.items()},
        "invariant_errors": inv_errors,
    }
    rhash = hashlib.sha256(_canonical(canon).encode()).hexdigest()
    status = "COMPLETE" if not inv_errors else "FAILED"
    reason = "ok" if not inv_errors else "accounting invariant violation"
    return BacktestResult(status=status, reason=reason, equity_curve=acct.equity_curve, fills=acct.fills,
                          metrics=m, quality_summary=qsumm, invariant_errors=inv_errors,
                          result_hash=rhash, manifest=_manifest(rhash),
                          max_accessed_epoch=ctx.max_accessed_epoch, look_ahead_ok=look_ahead_ok)
