"""Current vs target and rebalance trade generation."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty
from saathi.platform.portfolio_construction.models import (
    MarkQuote,
    RC_CASH_BUFFER_RESTORE,
    RC_MIN_TRADE_THRESHOLD,
    RC_NO_MATERIAL_DRIFT,
    RC_POSITION_ENTRY,
    RC_POSITION_EXIT,
    RC_STALE_PRICE,
    RC_TARGET_WEIGHT_RESTORE,
    RebalanceAction,
    RebalanceTrade,
    TargetAllocation,
)
from saathi.platform.portfolio_construction.policy import ConstructionPolicy, DEFAULT_POLICY


def current_weights_from_ledger(state: dict) -> tuple[dict[str, dict], Decimal, Decimal]:
    """Return positions map by security_id, cash, nav."""
    nav = D(state.get("nav") or state.get("paper_nav") or "0")
    cash = D(state.get("cash") or "0")
    by_id: dict[str, dict] = {}
    for p in state.get("positions") or []:
        sid = p.get("security_id") or f"sec_{p.get('symbol', '')}_PAPER"
        by_id[sid] = {
            "security_id": sid,
            "symbol": p.get("symbol"),
            "quantity": D(p.get("quantity") or "0"),
            "market_value": D(p.get("market_value") or "0"),
            "weight": D(p.get("weight") or "0"),
            "avg_cost": D(p.get("avg_cost") or "0"),
        }
        if by_id[sid]["weight"] == 0 and nav > 0:
            by_id[sid]["weight"] = by_id[sid]["market_value"] / nav
    return by_id, cash, nav


def build_trades(
    *,
    current: dict[str, dict],
    targets: list[TargetAllocation],
    cash_weight: Decimal,
    nav: Decimal,
    marks: dict[str, MarkQuote],
    policy: ConstructionPolicy = DEFAULT_POLICY,
    now: float | None = None,
) -> tuple[list[RebalanceTrade], list[str], list[str]]:
    """Generate BUY/SELL/HOLD/NO_ACTION rows. Returns trades, warnings, hard_errors."""
    warnings: list[str] = []
    errors: list[str] = []
    target_map = {t.security_id: t for t in targets}
    all_ids = set(current.keys()) | set(target_map.keys())
    trades: list[RebalanceTrade] = []

    for sid in sorted(all_ids):
        cur = current.get(sid) or {
            "security_id": sid,
            "symbol": target_map[sid].symbol if sid in target_map else sid,
            "quantity": Decimal("0"),
            "market_value": Decimal("0"),
            "weight": Decimal("0"),
        }
        tgt = target_map.get(sid)
        tw = D(tgt.target_weight) if tgt else Decimal("0")
        cw = D(cur["weight"])
        wdelta = tw - cw
        t_notional = q_money(nav * tw)
        c_notional = q_money(cur["market_value"] if cur["market_value"] else nav * cw)
        n_delta = q_money(t_notional - c_notional)

        mark = marks.get(sid)
        if mark is None and (tw > 0 or abs(n_delta) >= D(policy.min_trade_notional)):
            errors.append(RC_STALE_PRICE)
            continue
        if mark and mark.is_stale(now):
            errors.append(RC_STALE_PRICE)
            continue
        px = D(mark.price) if mark else Decimal("0")

        # materiality filters
        if abs(wdelta) < D(policy.min_weight_delta) and abs(n_delta) < D(policy.min_trade_notional):
            action = RebalanceAction.NO_ACTION if abs(wdelta) < D(policy.rebalance_drift_threshold) else RebalanceAction.HOLD
            codes = [RC_NO_MATERIAL_DRIFT] if action == RebalanceAction.NO_ACTION else [RC_MIN_TRADE_THRESHOLD]
            if action == RebalanceAction.NO_ACTION:
                warnings.append(RC_NO_MATERIAL_DRIFT)
            trades.append(
                RebalanceTrade(
                    security_id=sid,
                    symbol=cur.get("symbol") or (tgt.symbol if tgt else sid),
                    action=action,
                    current_weight=q_money(cw),
                    target_weight=q_money(tw),
                    weight_delta=q_money(wdelta),
                    current_notional=c_notional,
                    target_notional=t_notional,
                    notional_delta=Decimal("0"),
                    estimated_quantity=Decimal("0"),
                    reference_price=q_price(px) if px else Decimal("0"),
                    reason_codes=codes,
                )
            )
            continue

        if abs(wdelta) < D(policy.rebalance_drift_threshold) and abs(n_delta) < D(policy.min_trade_notional) * 2:
            trades.append(
                RebalanceTrade(
                    security_id=sid,
                    symbol=cur.get("symbol") or (tgt.symbol if tgt else sid),
                    action=RebalanceAction.HOLD,
                    current_weight=q_money(cw),
                    target_weight=q_money(tw),
                    weight_delta=q_money(wdelta),
                    current_notional=c_notional,
                    target_notional=t_notional,
                    notional_delta=Decimal("0"),
                    estimated_quantity=Decimal("0"),
                    reference_price=q_price(px),
                    reason_codes=[RC_NO_MATERIAL_DRIFT],
                )
            )
            continue

        if n_delta > 0:
            action = RebalanceAction.BUY
            codes = [RC_POSITION_ENTRY] if cw == 0 else [RC_TARGET_WEIGHT_RESTORE]
            qty = q_qty(n_delta / px) if px > 0 else Decimal("0")
        elif n_delta < 0:
            action = RebalanceAction.SELL
            codes = [RC_POSITION_EXIT] if tw == 0 else [RC_TARGET_WEIGHT_RESTORE]
            if tw == 0 and cw > 0:
                codes = [RC_POSITION_EXIT]
            qty = q_qty(abs(n_delta) / px) if px > 0 else Decimal("0")
        else:
            action = RebalanceAction.HOLD
            codes = [RC_NO_MATERIAL_DRIFT]
            qty = Decimal("0")

        trades.append(
            RebalanceTrade(
                security_id=sid,
                symbol=cur.get("symbol") or (tgt.symbol if tgt else sid),
                action=action,
                current_weight=q_money(cw),
                target_weight=q_money(tw),
                weight_delta=q_money(wdelta),
                current_notional=c_notional,
                target_notional=t_notional,
                notional_delta=n_delta if action != RebalanceAction.HOLD else Decimal("0"),
                estimated_quantity=qty,
                reference_price=q_price(px),
                reason_codes=codes,
            )
        )

    # cash delta informational
    target_invested = sum((D(t.target_weight) for t in targets), Decimal("0"))
    # if net buys exceed cash available after buffer — caller validates

    return trades, warnings, errors


def turnover(trades: Iterable[RebalanceTrade], nav: Decimal) -> Decimal:
    if nav <= 0:
        return Decimal("0")
    s = sum((abs(D(t.notional_delta)) for t in trades), Decimal("0"))
    return q_money(s / nav)


def before_after_summary(
    *,
    current_state: dict,
    projected_cash: Decimal,
    projected_nav: Decimal,
    targets: list[TargetAllocation],
    cash_weight: Decimal,
    current_risk: dict | None,
    projected_risk: dict | None,
) -> tuple[dict, dict, dict]:
    cur_pos = current_state.get("positions") or []
    largest_cur = max((D(p.get("weight") or 0) for p in cur_pos), default=Decimal("0"))
    largest_prop = max((D(t.target_weight) for t in targets), default=Decimal("0"))
    current = {
        "cash": str(q_money(current_state.get("cash") or "0")),
        "nav": str(q_money(current_state.get("nav") or "0")),
        "gross_exposure": str(q_money((current_state.get("exposure") or {}).get("gross") or current_state.get("positions_value") or "0")),
        "net_exposure": str(q_money((current_state.get("exposure") or {}).get("net") or "0")),
        "largest_position": str(q_money(largest_cur)),
        "position_count": len([p for p in cur_pos if D(p.get("quantity") or 0) != 0]),
        "risk_status": (current_risk or {}).get("risk_status"),
        "stress_loss": (current_risk or {}).get("stress_loss"),
        "cash_weight": str(q_money(D(current_state.get("cash") or 0) / D(current_state.get("nav") or 1))) if D(current_state.get("nav") or 0) else "0",
    }
    proposed = {
        "cash": str(q_money(projected_cash)),
        "nav": str(q_money(projected_nav)),
        "gross_exposure": str(q_money(sum((D(t.target_notional) for t in targets), Decimal("0")))),
        "net_exposure": str(q_money(sum((D(t.target_notional) for t in targets), Decimal("0")))),
        "largest_position": str(q_money(largest_prop)),
        "position_count": len([t for t in targets if D(t.target_weight) > 0]),
        "risk_status": (projected_risk or {}).get("risk_status") or (projected_risk or {}).get("result"),
        "stress_loss": (projected_risk or {}).get("stress_loss"),
        "cash_weight": str(q_money(cash_weight)),
    }
    delta = {
        "cash": str(q_money(D(proposed["cash"]) - D(current["cash"]))),
        "nav": str(q_money(D(proposed["nav"]) - D(current["nav"]))),
        "gross_exposure": str(q_money(D(proposed["gross_exposure"]) - D(current["gross_exposure"]))),
        "largest_position": str(q_money(D(proposed["largest_position"]) - D(current["largest_position"]))),
        "position_count": proposed["position_count"] - current["position_count"],
        "risk_status": f"{current.get('risk_status')} → {proposed.get('risk_status')}",
    }
    return current, proposed, delta
