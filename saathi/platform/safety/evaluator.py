"""M62.7 — deterministic breaker evaluation + default breaker policies.

Given a breaker definition and a metric snapshot, ``evaluate`` returns a
``SafetyFinding`` with a stable severity, reason codes, and an immutable metric
snapshot. Identical inputs → identical finding, severity, and snapshot hash. No
hidden randomness, no wall-clock inside the decision.
"""
from __future__ import annotations

import time as _time
from decimal import Decimal
from typing import Any

from saathi.platform.trading_models import D
from saathi.platform.paper_trading.models import q2
from saathi.platform.safety.models import (
    BreakerType, BreakerScope, Severity, OpenOrderPolicy,
    CircuitBreakerDefinition, SafetyMetricSnapshot, SafetyFinding,
    default_open_order_policy,
)


def _snap(defn: CircuitBreakerDefinition, *, ts: float, value: Decimal, num=Decimal("0"),
          den=Decimal("0"), sample_ok=True, window=None, detail=None) -> SafetyMetricSnapshot:
    return SafetyMetricSnapshot(
        definition_id=defn.id, org_id=defn.org_id, breaker_type=defn.breaker_type, scope=defn.scope,
        scope_ref=defn.scope_ref, ts=ts, value=value, threshold=defn.threshold, numerator=num,
        denominator=den, sample_sufficient=sample_ok, window=window or {}, detail=detail or {})


class BreakerEvaluator:
    """Pure evaluation. All inputs are supplied by the caller (deterministic)."""

    def evaluate(self, defn: CircuitBreakerDefinition, *, metrics: dict[str, Any] | None = None,
                 rejection: dict | None = None, failure_count: int = 0, peak_equity: Decimal | None = None,
                 now: float, market_health: dict | None = None) -> SafetyFinding:
        if defn.requires_config and defn.threshold == 0:
            # no safe default → inert but explicit (never silently trips or passes)
            return self._finding(defn, now, breached=False, severity=Severity.INFO,
                                 codes=["requires_config"], msg="breaker requires explicit threshold configuration",
                                 snap=_snap(defn, ts=now, value=Decimal("0")))

        m = metrics or {}
        bt = defn.breaker_type
        thr = D(defn.threshold)

        if bt == BreakerType.DAILY_REALIZED_LOSS:
            v = D(m.get("daily_realized_pnl", 0))
            breached = v <= -thr
            return self._loss(defn, now, v, thr, breached, "daily_realized_loss", m.get("day"))

        if bt == BreakerType.DAILY_TOTAL_LOSS:
            v = D(m.get("daily_total_pnl", 0))
            breached = v <= -thr
            return self._loss(defn, now, v, thr, breached, "daily_total_loss", m.get("day"))

        if bt == BreakerType.MAX_DRAWDOWN:
            equity = D(m.get("equity", 0))
            peak = max(D(peak_equity or 0), equity)
            dd = q2(peak - equity)
            dd_pct = q2(dd / peak * Decimal("100")) if peak > 0 else Decimal("0")
            breached = dd_pct >= thr and peak > 0
            snap = _snap(defn, ts=now, value=dd_pct, detail={"peak_equity": str(peak), "equity": str(equity),
                         "drawdown": str(dd), "drawdown_pct": str(dd_pct), "new_peak": str(peak)})
            return self._decide(defn, now, breached, "max_drawdown", snap,
                                f"drawdown {dd_pct}% >= {thr}%")

        if bt == BreakerType.GROSS_EXPOSURE:
            v = D(m.get("gross_exposure", 0))
            breached = v > thr
            snap = _snap(defn, ts=now, value=v, detail={"gross_exposure": str(v)})
            return self._decide(defn, now, breached, "gross_exposure", snap,
                                f"gross exposure {v} > {thr}")

        if bt == BreakerType.POSITION_CONCENTRATION:
            equity = D(m.get("equity", 0))
            top_notional = D(m.get("top_symbol_notional", 0))
            if equity <= 0 and top_notional > 0:
                snap = _snap(defn, ts=now, value=Decimal("0"), sample_ok=False,
                             detail={"reason": "undefined_denominator", "equity": str(equity)})
                return self._finding(defn, now, breached=True, severity=defn.severity,
                                     codes=["concentration_undefined_denominator"],
                                     msg="concentration denominator (equity) <= 0 with open position; fail closed",
                                     snap=snap)
            conc = D(m.get("concentration_pct", 0))
            warn = D(defn.warning_threshold) if defn.warning_threshold is not None else None
            snap = _snap(defn, ts=now, value=conc, detail={"top_symbol": m.get("top_symbol", ""),
                         "concentration_pct": str(conc)})
            if conc > thr:
                return self._decide(defn, now, True, "concentration", snap, f"concentration {conc}% > {thr}%")
            if warn is not None and conc >= warn:
                return self._finding(defn, now, breached=True, severity=Severity.WARNING,
                                     codes=["concentration_warning"],
                                     msg=f"concentration {conc}% >= warn {warn}%", snap=snap)
            return self._decide(defn, now, False, "concentration", snap, "concentration within limit")

        if bt == BreakerType.OPEN_ORDER_COUNT:
            v = D(m.get("open_order_count", 0))
            breached = v > thr
            snap = _snap(defn, ts=now, value=v, detail={"open_order_count": str(v)})
            return self._decide(defn, now, breached, "open_order_count", snap,
                                f"open orders {v} > {thr}")

        if bt == BreakerType.ORDER_REJECTION_RATE:
            rej = rejection or {}
            num = D(rej.get("numerator", 0)); den = D(rej.get("denominator", 0)); rate = D(rej.get("rate", 0))
            sample_ok = den >= defn.min_samples
            snap = _snap(defn, ts=now, value=rate, num=num, den=den, sample_ok=sample_ok,
                         window={"window_seconds": defn.window_seconds, "min_samples": defn.min_samples},
                         detail={"rate": str(rate)})
            if not sample_ok:
                return self._finding(defn, now, breached=False, severity=Severity.INFO,
                                     codes=["insufficient_sample"],
                                     msg=f"sample {den} < min {defn.min_samples}; no unstable trip", snap=snap)
            breached = rate > thr
            return self._decide(defn, now, breached, "rejection_rate", snap,
                                f"rejection rate {rate} > {thr}")

        if bt == BreakerType.PROCESSING_FAILURE:
            v = Decimal(int(failure_count))
            breached = v >= thr and thr > 0
            snap = _snap(defn, ts=now, value=v, window={"window_seconds": defn.window_seconds},
                         detail={"failures": int(failure_count)})
            return self._decide(defn, now, breached, "processing_failure", snap,
                                f"{failure_count} failures >= {thr} in window")

        if bt == BreakerType.ACCOUNTING_INVARIANT:
            errs = []
            if D(m.get("available_cash", 0)) < 0:
                errs.append("negative_available_cash")
            if D(m.get("reserved_cash", 0)) < 0:
                errs.append("negative_reserved_cash")
            if D(m.get("reserved_cash", 0)) > D(m.get("cash", 0)):
                errs.append("reserved_exceeds_cash")
            snap = _snap(defn, ts=now, value=D(m.get("available_cash", 0)),
                         detail={"available_cash": str(m.get("available_cash", 0)),
                                 "reserved_cash": str(m.get("reserved_cash", 0)), "errors": errs})
            return self._decide(defn, now, bool(errs), "accounting_invariant", snap,
                                "accounting invariant failed: " + ",".join(errs) if errs else "invariants hold")

        # types evaluated event-driven (recon / market-data) are not scored here
        return self._finding(defn, now, breached=False, severity=Severity.INFO, codes=["not_metric_evaluated"],
                             msg="breaker is event-driven; not evaluated by metric sweep",
                             snap=_snap(defn, ts=now, value=Decimal("0")))

    # ── helpers ─────────────────────────────────────────────────────────────────────
    def _loss(self, defn, now, v, thr, breached, code, day) -> SafetyFinding:
        snap = _snap(defn, ts=now, value=v, window={"day": day} if day else {},
                     detail={"pnl": str(v), "loss_threshold": str(thr), "day": day})
        return self._decide(defn, now, breached, code, snap, f"loss {v} <= -{thr}")

    def _decide(self, defn, now, breached, code, snap, msg) -> SafetyFinding:
        severity = defn.severity if breached else Severity.INFO
        return self._finding(defn, now, breached=breached, severity=severity,
                             codes=[code] if breached else [], msg=(msg if breached else "within limit"),
                             snap=snap)

    def _finding(self, defn, now, *, breached, severity, codes, msg, snap) -> SafetyFinding:
        return SafetyFinding(definition_id=defn.id, breaker_type=defn.breaker_type, scope=defn.scope,
                             scope_ref=defn.scope_ref, severity=severity, breached=breached,
                             reason_codes=list(codes), message=msg, snapshot=snap)


# ── default breaker policies (conservative local-paper defaults) ─────────────────
def default_account_breakers(org_id: str, account_id: str, *, created_by: str = "system",
                             tz_name: str = "UTC") -> list[CircuitBreakerDefinition]:
    """Conservative defaults for one paper account. Where no safe generic default
    exists, ``requires_config`` marks the breaker inert until an operator sets a
    threshold (fail-closed for high-impact loss limits)."""
    def mk(bt: BreakerType, threshold: str, *, warn=None, window=0, min_samples=0, severity=Severity.ERROR,
           requires_config=False) -> CircuitBreakerDefinition:
        return CircuitBreakerDefinition(
            id=f"brk_{account_id}_{bt.value.lower()}", org_id=org_id, breaker_type=bt,
            scope=BreakerScope.PAPER_ACCOUNT, scope_ref=account_id,
            threshold=D(threshold), warning_threshold=(D(warn) if warn is not None else None),
            window_seconds=window, min_samples=min_samples, severity=severity,
            open_order_policy=default_open_order_policy(bt), timezone=tz_name, requires_config=requires_config,
            created_by=created_by)
    return [
        # daily loss limits have no universal safe magnitude → require explicit config
        mk(BreakerType.DAILY_REALIZED_LOSS, "0", requires_config=True),
        mk(BreakerType.DAILY_TOTAL_LOSS, "0", requires_config=True),
        mk(BreakerType.MAX_DRAWDOWN, "50"),                    # 50% equity drawdown
        mk(BreakerType.GROSS_EXPOSURE, "0", requires_config=True),
        mk(BreakerType.POSITION_CONCENTRATION, "60", warn="40"),
        mk(BreakerType.OPEN_ORDER_COUNT, "50"),
        mk(BreakerType.ORDER_REJECTION_RATE, "0.5", window=3600, min_samples=10),
        mk(BreakerType.PROCESSING_FAILURE, "5", window=600, severity=Severity.CRITICAL),
        mk(BreakerType.ACCOUNTING_INVARIANT, "0", severity=Severity.CRITICAL),
        mk(BreakerType.RECONCILIATION_CRITICAL, "0", severity=Severity.CRITICAL),
    ]
