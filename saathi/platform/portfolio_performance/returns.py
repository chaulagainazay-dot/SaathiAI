"""Deterministic return calculation — simple and cash-flow-aware TWR."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money


def simple_return(start_nav: Decimal, end_nav: Decimal) -> Decimal | None:
    s = D(start_nav)
    e = D(end_nav)
    if s <= 0:
        return None
    return q_money((e - s) / s)


def twr_from_segments(segment_returns: Iterable[Decimal]) -> Decimal:
    """Product of (1+r_i) - 1."""
    acc = Decimal("1")
    for r in segment_returns:
        acc *= Decimal("1") + D(r)
    return q_money(acc - Decimal("1"))


def period_return_with_flows(
    observations: list[dict],
) -> dict:
    """Compute return across ordered observations.

    External cash flows (deposit/withdrawal) recorded on observation.external_flow
    (positive = deposit into fund, negative = withdrawal).

    Methodology:
    - If no non-zero external flows in window (excluding first obs): SIMPLE return
    - Else TWR: between consecutive obs, if flow at end of segment, return =
      (end_nav - flow - start_nav) / start_nav for that subperiod
      (flow assumed end-of-period standard for daily TWR)

    Returns dict with return_pct, methodology, external_flows_total, data status.
    """
    if len(observations) < 2:
        return {
            "return_pct": None,
            "methodology": None,
            "status": "DATA_INSUFFICIENT",
            "reason": "need_at_least_two_observations",
            "start_nav": None,
            "end_nav": None,
            "external_flows_total": "0",
        }
    start = observations[0]
    end = observations[-1]
    start_nav = D(start["nav"])
    end_nav = D(end["nav"])
    flows = []
    for o in observations[1:]:
        f = D(o.get("external_flow") or "0")
        if f != 0:
            flows.append(f)
    total_flow = sum(flows, Decimal("0"))

    if not flows:
        r = simple_return(start_nav, end_nav)
        return {
            "return_pct": str(r) if r is not None else None,
            "methodology": "SIMPLE",
            "status": "OK" if r is not None else "DATA_INSUFFICIENT",
            "start_nav": str(q_money(start_nav)),
            "end_nav": str(q_money(end_nav)),
            "external_flows_total": "0.00",
            "cash_flow_note": "no external flows in period — investment return = NAV change",
        }

    # TWR segments between consecutive observations
    segs = []
    for a, b in zip(observations, observations[1:]):
        sn = D(a["nav"])
        en = D(b["nav"])
        flow = D(b.get("external_flow") or "0")
        # end-of-period flow: remove flow from ending value for return calc
        adj_end = en - flow
        if sn <= 0:
            continue
        segs.append((adj_end - sn) / sn)
    if not segs:
        return {
            "return_pct": None,
            "methodology": "TWR",
            "status": "DATA_INSUFFICIENT",
            "start_nav": str(q_money(start_nav)),
            "end_nav": str(q_money(end_nav)),
            "external_flows_total": str(q_money(total_flow)),
        }
    r = twr_from_segments(segs)
    return {
        "return_pct": str(r),
        "methodology": "TWR",
        "status": "OK",
        "start_nav": str(q_money(start_nav)),
        "end_nav": str(q_money(end_nav)),
        "external_flows_total": str(q_money(total_flow)),
        "cash_flow_note": "external deposits/withdrawals excluded from investment return via TWR",
        "segments": len(segs),
    }


def realized_volatility(returns: list[Decimal], *, annualization: int, min_n: int) -> dict:
    if len(returns) < min_n:
        return {"status": "DATA_INSUFFICIENT", "volatility": None, "n": len(returns), "required": min_n}
    n = len(returns)
    mean = sum(returns, Decimal("0")) / Decimal(n)
    var = sum(((r - mean) ** 2 for r in returns), Decimal("0")) / Decimal(max(n - 1, 1))
    # std
    # Decimal sqrt
    from decimal import localcontext, ROUND_HALF_UP

    with localcontext() as ctx:
        ctx.prec = 28
        std = var.sqrt()
    ann = std * (Decimal(annualization).sqrt())
    return {
        "status": "OK",
        "volatility": str(q_money(std)),
        "volatility_annualized": str(q_money(ann)),
        "n": n,
        "mean_return": str(q_money(mean)),
    }


def sharpe_ratio(
    returns: list[Decimal],
    *,
    risk_free_per_period: Decimal,
    annualization: int,
    min_n: int,
    assumption: str,
) -> dict:
    if len(returns) < min_n:
        return {
            "status": "DATA_INSUFFICIENT",
            "sharpe": None,
            "n": len(returns),
            "required": min_n,
            "risk_free_assumption": assumption,
        }
    excess = [r - risk_free_per_period for r in returns]
    vol = realized_volatility(excess, annualization=annualization, min_n=min_n)
    if vol["status"] != "OK" or not vol.get("volatility"):
        return {**vol, "sharpe": None, "risk_free_assumption": assumption}
    std = D(vol["volatility"])
    if std == 0:
        return {
            "status": "DATA_INSUFFICIENT",
            "sharpe": None,
            "reason": "zero_volatility",
            "risk_free_assumption": assumption,
        }
    mean_ex = sum(excess, Decimal("0")) / Decimal(len(excess))
    # annualized sharpe approx
    sharpe = (mean_ex / std) * (Decimal(annualization).sqrt())
    return {
        "status": "OK",
        "sharpe": str(q_money(sharpe)),
        "n": len(returns),
        "risk_free_assumption": assumption,
        "risk_free_per_period": str(risk_free_per_period),
    }
