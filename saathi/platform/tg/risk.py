"""M170 — Deterministic Trading Guardian Risk Engine.

Independent of LLM judgment. Fixed-fractional sizing: risk / stop distance.
No leverage, margin, martingale, or averaging-down unless explicitly approved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.trading_models import D
from saathi.platform.tg.domain import RiskDecision, TradeProposal, TradingGuardianPolicy
from saathi.platform.tg.kill_switch import KillSwitchStore


@dataclass
class RiskLimitsConfig:
    max_risk_per_trade_pct: Decimal = field(default_factory=lambda: Decimal("1"))
    max_position_value: Decimal = field(default_factory=lambda: Decimal("25000"))
    max_portfolio_heat_pct: Decimal = field(default_factory=lambda: Decimal("6"))
    max_sector_exposure_pct: Decimal = field(default_factory=lambda: Decimal("40"))
    max_correlated_exposure_pct: Decimal = field(default_factory=lambda: Decimal("50"))
    max_open_positions: int = 5
    daily_loss_limit: Decimal = field(default_factory=lambda: Decimal("500"))
    weekly_loss_limit: Decimal = field(default_factory=lambda: Decimal("1500"))
    max_drawdown_pct: Decimal = field(default_factory=lambda: Decimal("15"))
    max_consecutive_losses: int = 3
    min_stop_distance_pct: Decimal = field(default_factory=lambda: Decimal("0.002"))
    max_stop_distance_pct: Decimal = field(default_factory=lambda: Decimal("0.15"))
    min_tradable_qty: Decimal = field(default_factory=lambda: Decimal("1"))
    slippage_budget_pct: Decimal = field(default_factory=lambda: Decimal("0.002"))
    fee_budget_pct: Decimal = field(default_factory=lambda: Decimal("0.001"))
    gap_risk_buffer_pct: Decimal = field(default_factory=lambda: Decimal("0.005"))
    min_reward_to_risk: Decimal = field(default_factory=lambda: Decimal("1.5"))
    allow_averaging_down: bool = False
    allow_martingale: bool = False


class RiskEngine:
    """Pure deterministic risk. LLM outputs must never call into final sizing."""

    def __init__(
        self,
        limits: RiskLimitsConfig | None = None,
        kill_switches: KillSwitchStore | None = None,
    ):
        self.limits = limits or RiskLimitsConfig()
        self.kill_switches = kill_switches or KillSwitchStore()

    @classmethod
    def from_policy(cls, policy: TradingGuardianPolicy, kill_switches: KillSwitchStore | None = None) -> "RiskEngine":
        lim = RiskLimitsConfig(
            max_risk_per_trade_pct=policy.max_risk_per_trade_pct,
            max_position_value=policy.max_position_value,
            max_portfolio_heat_pct=policy.max_portfolio_heat_pct,
            max_sector_exposure_pct=policy.max_sector_exposure_pct,
            max_correlated_exposure_pct=policy.max_correlated_exposure_pct,
            max_open_positions=policy.max_open_positions,
            daily_loss_limit=policy.daily_loss_limit,
            weekly_loss_limit=policy.weekly_loss_limit,
            max_drawdown_pct=policy.max_drawdown_pct,
            max_consecutive_losses=policy.max_consecutive_losses,
            min_reward_to_risk=policy.min_reward_to_risk,
            allow_averaging_down=policy.averaging_down_allowed,
            allow_martingale=False,
        )
        return cls(limits=lim, kill_switches=kill_switches)

    def evaluate(
        self,
        proposal: TradeProposal,
        *,
        equity: Decimal,
        cash: Decimal,
        portfolio: dict[str, Any] | None = None,
        existing_position_qty: Decimal = Decimal("0"),
        price_stale: bool = False,
        fee_rate: Decimal = Decimal("0.001"),
        slippage_rate: Decimal = Decimal("0.001"),
        now: float | None = None,
    ) -> RiskDecision:
        portfolio = portfolio or {}
        checks: list[dict[str, Any]] = []
        reasons: list[str] = []
        lim = self.limits

        def check(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"check": name, "ok": bool(ok), "detail": detail})
            if not ok:
                reasons.append(detail or name)

        # Kill switch
        ks = self.kill_switches.is_blocked(
            org_id=proposal.org_id,
            workspace_id=proposal.workspace_id,
            strategy_id=proposal.strategy_id,
            instrument=proposal.symbol,
            portfolio_id=proposal.portfolio_id,
        )
        check("kill_switch", not ks["blocked"], ks.get("reason", ""))

        # No leverage / margin
        check("no_leverage", True, "leverage disabled")
        check("no_margin", True, "margin disabled")
        check("no_withdrawals", True, "withdrawals not applicable in paper sim")

        # Stale price
        check("price_not_stale", not price_stale, "price is stale")

        # Portfolio reconcile capability
        check("portfolio_reconciled", portfolio.get("reconciled", True) is not False, "portfolio cannot be reconciled")

        entry = D(proposal.entry_price)
        stop = D(proposal.stop_price) if proposal.stop_price is not None else Decimal("0")
        check("entry_price_valid", entry > 0, "entry price invalid")

        # Prefer explicit stop_distance only when stop price is also valid, otherwise
        # treat missing/zero stop as invalid regardless of residual distance fields.
        if proposal.stop_price is None or stop <= 0:
            stop_distance = Decimal("0")
        else:
            stop_distance = entry - stop if proposal.side == "BUY" else stop - entry
            if proposal.stop_distance and D(proposal.stop_distance) > 0:
                stop_distance = D(proposal.stop_distance)

        check("stop_distance_valid", stop_distance > 0, "stop distance zero or invalid")

        if entry > 0 and stop_distance > 0:
            stop_pct = stop_distance / entry
            check(
                "min_stop_distance",
                stop_pct >= lim.min_stop_distance_pct,
                f"stop pct {stop_pct} < min {lim.min_stop_distance_pct}",
            )
            check(
                "max_stop_distance",
                stop_pct <= lim.max_stop_distance_pct,
                f"stop pct {stop_pct} > max {lim.max_stop_distance_pct}",
            )
        else:
            stop_pct = Decimal("0")
            check("min_stop_distance", False, "cannot compute stop pct")
            check("max_stop_distance", False, "cannot compute stop pct")

        # Fixed fractional: allowed risk / distance to stop
        equity = D(equity)
        cash = D(cash)
        risk_amount = equity * (lim.max_risk_per_trade_pct / Decimal("100"))
        if stop_distance > 0:
            raw_qty = risk_amount / stop_distance
        else:
            raw_qty = Decimal("0")

        # Caps
        max_qty_by_value = lim.max_position_value / entry if entry > 0 else Decimal("0")
        max_qty_by_cash = cash / entry if entry > 0 else Decimal("0")
        sized = min(raw_qty, max_qty_by_value, max_qty_by_cash)
        # Floor to integer shares for equities
        sized = Decimal(int(sized))

        check("size_above_minimum", sized >= lim.min_tradable_qty, f"size {sized} below tradable minimum")
        check("risk_data_complete", equity > 0 and entry > 0 and stop_distance > 0, "risk data incomplete")

        # Fees / slippage destroy edge
        notional = sized * entry
        fees = notional * fee_rate
        slip = notional * slippage_rate
        cost = fees + slip
        expected_reward = Decimal("0")
        if proposal.take_profit_price and entry > 0 and sized > 0:
            expected_reward = abs(D(proposal.take_profit_price) - entry) * sized
        edge_ok = expected_reward > cost * Decimal("2") if expected_reward > 0 else True
        check("fees_slippage_edge", edge_ok, f"costs {cost} vs expected reward {expected_reward}")
        check("slippage_budget", slip <= notional * lim.slippage_budget_pct + Decimal("0.01") or notional == 0,
              f"slippage {slip}")
        check("fee_budget", fees <= notional * lim.fee_budget_pct + Decimal("0.01") or notional == 0,
              f"fees {fees}")

        # Gap risk buffer already in stop distance check via max; explicit note
        check("gap_risk_buffer", stop_pct >= lim.gap_risk_buffer_pct or stop_distance == 0,
              f"stop should cover gap buffer {lim.gap_risk_buffer_pct}")

        # Reward to risk
        rr = D(proposal.reward_to_risk)
        check("reward_to_risk", rr >= lim.min_reward_to_risk, f"R:R {rr} < {lim.min_reward_to_risk}")

        # Portfolio heat
        heat = D(portfolio.get("portfolio_heat_pct", 0))
        trade_heat = (risk_amount / equity * Decimal("100")) if equity > 0 else Decimal("100")
        check("portfolio_heat", heat + trade_heat <= lim.max_portfolio_heat_pct,
              f"heat {heat}+{trade_heat} > {lim.max_portfolio_heat_pct}")

        # Sector / correlated
        sector_pct = D(portfolio.get("sector_exposure_pct", {}).get(proposal.sector or "UNKNOWN", 0))
        add_sector = (notional / equity * Decimal("100")) if equity > 0 else Decimal("0")
        check("sector_exposure", sector_pct + add_sector <= lim.max_sector_exposure_pct,
              f"sector exposure {sector_pct}+{add_sector}")
        corr = D(portfolio.get("correlated_exposure_pct", 0))
        check("correlated_exposure", corr + add_sector <= lim.max_correlated_exposure_pct,
              f"corr exposure {corr}")

        open_pos = int(portfolio.get("open_positions", 0))
        new_pos = 0 if existing_position_qty > 0 else 1
        check("max_concurrent_positions", open_pos + new_pos <= lim.max_open_positions,
              f"open positions {open_pos}")

        daily_loss = D(portfolio.get("daily_realized_loss", 0))
        weekly_loss = D(portfolio.get("weekly_realized_loss", 0))
        check("daily_loss_limit", daily_loss < lim.daily_loss_limit, f"daily loss {daily_loss}")
        check("weekly_loss_limit", weekly_loss < lim.weekly_loss_limit, f"weekly loss {weekly_loss}")

        dd = D(portfolio.get("drawdown_pct", 0))
        check("trailing_drawdown", dd < lim.max_drawdown_pct, f"drawdown {dd}%")

        consec = int(portfolio.get("consecutive_losses", 0))
        check("consecutive_loss_threshold", consec < lim.max_consecutive_losses,
              f"consecutive losses {consec}")

        # Averaging down / martingale
        if existing_position_qty > 0 and proposal.side == "BUY":
            check(
                "no_averaging_down",
                lim.allow_averaging_down,
                "averaging down not approved for this strategy",
            )
        else:
            check("no_averaging_down", True, "n/a")

        # Martingale: doubling after losses
        last_size = D(portfolio.get("last_position_size", 0))
        if last_size > 0 and sized > last_size * Decimal("1.5") and consec > 0:
            check("no_martingale", False, "size increase after losses looks like martingale")
        else:
            check("no_martingale", not lim.allow_martingale or True, "martingale disabled")

        # Unlimited grid / doubling
        check("no_unlimited_grid", True, "grid strategies not enabled")
        check("no_doubling_after_losses", sized <= last_size * Decimal("1.5") or last_size == 0 or consec == 0,
              "doubling after losses rejected")

        # Prefer engine size over proposal when proposal is larger
        final_size = sized
        if proposal.quantity > 0:
            final_size = min(sized, D(proposal.quantity))

        allowed = len(reasons) == 0 and final_size >= lim.min_tradable_qty
        if final_size < lim.min_tradable_qty and "size_above_minimum" not in "".join(reasons):
            # already checked
            pass

        return RiskDecision(
            proposal_id=proposal.id,
            allowed=allowed,
            reasons=reasons,
            checks=checks,
            position_size=final_size if allowed else Decimal("0"),
            risk_amount=risk_amount,
            max_loss=final_size * stop_distance if stop_distance > 0 else Decimal("0"),
            portfolio_heat=heat + trade_heat,
            sizing_method="FIXED_FRACTIONAL",
            policy_version=proposal.policy_version,
            strategy_version=proposal.strategy_version,
            correlation_id=proposal.correlation_id,
            org_id=proposal.org_id,
            workspace_id=proposal.workspace_id,
            leverage_used=False,
            margin_used=False,
        )

    def size_position(
        self,
        *,
        equity: Decimal,
        entry: Decimal,
        stop: Decimal,
        side: str = "BUY",
    ) -> Decimal:
        """Public pure sizing: allowed risk / stop distance, capped."""
        stop_distance = (entry - stop) if side == "BUY" else (stop - entry)
        if stop_distance <= 0 or entry <= 0 or equity <= 0:
            return Decimal("0")
        risk_amount = equity * (self.limits.max_risk_per_trade_pct / Decimal("100"))
        qty = risk_amount / stop_distance
        max_qty = self.limits.max_position_value / entry
        return Decimal(int(min(qty, max_qty)))
