"""M180 — Portfolio-level research and risk validation (paper/simulated only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.tg.domain import coerce_decimal


class ReconciliationVerdict(str, Enum):
    RECONCILED = "RECONCILED"
    RECONCILED_WITH_WARNINGS = "RECONCILED_WITH_WARNINGS"
    UNRECONCILED_BLOCKED = "UNRECONCILED_BLOCKED"


@dataclass
class PortfolioState:
    cash: Decimal = field(default_factory=lambda: Decimal("100000"))
    equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    sector_of: dict[str, str] = field(default_factory=dict)
    strategy_of: dict[str, str] = field(default_factory=dict)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    fees_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    reconciliation: ReconciliationVerdict = ReconciliationVerdict.RECONCILED
    reconciliation_notes: list[str] = field(default_factory=list)
    peak_equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    funds_label: str = "SIMULATED"
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "cash": str(self.cash),
            "equity": str(self.equity),
            "positions": {k: {kk: str(vv) if isinstance(vv, Decimal) else vv for kk, vv in v.items()}
                          for k, v in self.positions.items()},
            "open_orders": list(self.open_orders),
            "realized_pnl": str(self.realized_pnl),
            "fees_paid": str(self.fees_paid),
            "slippage_paid": str(self.slippage_paid),
            "reconciliation": self.reconciliation.value,
            "reconciliation_notes": list(self.reconciliation_notes),
            "funds_label": "SIMULATED",
            "paper_only": True,
            "live_money": False,
            "disclaimer": "SIMULATED FUNDS — NOT REAL MONEY",
        }


class PortfolioRiskAnalyzer:
    def __init__(
        self,
        *,
        max_sector_pct: Decimal = Decimal("40"),
        max_instrument_pct: Decimal = Decimal("25"),
        max_strategy_pct: Decimal = Decimal("50"),
        max_corr_exposure_pct: Decimal = Decimal("50"),
        max_heat_pct: Decimal = Decimal("6"),
        max_gross_pct: Decimal = Decimal("100"),
    ):
        self.max_sector_pct = max_sector_pct
        self.max_instrument_pct = max_instrument_pct
        self.max_strategy_pct = max_strategy_pct
        self.max_corr_exposure_pct = max_corr_exposure_pct
        self.max_heat_pct = max_heat_pct
        self.max_gross_pct = max_gross_pct

    def analyze(self, state: PortfolioState, *, marks: dict[str, Decimal] | None = None) -> dict[str, Any]:
        marks = marks or {}
        equity = state.equity if state.equity > 0 else Decimal("1")
        gross = Decimal("0")
        sector_exp: dict[str, Decimal] = {}
        strategy_exp: dict[str, Decimal] = {}
        instrument_exp: dict[str, Decimal] = {}

        for sym, pos in state.positions.items():
            qty = coerce_decimal(pos.get("quantity", 0))
            px = marks.get(sym, coerce_decimal(pos.get("avg_cost", 0)))
            notional = abs(qty * px)
            gross += notional
            instrument_exp[sym] = instrument_exp.get(sym, Decimal("0")) + notional
            sec = state.sector_of.get(sym, pos.get("sector", "UNKNOWN"))
            sector_exp[sec] = sector_exp.get(sec, Decimal("0")) + notional
            strat = state.strategy_of.get(sym, pos.get("strategy", "UNKNOWN"))
            strategy_exp[strat] = strategy_exp.get(strat, Decimal("0")) + notional

        def pct(v: Decimal) -> Decimal:
            return (v / equity * Decimal("100")) if equity else Decimal("0")

        top_inst = max(instrument_exp.values()) if instrument_exp else Decimal("0")
        top_sec = max(sector_exp.values()) if sector_exp else Decimal("0")
        top_strat = max(strategy_exp.values()) if strategy_exp else Decimal("0")

        dd = Decimal("0")
        if state.peak_equity > 0:
            dd = (state.peak_equity - state.equity) / state.peak_equity * Decimal("100")

        # Simple correlation proxy: same-sector exposure treated as correlated
        corr_exposure = top_sec

        heat = pct(sum(
            abs(coerce_decimal(p.get("risk_amount", 0))) for p in state.positions.values()
        )) if state.positions else Decimal("0")

        breaches = []
        if pct(gross) > self.max_gross_pct:
            breaches.append("GROSS_EXPOSURE")
        if pct(top_sec) > self.max_sector_pct:
            breaches.append("SECTOR_LIMIT")
        if pct(top_inst) > self.max_instrument_pct:
            breaches.append("INSTRUMENT_CONCENTRATION")
        if pct(top_strat) > self.max_strategy_pct:
            breaches.append("STRATEGY_CONCENTRATION")
        if pct(corr_exposure) > self.max_corr_exposure_pct:
            breaches.append("CORRELATED_EXPOSURE")
        if heat > self.max_heat_pct:
            breaches.append("PORTFOLIO_HEAT")

        return {
            "gross_exposure": str(gross),
            "net_simulated_exposure": str(gross),  # long-only paper
            "gross_exposure_pct": str(pct(gross)),
            "sector_exposure": {k: str(pct(v)) for k, v in sector_exp.items()},
            "instrument_concentration": {k: str(pct(v)) for k, v in instrument_exp.items()},
            "strategy_concentration": {k: str(pct(v)) for k, v in strategy_exp.items()},
            "correlated_exposure_pct": str(pct(corr_exposure)),
            "portfolio_heat_pct": str(heat),
            "drawdown_pct": str(dd),
            "fee_contribution": str(state.fees_paid),
            "slippage_contribution": str(state.slippage_paid),
            "turnover_proxy": str(sum(abs(coerce_decimal(p.get("quantity", 0))) for p in state.positions.values())),
            "open_order_count": len(state.open_orders),
            "breaches": breaches,
            "reconciliation": state.reconciliation.value,
            "blocks_new_proposals": (
                state.reconciliation == ReconciliationVerdict.UNRECONCILED_BLOCKED
                or bool(breaches)
            ),
            "paper_only": True,
            "funds_label": "SIMULATED",
        }

    def scenario(self, name: str, state: PortfolioState, **kwargs: Any) -> dict[str, Any]:
        """Deterministic portfolio stress scenarios."""
        s = PortfolioState(
            cash=state.cash, equity=state.equity,
            positions=dict(state.positions), sector_of=dict(state.sector_of),
            strategy_of=dict(state.strategy_of), open_orders=list(state.open_orders),
            realized_pnl=state.realized_pnl, fees_paid=state.fees_paid,
            slippage_paid=state.slippage_paid, reconciliation=state.reconciliation,
            peak_equity=state.peak_equity,
        )
        notes = []
        if name == "correlated_selloff":
            # All positions lose 10%
            loss = Decimal("0")
            for sym, pos in s.positions.items():
                qty = coerce_decimal(pos.get("quantity", 0))
                cost = coerce_decimal(pos.get("avg_cost", 0))
                loss += qty * cost * Decimal("0.10")
            s.equity = s.equity - loss
            s.realized_pnl -= loss
            notes.append("all_positions_-10pct")
        elif name == "gap_through_stops":
            loss = Decimal("0")
            for sym, pos in s.positions.items():
                qty = coerce_decimal(pos.get("quantity", 0))
                cost = coerce_decimal(pos.get("avg_cost", 0))
                # gap 5% beyond stop assumption
                loss += qty * cost * Decimal("0.08")
            s.equity -= loss
            notes.append("stops_gapped_8pct")
        elif name == "liquidity_collapse":
            notes.append("liquidity_collapsed_sim")
            # Mark unreconciled if open orders exist
            if s.open_orders:
                s.reconciliation = ReconciliationVerdict.UNRECONCILED_BLOCKED
                s.reconciliation_notes.append("open_orders_during_liquidity_collapse")
        elif name == "loss_streak":
            s.realized_pnl -= Decimal("1500")
            s.equity -= Decimal("1500")
            notes.append("strategy_loss_streak")
        elif name == "daily_loss_cap":
            notes.append("daily_loss_cap_reached")
        elif name == "kill_switch_partial":
            cancelled = []
            remaining = []
            for o in s.open_orders:
                if o.get("status") in ("PENDING", "SUBMITTED", "PARTIAL"):
                    cancelled.append({**o, "status": "CANCELLED", "reason": "kill_switch"})
                else:
                    remaining.append(o)
            s.open_orders = remaining
            notes.append(f"cancelled_{len(cancelled)}_orders")
        elif name == "unreconciled":
            s.reconciliation = ReconciliationVerdict.UNRECONCILED_BLOCKED
            s.reconciliation_notes.append("injected_unreconciled")
            notes.append("unreconciled")
        elif name == "conflicting_proposals":
            notes.append("two_strategies_conflicting_proposals")
        else:
            notes.append("unknown_scenario")

        analysis = self.analyze(s)
        return {
            "scenario": name,
            "notes": notes,
            "state": s.to_public(),
            "analysis": analysis,
            "blocks_new_proposals": analysis["blocks_new_proposals"],
            "paper_only": True,
        }

    def may_accept_proposal(self, state: PortfolioState, analysis: dict[str, Any] | None = None) -> tuple[bool, str]:
        if state.reconciliation == ReconciliationVerdict.UNRECONCILED_BLOCKED:
            return False, "UNRECONCILED_BLOCKED"
        a = analysis or self.analyze(state)
        if a.get("breaches"):
            return False, f"PORTFOLIO_BREACH:{','.join(a['breaches'])}"
        return True, "OK"
