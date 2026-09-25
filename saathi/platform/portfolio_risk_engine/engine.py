"""PortfolioRiskEngine — independent of OMS/EG; reads ledger only."""
from __future__ import annotations

import time as _time
import hashlib
from decimal import Decimal
from typing import Any, Callable

from saathi.platform.fund_ledger.money import D, q_money
from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V1, RiskBudget
from saathi.platform.portfolio_risk_engine.drawdown import compute_drawdown
from saathi.platform.portfolio_risk_engine.history import NavHistoryStore
from saathi.platform.portfolio_risk_engine.metrics import portfolio_metrics, project_trade
from saathi.platform.portfolio_risk_engine.models import (
    LimitEvaluation,
    LimitSeverity,
    REASON_BUDGET_INVALID,
    REASON_CANDIDATE_AUTHORITY_INVALID,
    REASON_CANDIDATE_CURRENCY_MISMATCH,
    REASON_CANDIDATE_SNAPSHOT_MISMATCH,
    REASON_CANDIDATE_WEIGHT_INVALID,
    REASON_CRYPTO_EXPOSURE_LIMIT,
    REASON_DAILY_LOSS_LIMIT_EXCEEDED,
    REASON_GROSS_EXPOSURE_LIMIT,
    REASON_INVALID_QUANTITY,
    REASON_LEDGER_UNRECONCILED,
    REASON_MAX_DRAWDOWN_EXCEEDED,
    REASON_MAX_POSITION_WEIGHT_EXCEEDED,
    REASON_MAX_TOP3_CONCENTRATION,
    REASON_MAX_TOP5_CONCENTRATION,
    REASON_MAX_TRADE_NOTIONAL,
    REASON_MIN_CASH_BUFFER_BREACH,
    REASON_NAV_MISSING,
    REASON_NET_EXPOSURE_LIMIT,
    REASON_NEPSE_EXPOSURE_LIMIT,
    REASON_PRICE_MISSING,
    REASON_SHORTS_DISABLED,
    REASON_STALE_MARKET_DATA,
    REASON_WEEKLY_LOSS_LIMIT_EXCEEDED,
    RiskDecision,
    RiskResult,
    RiskState,
    TradeProposal,
    new_decision_id,
    now_ts,
)
from saathi.platform.portfolio_risk_engine.periods import period_pnl, utc_day_start, utc_week_start
from saathi.platform.portfolio_risk_engine.sizing import size_fixed_fractional, size_max_notional, size_stop_risk
from saathi.platform.portfolio_risk_engine.stress import apply_scenario, run_default_stress, DEFAULT_SCENARIOS


class PortfolioRiskEngine:
    """Deterministic PAPER risk measurement + budgets. Does not mutate ledger."""

    def __init__(
        self,
        *,
        budget: RiskBudget | None = None,
        history: NavHistoryStore | None = None,
        get_ledger_state: Callable[[str], dict] | None = None,
        get_recon_status: Callable[[str], dict] | None = None,
    ):
        self.budget = budget or PAPER_BUDGET_V1
        self.history = history or NavHistoryStore()
        self._get_state = get_ledger_state
        self._get_recon = get_recon_status

    def bind_ledger(
        self,
        get_ledger_state: Callable[[str], dict],
        get_recon_status: Callable[[str], dict] | None = None,
    ) -> "PortfolioRiskEngine":
        self._get_state = get_ledger_state
        self._get_recon = get_recon_status
        return self

    def bind_paper_service(self, paper_svc: Any) -> "PortfolioRiskEngine":
        """Bind to PaperTradingService for fund_id via account or fund_id string."""

        def state_fn(fund_or_account: str) -> dict:
            # accept fund_id or paper account_id
            if paper_svc.ledger.store.get_fund(fund_or_account):
                return paper_svc.ledger.get_state(fund_or_account)
            from saathi.platform.fund_ledger.cutover import fund_id_for_account

            fid = paper_svc.fill_posts.fund_for_account(fund_or_account) or fund_id_for_account(fund_or_account)
            return paper_svc.ledger.get_state(fid)

        def recon_fn(fund_or_account: str) -> dict:
            # best-effort: if account, use paper recon; if fund, synthetic
            try:
                return paper_svc.portfolio_reconciliation_status(
                    type("C", (), {"org_id": "", "require_permission": lambda *a, **k: None})(),
                    fund_or_account,
                )
            except Exception:
                pending = paper_svc.fill_posts.pending_count()
                return {
                    "ok": pending == 0,
                    "portfolio_status": "HEALTHY" if pending == 0 else "RECONCILIATION_REQUIRED",
                }

        return self.bind_ledger(state_fn, recon_fn)

    # ── public API ───────────────────────────────────────────────────────
    def evaluate_current_state(
        self,
        fund_id: str,
        *,
        ledger_state: dict | None = None,
        recon: dict | None = None,
        now: float | None = None,
        record_history: bool = True,
    ) -> RiskDecision:
        ts = now if now is not None else now_ts()
        state, recon_st, early = self._load(fund_id, ledger_state, recon)
        if early:
            return early

        if record_history and state.get("nav") is not None:
            self.history.record_nav(fund_id, state["nav"], ts=ts)

        metrics = portfolio_metrics(state, now=ts)
        series = self.history.series(fund_id)
        dd = compute_drawdown(series if series else [(ts, metrics["nav"])])
        daily = period_pnl(series, period_start=utc_day_start(ts), current_nav=metrics["nav"])
        weekly = period_pnl(series, period_start=utc_week_start(ts), current_nav=metrics["nav"])

        metrics["drawdown"] = dd
        metrics["daily_pnl"] = daily
        metrics["weekly_pnl"] = weekly
        metrics["budget_version"] = self.budget.version

        limits, breaches, warnings, codes = self._evaluate_limits(metrics, state, recon_st)
        result, risk_state = self._rollup(breaches, warnings, codes, recon_st, metrics)

        return RiskDecision(
            decision_id=new_decision_id(),
            result=result,
            risk_state=risk_state,
            timestamp=ts,
            budget_version=self.budget.version,
            fund_id=fund_id,
            metrics=self._public_metrics(metrics),
            limits_evaluated=limits,
            breaches=breaches,
            warnings=warnings,
            reason_codes=codes,
        )

    def evaluate_proposed_trade(
        self,
        fund_id: str,
        proposal: TradeProposal,
        *,
        ledger_state: dict | None = None,
        recon: dict | None = None,
        fee: Decimal | str = "0",
        now: float | None = None,
    ) -> RiskDecision:
        ts = now if now is not None else now_ts()
        state, recon_st, early = self._load(fund_id, ledger_state, recon)
        if early:
            early.proposal = proposal.to_public()
            return early

        if D(proposal.quantity) <= 0:
            return self._insufficient(
                fund_id, ts, [REASON_INVALID_QUANTITY], metrics={}, proposal=proposal.to_public()
            )
        if D(proposal.price) <= 0:
            return self._insufficient(
                fund_id, ts, [REASON_PRICE_MISSING], metrics={}, proposal=proposal.to_public()
            )

        # current first
        base = self.evaluate_current_state(
            fund_id, ledger_state=state, recon=recon_st, now=ts, record_history=True
        )
        if base.result == RiskResult.BLOCK and REASON_LEDGER_UNRECONCILED in base.reason_codes:
            base.proposal = proposal.to_public()
            return base

        proj = project_trade(
            state,
            side=proposal.side,
            symbol=proposal.symbol,
            quantity=D(proposal.quantity),
            price=D(proposal.price),
            fee=D(fee),
        )
        if not proj.get("ok"):
            code = proj.get("error") or REASON_INVALID_QUANTITY
            if code == "SHORTS_DISABLED":
                code = REASON_SHORTS_DISABLED
            return self._block(
                fund_id,
                ts,
                [code],
                metrics=base.metrics,
                proposal=proposal.to_public(),
                detail=str(proj.get("error")),
            )

        notional = D(proj["trade_notional"])
        pmetrics = proj["projected_metrics"]
        # attach period/dd from base (projected NAV for loss checks still use projected metrics for exposure)
        series = self.history.series(fund_id) + [(ts, pmetrics["nav"])]
        dd = compute_drawdown(series)
        pmetrics["drawdown"] = dd
        pmetrics["daily_pnl"] = base.metrics.get("daily_pnl")
        pmetrics["weekly_pnl"] = base.metrics.get("weekly_pnl")

        limits, breaches, warnings, codes = self._evaluate_limits(pmetrics, proj["projected_state"], recon_st)
        # trade notional hard limit
        te = self._check_limit(
            "max_trade_notional",
            notional,
            D(self.budget.max_trade_notional),
            REASON_MAX_TRADE_NOTIONAL,
            higher_is_breach=True,
            absolute=True,
        )
        limits.append(te)
        if te.breached:
            breaches.append(te.to_public())
            codes.append(REASON_MAX_TRADE_NOTIONAL)
        elif te.warning:
            warnings.append(te.to_public())

        result, risk_state = self._rollup(breaches, warnings, codes, recon_st, pmetrics)
        # merge base hard breaches
        if base.result == RiskResult.BLOCK:
            for c in base.reason_codes:
                if c not in codes:
                    codes.append(c)
            result = RiskResult.BLOCK
            risk_state = RiskState.BREACHED

        return RiskDecision(
            decision_id=new_decision_id(),
            result=result,
            risk_state=risk_state,
            timestamp=ts,
            budget_version=self.budget.version,
            fund_id=fund_id,
            metrics=self._public_metrics(pmetrics),
            limits_evaluated=limits,
            breaches=breaches,
            warnings=warnings,
            reason_codes=codes,
            proposal=proposal.to_public(),
            projected={
                "trade_notional": proj["trade_notional"],
                "projected_cash": proj["projected_cash"],
                "projected_nav": proj["projected_nav"],
            },
        )

    def evaluate_candidate_portfolio(
        self,
        candidate: Any,
        *,
        portfolio_snapshot: Any,
    ) -> RiskDecision:
        """Atomically enforce hard limits on a V2 candidate portfolio.

        This supplements, rather than replaces, single-trade impact checks. It
        is read-only and returns a risk decision that never constitutes an
        approval or execution authorization.
        """
        ts = candidate.decision_time.timestamp()
        codes: list[str] = []
        limits: list[LimitEvaluation] = []
        breaches: list[dict] = []

        def breach(name: str, value: Decimal, limit: Decimal, code: str, detail: str = "") -> None:
            if code not in codes:
                codes.append(code)
            ev = LimitEvaluation(
                name=name,
                severity=LimitSeverity.HARD_LIMIT,
                value=D(value),
                limit=D(limit),
                breached=True,
                warning=False,
                reason_code=code,
                detail=detail or f"{name}={value} limit={limit}",
            )
            limits.append(ev)
            breaches.append(ev.to_public())

        authority_valid = (
            candidate.mode == "PAPER"
            and candidate.authorizes_execution is False
            and candidate.risk_approved is False
            and candidate.quality.startswith("VALID")
            and candidate.market_data_mode in {"HISTORICAL", "REPLAY", "LIVE"}
            and candidate.construction_policy_version.startswith("portfolio-construction/v2.")
            and candidate.risk_budget_version == self.budget.version
            and self.budget.environment == "PAPER"
            and not self.budget.leverage_enabled
            and not self.budget.shorts_enabled
        )
        if not authority_valid:
            breach(
                "candidate_authority",
                Decimal("1"),
                Decimal("0"),
                REASON_CANDIDATE_AUTHORITY_INVALID,
                "candidate quality, policy, or proposal-only authority contract is invalid",
            )

        snapshot_valid = (
            candidate.fund_id == portfolio_snapshot.fund_id
            and candidate.portfolio_snapshot_ref == portfolio_snapshot.snapshot_ref
            and portfolio_snapshot.source_authority == "CANONICAL_FUND_LEDGER"
        )
        if not snapshot_valid:
            breach(
                "candidate_snapshot_identity",
                Decimal("1"),
                Decimal("0"),
                REASON_CANDIDATE_SNAPSHOT_MISMATCH,
            )
        if portfolio_snapshot.reconciliation_status != "HEALTHY":
            breach(
                "ledger_reconciliation",
                Decimal("1"),
                Decimal("0"),
                REASON_LEDGER_UNRECONCILED,
            )

        gross = Decimal("0")
        crypto = Decimal("0")
        nepse = Decimal("0")
        weights: list[Decimal] = []
        nav = D(portfolio_snapshot.nav)
        instrument_ids = [allocation.instrument_id for allocation in candidate.allocations]
        if len(instrument_ids) != len(set(instrument_ids)):
            breach(
                "candidate_instrument_identity",
                Decimal(len(instrument_ids)),
                Decimal(len(set(instrument_ids))),
                REASON_CANDIDATE_WEIGHT_INVALID,
                "duplicate instrument allocation identity",
            )
        expected_current_cash = D(portfolio_snapshot.cash) / nav
        if abs(D(candidate.cash_current_weight) - expected_current_cash) > Decimal("0.0000001"):
            breach(
                "candidate_current_cash_identity",
                D(candidate.cash_current_weight),
                expected_current_cash,
                REASON_CANDIDATE_WEIGHT_INVALID,
            )
        for allocation in candidate.allocations:
            weight = D(allocation.target_weight)
            weights.append(weight)
            if (
                weight < 0
                or weight > 1
                or D(allocation.current_weight) < 0
                or D(allocation.target_notional) != weight * nav
                or D(allocation.weight_change)
                != weight - D(allocation.current_weight)
            ):
                breach(
                    f"candidate_weight:{allocation.instrument_id}",
                    weight,
                    Decimal("1"),
                    REASON_CANDIDATE_WEIGHT_INVALID,
                )
            if allocation.quote_currency != portfolio_snapshot.reporting_currency:
                breach(
                    f"candidate_currency:{allocation.instrument_id}",
                    Decimal("1"),
                    Decimal("0"),
                    REASON_CANDIDATE_CURRENCY_MISMATCH,
                )
            if weight > D(self.budget.max_position_weight):
                breach(
                    f"max_position:{allocation.instrument_id}",
                    weight,
                    D(self.budget.max_position_weight),
                    REASON_MAX_POSITION_WEIGHT_EXCEEDED,
                )
            gross += max(Decimal("0"), weight)
            asset_class = allocation.asset_class.value
            if asset_class == "CRYPTO":
                crypto += max(Decimal("0"), weight)
            elif asset_class == "EQUITY" and allocation.instrument_id.startswith("NEPSE:"):
                nepse += max(Decimal("0"), weight)

        cash = D(candidate.cash_target_weight)
        tolerance = Decimal("0.0000001")
        expected_turnover = sum(
            (abs(D(allocation.weight_change)) for allocation in candidate.allocations),
            Decimal("0"),
        )
        expected_cost = sum(
            (D(allocation.estimated_cost) for allocation in candidate.allocations),
            Decimal("0"),
        )
        if (
            abs(D(candidate.turnover) - expected_turnover) > tolerance
            or abs(D(candidate.estimated_cost) - expected_cost) > tolerance
            or expected_cost < 0
        ):
            breach(
                "candidate_aggregate_identity",
                D(candidate.turnover),
                expected_turnover,
                REASON_CANDIDATE_WEIGHT_INVALID,
                "turnover or estimated-cost aggregate is inconsistent",
            )
        if cash < D(self.budget.min_cash_buffer):
            breach(
                "min_cash_buffer",
                cash,
                D(self.budget.min_cash_buffer),
                REASON_MIN_CASH_BUFFER_BREACH,
            )
        if gross > D(self.budget.max_gross_exposure) + tolerance:
            breach(
                "candidate_gross_exposure",
                gross,
                D(self.budget.max_gross_exposure),
                REASON_GROSS_EXPOSURE_LIMIT,
            )
        if abs(gross + cash - Decimal("1")) > tolerance:
            breach(
                "candidate_funded_weight_identity",
                gross + cash,
                Decimal("1"),
                REASON_CANDIDATE_WEIGHT_INVALID,
            )
        if crypto > D(self.budget.max_crypto_exposure) + tolerance:
            breach(
                "crypto_exposure",
                crypto,
                D(self.budget.max_crypto_exposure),
                REASON_CRYPTO_EXPOSURE_LIMIT,
            )
        if nepse > D(self.budget.max_nepse_exposure) + tolerance:
            breach(
                "nepse_exposure",
                nepse,
                D(self.budget.max_nepse_exposure),
                REASON_NEPSE_EXPOSURE_LIMIT,
            )
        ordered = sorted(weights, reverse=True)
        top3 = sum(ordered[:3], Decimal("0"))
        top5 = sum(ordered[:5], Decimal("0"))
        if top3 > D(self.budget.max_top3_concentration) + tolerance:
            breach("candidate_top3", top3, D(self.budget.max_top3_concentration), REASON_MAX_TOP3_CONCENTRATION)
        if top5 > D(self.budget.max_top5_concentration) + tolerance:
            breach("candidate_top5", top5, D(self.budget.max_top5_concentration), REASON_MAX_TOP5_CONCENTRATION)
        if D(portfolio_snapshot.current_drawdown) >= D(self.budget.max_drawdown):
            breach(
                "candidate_drawdown",
                D(portfolio_snapshot.current_drawdown),
                D(self.budget.max_drawdown),
                REASON_MAX_DRAWDOWN_EXCEEDED,
            )

        result = RiskResult.BLOCK if breaches else RiskResult.ALLOW
        risk_state = (
            RiskState.RECONCILIATION_REQUIRED
            if REASON_LEDGER_UNRECONCILED in codes
            else RiskState.BREACHED if breaches else RiskState.HEALTHY
        )
        decision_seed = f"{candidate.candidate_portfolio_id}|{self.budget.version}|{result.value}"
        return RiskDecision(
            decision_id="rskcand_" + hashlib.sha256(decision_seed.encode("utf-8")).hexdigest()[:16],
            result=result,
            risk_state=risk_state,
            timestamp=ts,
            budget_version=self.budget.version,
            fund_id=candidate.fund_id,
            metrics={
                "candidate_gross_exposure": str(gross),
                "candidate_cash_weight": str(cash),
                "crypto_exposure": str(crypto),
                "nepse_exposure": str(nepse),
                "position_count": len(candidate.allocations),
            },
            limits_evaluated=limits,
            breaches=breaches,
            warnings=[],
            reason_codes=codes,
            proposal=candidate.to_public(),
            projected={
                "gross_exposure": str(gross),
                "cash_weight": str(cash),
                "crypto_exposure": str(crypto),
                "nepse_exposure": str(nepse),
            },
        )

    def get_risk_snapshot(self, fund_id: str, **kwargs) -> dict:
        d = self.evaluate_current_state(fund_id, **kwargs)
        stress = []
        state = kwargs.get("ledger_state")
        if state is None and self._get_state:
            try:
                state = self._get_state(fund_id)
            except Exception:
                state = None
        if state:
            stress = run_default_stress(state)
        pub = d.to_public()
        pub["stress"] = stress
        pub["budget"] = self.budget.to_public()
        pub["risk_budget_bars"] = self._budget_bars(d)
        return pub

    def get_limit_status(self, fund_id: str, **kwargs) -> dict:
        d = self.evaluate_current_state(fund_id, **kwargs)
        return {
            "fund_id": fund_id,
            "risk_state": d.risk_state.value,
            "result": d.result.value,
            "limits": [x.to_public() for x in d.limits_evaluated],
            "breaches": d.breaches,
            "warnings": d.warnings,
            "budget_version": d.budget_version,
            "mode": "PAPER",
        }

    def get_risk_budget(self) -> dict:
        return self.budget.to_public()

    def run_stress(self, fund_id: str, *, ledger_state: dict | None = None) -> list[dict]:
        state, _, early = self._load(fund_id, ledger_state, None)
        if early:
            return [{"error": early.risk_state.value, "reason_codes": early.reason_codes}]
        return run_default_stress(state)

    def size_position(
        self,
        fund_id: str,
        *,
        symbol: str,
        price: Decimal | str,
        method: str = "fixed_fractional",
        stop_price: Decimal | str | None = None,
        fraction: Decimal | str | None = None,
        ledger_state: dict | None = None,
    ) -> dict:
        state, _, early = self._load(fund_id, ledger_state, None)
        if early:
            return {"ok": False, "reason_codes": early.reason_codes, "authorizes_execution": False}
        nav = D(state.get("nav") or "0")
        cash = D(state.get("cash") or "0")
        method = method.lower()
        if method == "stop_risk":
            if stop_price is None:
                return {"ok": False, "reason_code": "INVALID_STOP", "authorizes_execution": False}
            return size_stop_risk(nav=nav, entry_price=D(price), stop_price=D(stop_price), budget=self.budget)
        if method == "max_notional":
            return size_max_notional(price=D(price), budget=self.budget, cash=cash)
        return size_fixed_fractional(
            nav=nav, price=D(price), budget=self.budget, fraction=D(fraction) if fraction is not None else None
        )

    def command_risk_contract(self, fund_id: str, **kwargs) -> dict:
        snap = self.get_risk_snapshot(fund_id, **kwargs)
        m = snap.get("metrics") or {}
        dd = m.get("drawdown") or {}
        daily = m.get("daily_pnl") or {}
        weekly = m.get("weekly_pnl") or {}
        return {
            "label": "PAPER RISK",
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
            "risk_status": snap.get("risk_state"),
            "result": snap.get("result"),
            "nav": m.get("nav"),
            "drawdown": dd.get("current_drawdown"),
            "max_drawdown": dd.get("max_drawdown"),
            "daily_pnl": daily.get("pnl"),
            "daily_pnl_pct": daily.get("pnl_pct"),
            "weekly_pnl": weekly.get("pnl"),
            "weekly_pnl_pct": weekly.get("pnl_pct"),
            "gross_exposure": m.get("gross_exposure"),
            "gross_exposure_pct": m.get("gross_exposure_pct"),
            "cash_pct": m.get("cash_pct"),
            "largest_position": m.get("largest_position_pct"),
            "risk_budget_consumed": snap.get("risk_budget_bars"),
            "active_breaches": snap.get("breaches") or [],
            "stress_loss": (snap.get("stress") or [{}])[0].get("loss") if snap.get("stress") else None,
            "budget_version": snap.get("budget_version"),
            "reason_codes": snap.get("reason_codes") or [],
            "source": "portfolio_risk_engine",
        }

    # ── internals ────────────────────────────────────────────────────────
    def _load(self, fund_id: str, ledger_state, recon) -> tuple[dict | None, dict | None, RiskDecision | None]:
        if self.budget.environment != "PAPER" or self.budget.leverage_enabled or self.budget.shorts_enabled:
            d = self._insufficient(fund_id, now_ts(), [REASON_BUDGET_INVALID], metrics={})
            return None, None, d
        state = ledger_state
        if state is None:
            if not self._get_state:
                return None, None, self._insufficient(fund_id, now_ts(), [REASON_NAV_MISSING], metrics={})
            try:
                state = self._get_state(fund_id)
            except Exception:
                return None, None, self._insufficient(fund_id, now_ts(), [REASON_NAV_MISSING], metrics={})
        if state is None or state.get("nav") is None:
            return None, None, self._insufficient(fund_id, now_ts(), [REASON_NAV_MISSING], metrics={})

        recon_st = recon
        if recon_st is None and self._get_recon:
            try:
                recon_st = self._get_recon(fund_id)
            except Exception:
                recon_st = None
        return state, recon_st, None

    def _evaluate_limits(self, metrics: dict, state: dict, recon: dict | None):
        b = self.budget
        limits: list[LimitEvaluation] = []
        breaches: list[dict] = []
        warnings: list[dict] = []
        codes: list[str] = []

        def add(ev: LimitEvaluation):
            limits.append(ev)
            if ev.breached:
                breaches.append(ev.to_public())
                codes.append(ev.reason_code)
            elif ev.warning:
                warnings.append(ev.to_public())

        # recon
        if recon is not None and (
            recon.get("portfolio_status") == "RECONCILIATION_REQUIRED" or recon.get("ok") is False
        ):
            add(
                LimitEvaluation(
                    name="ledger_reconciliation",
                    severity=LimitSeverity.HARD_LIMIT,
                    value=Decimal("1"),
                    limit=Decimal("0"),
                    breached=True,
                    warning=False,
                    reason_code=REASON_LEDGER_UNRECONCILED,
                    detail="ledger reconciliation not HEALTHY",
                )
            )

        if state.get("invariants_ok") is False:
            add(
                LimitEvaluation(
                    name="ledger_invariants",
                    severity=LimitSeverity.HARD_LIMIT,
                    value=Decimal("1"),
                    limit=Decimal("0"),
                    breached=True,
                    warning=False,
                    reason_code=REASON_LEDGER_UNRECONCILED,
                    detail="ledger invariants failed",
                )
            )

        add(
            self._check_limit(
                "gross_exposure_pct",
                D(metrics["gross_exposure_pct"]),
                D(b.max_gross_exposure),
                REASON_GROSS_EXPOSURE_LIMIT,
            )
        )
        add(
            self._check_limit(
                "net_exposure_pct",
                D(metrics["net_exposure_pct"]),
                D(b.max_net_exposure),
                REASON_NET_EXPOSURE_LIMIT,
            )
        )
        add(
            self._check_limit(
                "largest_position_pct",
                D(metrics["largest_position_pct"]),
                D(b.max_position_weight),
                REASON_MAX_POSITION_WEIGHT_EXCEEDED,
            )
        )
        add(
            self._check_limit(
                "top3_concentration",
                D(metrics["top3_concentration"]),
                D(b.max_top3_concentration),
                REASON_MAX_TOP3_CONCENTRATION,
            )
        )
        add(
            self._check_limit(
                "top5_concentration",
                D(metrics["top5_concentration"]),
                D(b.max_top5_concentration),
                REASON_MAX_TOP5_CONCENTRATION,
            )
        )
        # cash buffer: breach if cash_pct < min (lower is breach)
        cash_pct = D(metrics["cash_pct"])
        cash_ev = LimitEvaluation(
            name="min_cash_buffer",
            severity=LimitSeverity.HARD_LIMIT,
            value=cash_pct,
            limit=D(b.min_cash_buffer),
            breached=cash_pct < D(b.min_cash_buffer) - Decimal("0.0000001"),
            warning=False,
            reason_code=REASON_MIN_CASH_BUFFER_BREACH,
            detail=f"cash_pct={cash_pct} min={b.min_cash_buffer}",
        )
        if not cash_ev.breached and cash_pct < D(b.min_cash_buffer) / max(D(b.soft_warning_ratio), Decimal("0.01")):
            # approaching from above: soft when within soft band above min
            soft_floor = D(b.min_cash_buffer) / D(b.soft_warning_ratio) if b.soft_warning_ratio else D(b.min_cash_buffer)
            # simpler: warn if cash_pct < min * 1.15
            if cash_pct < D(b.min_cash_buffer) * Decimal("1.15"):
                cash_ev = LimitEvaluation(
                    name="min_cash_buffer",
                    severity=LimitSeverity.SOFT_WARNING,
                    value=cash_pct,
                    limit=D(b.min_cash_buffer),
                    breached=False,
                    warning=True,
                    reason_code=REASON_MIN_CASH_BUFFER_BREACH,
                    detail="cash buffer approaching minimum",
                )
        add(cash_ev)

        # drawdown
        dd = D((metrics.get("drawdown") or {}).get("current_drawdown") or "0")
        add(
            self._check_limit(
                "max_drawdown",
                dd,
                D(b.max_drawdown),
                REASON_MAX_DRAWDOWN_EXCEEDED,
            )
        )

        # daily / weekly loss — fail closed if data insufficient when positions exist
        daily = metrics.get("daily_pnl") or {}
        weekly = metrics.get("weekly_pnl") or {}
        if daily.get("ok"):
            # loss is negative pnl_pct
            loss = -D(daily.get("pnl_pct") or "0")
            if loss < 0:
                loss = Decimal("0")
            add(self._check_limit("daily_loss", loss, D(b.max_daily_loss), REASON_DAILY_LOSS_LIMIT_EXCEEDED))
        elif int(metrics.get("position_count") or 0) > 0 and len(self.history.series(state.get("fund_id") or "")) == 0:
            # insufficient history: informational only for daily at first observation
            add(
                LimitEvaluation(
                    name="daily_loss",
                    severity=LimitSeverity.INFORMATIONAL,
                    value=Decimal("0"),
                    limit=D(b.max_daily_loss),
                    breached=False,
                    warning=False,
                    reason_code="DATA_INSUFFICIENT",
                    detail="daily baseline not yet established",
                )
            )
        elif daily.get("ok") is False and daily.get("reason") == "DATA_INSUFFICIENT":
            add(
                LimitEvaluation(
                    name="daily_loss",
                    severity=LimitSeverity.INFORMATIONAL,
                    value=Decimal("0"),
                    limit=D(b.max_daily_loss),
                    breached=False,
                    warning=False,
                    reason_code="DATA_INSUFFICIENT",
                    detail="daily pnl data insufficient",
                )
            )

        if weekly.get("ok"):
            loss = -D(weekly.get("pnl_pct") or "0")
            if loss < 0:
                loss = Decimal("0")
            add(self._check_limit("weekly_loss", loss, D(b.max_weekly_loss), REASON_WEEKLY_LOSS_LIMIT_EXCEEDED))

        # stale marks — hard if any position mark_stale
        stale = int(metrics.get("stale_mark_count") or 0)
        if stale > 0:
            add(
                LimitEvaluation(
                    name="stale_market_data",
                    severity=LimitSeverity.HARD_LIMIT,
                    value=Decimal(stale),
                    limit=Decimal("0"),
                    breached=True,
                    warning=False,
                    reason_code=REASON_STALE_MARKET_DATA,
                    detail=f"{stale} stale mark(s)",
                )
            )

        return limits, breaches, warnings, codes

    def _check_limit(
        self,
        name: str,
        value: Decimal,
        hard: Decimal,
        reason: str,
        *,
        higher_is_breach: bool = True,
        absolute: bool = False,
    ) -> LimitEvaluation:
        soft = self.budget.soft_threshold(hard) if not absolute else hard * D(self.budget.soft_warning_ratio)
        if higher_is_breach:
            breached = value > hard + Decimal("0.0000001")
            warning = (not breached) and value > soft + Decimal("0.0000001")
        else:
            breached = value < hard - Decimal("0.0000001")
            warning = False
        sev = LimitSeverity.HARD_LIMIT if breached else (
            LimitSeverity.SOFT_WARNING if warning else LimitSeverity.INFORMATIONAL
        )
        return LimitEvaluation(
            name=name,
            severity=sev if (breached or warning) else LimitSeverity.INFORMATIONAL,
            value=value,
            limit=hard,
            breached=breached,
            warning=warning,
            reason_code=reason,
            detail=f"{name}={value} limit={hard}",
        )

    def _rollup(self, breaches, warnings, codes, recon, metrics):
        if REASON_LEDGER_UNRECONCILED in codes:
            return RiskResult.BLOCK, RiskState.RECONCILIATION_REQUIRED
        if REASON_NAV_MISSING in codes or REASON_BUDGET_INVALID in codes:
            return RiskResult.DATA_INSUFFICIENT, RiskState.DATA_INSUFFICIENT
        if breaches:
            return RiskResult.BLOCK, RiskState.BREACHED
        if warnings:
            return RiskResult.WARN, RiskState.WARNING
        return RiskResult.ALLOW, RiskState.HEALTHY

    def _insufficient(self, fund_id, ts, codes, metrics, proposal=None):
        return RiskDecision(
            decision_id=new_decision_id(),
            result=RiskResult.DATA_INSUFFICIENT,
            risk_state=RiskState.DATA_INSUFFICIENT,
            timestamp=ts,
            budget_version=self.budget.version,
            fund_id=fund_id,
            metrics=metrics or {},
            limits_evaluated=[],
            breaches=[],
            warnings=[],
            reason_codes=list(codes),
            proposal=proposal,
        )

    def _block(self, fund_id, ts, codes, metrics, proposal=None, detail=""):
        return RiskDecision(
            decision_id=new_decision_id(),
            result=RiskResult.BLOCK,
            risk_state=RiskState.BREACHED,
            timestamp=ts,
            budget_version=self.budget.version,
            fund_id=fund_id,
            metrics=metrics or {},
            limits_evaluated=[],
            breaches=[{"reason_code": c, "detail": detail} for c in codes],
            warnings=[],
            reason_codes=list(codes),
            proposal=proposal,
        )

    def _public_metrics(self, metrics: dict) -> dict:
        out = {}
        for k, v in metrics.items():
            if isinstance(v, Decimal):
                out[k] = str(v)
            else:
                out[k] = v
        return out

    def _budget_bars(self, decision: RiskDecision) -> list[dict]:
        """UI-friendly used/remaining/limit/status."""
        m = decision.metrics
        b = self.budget

        def bar(name, used, limit, unit="fraction"):
            u = D(used or "0")
            lim = D(limit)
            rem = lim - u
            if rem < 0:
                rem = Decimal("0")
            status = "OK"
            if u > lim:
                status = "BREACHED"
            elif u > lim * D(b.soft_warning_ratio):
                status = "WARNING"
            return {
                "name": name,
                "used": str(q_money(u)),
                "remaining": str(q_money(rem)),
                "limit": str(lim),
                "unit": unit,
                "status": status,
            }

        return [
            bar("position_concentration", m.get("largest_position_pct"), b.max_position_weight),
            bar("gross_exposure", m.get("gross_exposure_pct"), b.max_gross_exposure),
            bar("drawdown", (m.get("drawdown") or {}).get("current_drawdown"), b.max_drawdown),
            bar("cash_buffer_used_inverse", D("1") - D(m.get("cash_pct") or "0"), D("1") - D(b.min_cash_buffer)),
        ]
