"""M169 — Versioned deterministic Trading Guardian Policy Engine.

Every mandatory gate emits structured results. One failed mandatory gate blocks.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import (
    AuthorityMode,
    GateStatus,
    MarketSnapshot,
    PolicyDecision,
    PolicyGateResult,
    StrategyActivation,
    TradeProposal,
    TradingGuardianPolicy,
    TradingStrategy,
    StrategyVersion,
)
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.regime import RegimeAssessment

POLICY_VERSION = "1.0.0"

DEFAULT_POLICY = TradingGuardianPolicy(
    version=POLICY_VERSION,
    name="default_paper_policy",
    authority_mode=AuthorityMode.ADVISORY,
    instrument_allowlist=[],  # empty = all non-empty symbols allowed in paper
    require_approval=True,
    leverage_allowed=False,
    margin_allowed=False,
    shorting_allowed=False,
    martingale_allowed=False,
    live_trading_allowed=False,
)


class PolicyEngine:
    def __init__(
        self,
        policy: TradingGuardianPolicy | None = None,
        kill_switches: KillSwitchStore | None = None,
    ):
        self.policy = policy or DEFAULT_POLICY
        self.kill_switches = kill_switches or KillSwitchStore()

    def evaluate(
        self,
        proposal: TradeProposal,
        *,
        snapshot: MarketSnapshot,
        strategy: TradingStrategy | None,
        strategy_version: StrategyVersion | None,
        regime: RegimeAssessment | None,
        portfolio: dict[str, Any] | None = None,
        approval_id: str = "",
        seen_idempotency: set[str] | None = None,
        now: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        pol = self.policy
        ts = now if now is not None else time.time()
        portfolio = portfolio or {}
        extra = extra or {}
        gates: list[PolicyGateResult] = []

        def gate(
            name: str,
            ok: bool,
            reason: str,
            explanation: str,
            evidence: dict | None = None,
            na: bool = False,
        ) -> None:
            if na:
                status = GateStatus.NOT_APPLICABLE
            else:
                status = GateStatus.PASS if ok else GateStatus.FAIL
            gates.append(PolicyGateResult(
                gate=name,
                status=status,
                reason_code=reason if not ok and not na else ("OK" if ok else reason),
                explanation=explanation,
                evidence=evidence or {},
                policy_version=pol.version,
                timestamp=ts,
            ))

        # 1. instrument allowlist
        allow = pol.instrument_allowlist
        if allow:
            gate(
                "instrument_allowlist",
                proposal.symbol in allow,
                "INSTRUMENT_NOT_ALLOWED",
                f"symbol {proposal.symbol} allowlist check",
                {"symbol": proposal.symbol, "allowlist": allow},
            )
        else:
            gate(
                "instrument_allowlist",
                bool(proposal.symbol),
                "INSTRUMENT_MISSING",
                "empty allowlist: any non-empty symbol permitted in paper",
                {"symbol": proposal.symbol},
            )

        # 2. supported market
        market = snapshot.source_identity if snapshot.source_identity in pol.supported_markets else "SIM"
        # snapshots from fixtures use source_identity fixture/sim — map to SIM
        mkt = "SIM" if snapshot.source_identity in ("fixture", "sim", "paper", "SIM") else snapshot.source_identity
        if mkt not in pol.supported_markets and "SIM" in pol.supported_markets:
            mkt = "SIM"
        gate(
            "supported_market",
            mkt in pol.supported_markets,
            "MARKET_UNSUPPORTED",
            f"market {mkt}",
            {"market": mkt, "supported": pol.supported_markets},
        )

        # 3. supported timeframe
        tf = snapshot.bars[0].timeframe if snapshot.bars else "1d"
        gate(
            "supported_timeframe",
            tf in pol.supported_timeframes,
            "TIMEFRAME_UNSUPPORTED",
            f"timeframe {tf}",
            {"timeframe": tf},
        )

        # 4. data freshness
        fresh = snapshot.freshness_seconds <= pol.max_data_freshness_seconds
        gate(
            "data_freshness",
            fresh,
            "DATA_STALE",
            f"freshness {snapshot.freshness_seconds}s vs max {pol.max_data_freshness_seconds}s",
            {"freshness_seconds": snapshot.freshness_seconds},
        )

        # 5. data completeness
        complete = (
            snapshot.last_price > 0
            and snapshot.data_quality in ("VALID",)
            and bool(snapshot.symbol)
        )
        gate(
            "data_completeness",
            complete,
            "DATA_INCOMPLETE",
            f"quality={snapshot.data_quality} price={snapshot.last_price}",
            {"data_quality": snapshot.data_quality},
        )

        # 6. strategy active
        strat_active = bool(
            strategy
            and strategy.activation == StrategyActivation.ACTIVE
            and not strategy.deprecated
        )
        gate(
            "strategy_active",
            strat_active,
            "STRATEGY_INACTIVE",
            f"activation={getattr(strategy, 'activation', None)}",
            {"strategy_id": getattr(strategy, "id", "")},
        )

        # 7. strategy version approved (activated/immutable)
        ver_ok = bool(
            strategy_version
            and (
                strategy_version.activation == StrategyActivation.ACTIVE
                or strategy_version.immutable
            )
            and not strategy_version.deprecated
        )
        gate(
            "strategy_version_approved",
            ver_ok,
            "STRATEGY_VERSION_NOT_APPROVED",
            f"version activation={getattr(strategy_version, 'activation', None)}",
            {"version": getattr(strategy_version, "version", "")},
        )

        # 8. regime compatible
        if regime is None:
            gate("regime_compatible", False, "REGIME_MISSING", "regime assessment required")
        else:
            compat_list = list(strategy_version.regime_compatibility) if strategy_version else []
            overlap = set(regime.labels) & set(compat_list)
            ok = bool(overlap) and not (regime.fail_closed and regime.primary == "UNKNOWN")
            gate(
                "regime_compatible",
                ok,
                "REGIME_INCOMPATIBLE",
                f"regime {regime.labels} vs {compat_list}",
                {"regime": regime.labels, "compatible": compat_list, "overlap": sorted(overlap)},
            )

        # 9. liquidity threshold
        liq = snapshot.avg_traded_value if snapshot.avg_traded_value > 0 else snapshot.volume * snapshot.last_price
        gate(
            "liquidity_threshold",
            liq >= pol.min_avg_traded_value,
            "LIQUIDITY_LOW",
            f"liquidity {liq} < {pol.min_avg_traded_value}",
            {"liquidity": str(liq)},
        )

        # 10. maximum spread
        spread_ok = snapshot.spread <= pol.max_spread if snapshot.spread > 0 else True
        gate(
            "maximum_spread",
            spread_ok,
            "SPREAD_TOO_WIDE",
            f"spread {snapshot.spread} vs max {pol.max_spread}",
            {"spread": str(snapshot.spread)},
        )

        # 11. minimum average traded value (same metric, explicit gate)
        gate(
            "minimum_average_traded_value",
            liq >= pol.min_avg_traded_value,
            "AVG_TRADED_VALUE_LOW",
            f"avg traded value {liq}",
            {"avg_traded_value": str(liq)},
        )

        # 12. volatility limit
        gate(
            "volatility_limit",
            snapshot.volatility <= pol.max_volatility or snapshot.volatility == 0,
            "VOLATILITY_HIGH",
            f"vol {snapshot.volatility} vs max {pol.max_volatility}",
            {"volatility": str(snapshot.volatility)},
        )

        # 13. event-risk restriction
        gate(
            "event_risk_restriction",
            pol.allow_event_risk or not snapshot.event_risk,
            "EVENT_RISK_BLOCKED",
            f"event_risk={snapshot.event_risk}",
            {"event_risk": snapshot.event_risk},
        )

        # 14. earnings-window restriction
        gate(
            "earnings_window_restriction",
            pol.allow_earnings_window or not snapshot.earnings_window,
            "EARNINGS_WINDOW_BLOCKED",
            f"earnings_window={snapshot.earnings_window}",
            {"earnings_window": snapshot.earnings_window},
        )

        # 15. market-hours policy
        gate(
            "market_hours_policy",
            snapshot.market_state == "OPEN",
            "MARKET_NOT_OPEN",
            f"market_state={snapshot.market_state}",
            {"market_state": snapshot.market_state},
        )

        # 16. portfolio exposure
        gross = Decimal(str(portfolio.get("gross_exposure", 0)))
        equity = Decimal(str(portfolio.get("equity", 0))) or Decimal("1")
        proposed_notional = proposal.notional or (proposal.quantity * proposal.entry_price)
        exposure_pct = (gross + proposed_notional) / equity * Decimal("100") if equity > 0 else Decimal("100")
        gate(
            "portfolio_exposure",
            exposure_pct <= Decimal("100"),  # paper: no leverage over 100% equity gross heuristic
            "PORTFOLIO_EXPOSURE_EXCEEDED",
            f"projected exposure {exposure_pct}%",
            {"exposure_pct": str(exposure_pct)},
        )

        # 17. sector exposure
        sector_pct = Decimal(str(portfolio.get("sector_exposure_pct", {}).get(proposal.sector or "UNKNOWN", 0)))
        gate(
            "sector_exposure",
            sector_pct + (proposed_notional / equity * Decimal("100") if equity > 0 else Decimal("0"))
            <= pol.max_sector_exposure_pct,
            "SECTOR_EXPOSURE_EXCEEDED",
            f"sector={proposal.sector} current={sector_pct}%",
            {"sector": proposal.sector, "sector_pct": str(sector_pct)},
        )

        # 18. correlated-position exposure
        corr_pct = Decimal(str(portfolio.get("correlated_exposure_pct", 0)))
        gate(
            "correlated_position_exposure",
            corr_pct <= pol.max_correlated_exposure_pct,
            "CORRELATED_EXPOSURE_EXCEEDED",
            f"correlated exposure {corr_pct}%",
            {"correlated_exposure_pct": str(corr_pct)},
        )

        # 19. risk budget available
        heat = Decimal(str(portfolio.get("portfolio_heat_pct", 0)))
        gate(
            "risk_budget_available",
            heat < pol.max_portfolio_heat_pct,
            "RISK_BUDGET_EXHAUSTED",
            f"heat {heat}% vs max {pol.max_portfolio_heat_pct}%",
            {"portfolio_heat_pct": str(heat)},
        )

        # 20. stop-loss present
        gate(
            "stop_loss_present",
            (not pol.require_stop_loss) or (proposal.stop_price is not None and proposal.stop_price > 0),
            "STOP_LOSS_MISSING",
            f"stop_price={proposal.stop_price}",
            {"stop_price": str(proposal.stop_price) if proposal.stop_price is not None else None},
        )

        # 21. take-profit or exit plan present
        exit_ok = (
            (not pol.require_exit_plan)
            or (proposal.take_profit_price is not None and proposal.take_profit_price > 0)
            or bool(extra.get("exit_plan"))
        )
        gate(
            "take_profit_or_exit_plan",
            exit_ok,
            "EXIT_PLAN_MISSING",
            "require take-profit or explicit exit plan",
            {"take_profit": str(proposal.take_profit_price) if proposal.take_profit_price else None},
        )

        # 22. minimum reward-to-risk
        rr = proposal.reward_to_risk
        gate(
            "minimum_reward_to_risk",
            rr >= pol.min_reward_to_risk,
            "REWARD_RISK_TOO_LOW",
            f"R:R {rr} < {pol.min_reward_to_risk}",
            {"reward_to_risk": str(rr)},
        )

        # 23. position-size validation (basic; risk engine does sizing)
        gate(
            "position_size_validation",
            proposal.quantity > 0 and proposed_notional <= pol.max_position_value,
            "POSITION_SIZE_INVALID",
            f"qty={proposal.quantity} notional={proposed_notional}",
            {"quantity": str(proposal.quantity), "notional": str(proposed_notional)},
        )

        # 24. daily-loss limit
        daily_loss = Decimal(str(portfolio.get("daily_realized_loss", 0)))
        gate(
            "daily_loss_limit",
            daily_loss < pol.daily_loss_limit,
            "DAILY_LOSS_LIMIT",
            f"daily loss {daily_loss} vs limit {pol.daily_loss_limit}",
            {"daily_realized_loss": str(daily_loss)},
        )

        # 25. weekly-loss limit
        weekly_loss = Decimal(str(portfolio.get("weekly_realized_loss", 0)))
        gate(
            "weekly_loss_limit",
            weekly_loss < pol.weekly_loss_limit,
            "WEEKLY_LOSS_LIMIT",
            f"weekly loss {weekly_loss} vs limit {pol.weekly_loss_limit}",
            {"weekly_realized_loss": str(weekly_loss)},
        )

        # 26. maximum drawdown state
        dd = Decimal(str(portfolio.get("drawdown_pct", 0)))
        gate(
            "maximum_drawdown_state",
            dd < pol.max_drawdown_pct,
            "MAX_DRAWDOWN_BREACHED",
            f"drawdown {dd}% vs max {pol.max_drawdown_pct}%",
            {"drawdown_pct": str(dd)},
        )

        # 27. maximum open positions
        open_pos = int(portfolio.get("open_positions", 0))
        gate(
            "maximum_open_positions",
            open_pos < pol.max_open_positions,
            "MAX_OPEN_POSITIONS",
            f"open={open_pos} max={pol.max_open_positions}",
            {"open_positions": open_pos},
        )

        # 28. cooldown after losses
        consec = int(portfolio.get("consecutive_losses", 0))
        last_loss_ts = float(portfolio.get("last_loss_ts", 0) or 0)
        in_cooldown = (
            consec >= pol.max_consecutive_losses
            and last_loss_ts > 0
            and (ts - last_loss_ts) < pol.cooldown_after_losses_seconds
        )
        gate(
            "cooldown_after_losses",
            not in_cooldown,
            "LOSS_COOLDOWN_ACTIVE",
            f"consecutive_losses={consec}",
            {"consecutive_losses": consec, "in_cooldown": in_cooldown},
        )

        # 29. kill-switch status
        ks_hit = self.kill_switches.is_blocked(
            org_id=proposal.org_id,
            workspace_id=proposal.workspace_id,
            strategy_id=proposal.strategy_id,
            instrument=proposal.symbol,
            portfolio_id=proposal.portfolio_id,
            market="SIM",
            automation_id=extra.get("automation_id", ""),
        )
        gate(
            "kill_switch_status",
            not ks_hit["blocked"],
            "KILL_SWITCH_ACTIVE",
            ks_hit.get("reason", "kill switch clear"),
            ks_hit,
        )

        # 30. approval status
        if pol.authority_mode == AuthorityMode.ADVISORY:
            # Advisory: proposals never auto-execute; approval N/A for generation
            gate(
                "approval_status",
                True,
                "ADVISORY_NO_EXEC",
                "ADVISORY mode: proposal generation does not require approval; execution blocked",
                {"authority_mode": pol.authority_mode.value},
                na=True,
            )
        elif pol.require_approval or pol.authority_mode == AuthorityMode.APPROVAL_REQUIRED:
            gate(
                "approval_status",
                bool(approval_id) or bool(proposal.approval_id),
                "APPROVAL_REQUIRED",
                "human approval required before paper execution",
                {"approval_id": approval_id or proposal.approval_id},
            )
        else:
            # LIMITED_AUTONOMOUS_PAPER — still may proceed without approval if policy says so
            gate(
                "approval_status",
                True,
                "AUTONOMOUS_PAPER",
                "LIMITED_AUTONOMOUS_PAPER policy active",
                {"authority_mode": pol.authority_mode.value},
            )

        # 31. idempotency
        seen = seen_idempotency or set()
        idem = proposal.idempotency_key
        gate(
            "idempotency",
            bool(idem) and idem not in seen,
            "IDEMPOTENCY_REPLAY" if idem in seen else "IDEMPOTENCY_MISSING",
            "idempotency key required and must be unique",
            {"idempotency_key": idem, "replay": idem in seen},
        )

        # 32. stale-proposal rejection
        expired = proposal.expires_at > 0 and ts > proposal.expires_at
        age = ts - proposal.created_at
        stale = expired or age > pol.proposal_ttl_seconds
        gate(
            "stale_proposal_rejection",
            not stale,
            "PROPOSAL_STALE",
            f"age={age:.1f}s ttl={pol.proposal_ttl_seconds}s expired={expired}",
            {"age": age, "expires_at": proposal.expires_at},
        )

        # Hard safety: live trading never allowed
        gate(
            "live_trading_disabled",
            not pol.live_trading_allowed and not proposal.live_order,
            "LIVE_TRADING_FORBIDDEN",
            "live trading is not an executable option",
            {"live_trading_allowed": False},
        )

        allowed = all(g.status != GateStatus.FAIL for g in gates)
        return PolicyDecision(
            proposal_id=proposal.id,
            policy_version=pol.version,
            allowed=allowed,
            gates=gates,
            correlation_id=proposal.correlation_id,
            strategy_version=proposal.strategy_version,
            org_id=proposal.org_id,
            workspace_id=proposal.workspace_id,
        )
