"""Paper Activation Governance Service (M192–M199).

Orchestrates: eligibility → owner approval → PAPER_ACTIVE → paper portfolio
→ orders → risk → analytics → journal → reconciliation.

PAPER ONLY. No live broker. LLM cannot approve or execute.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.paper_activation.activation import (
    PaperActivationService,
    ActivationError,
)
from saathi.platform.tg.paper_activation.approvals import ActivationApprovalCenter
from saathi.platform.tg.paper_activation.analytics import compute_analytics, compare_portfolios
from saathi.platform.tg.paper_activation.journal import PaperActivationJournal
from saathi.platform.tg.paper_activation.models import (
    JournalEntry,
    PaperActivationState,
    RiskLimits,
    SimOrder,
    SimOrderType,
    SimTimeInForce,
    D,
)
from saathi.platform.tg.paper_activation.order_simulator import MarketTick
from saathi.platform.tg.paper_activation.portfolio_engine import (
    PaperPortfolioEngine,
    PortfolioEngineError,
)
from saathi.platform.tg.paper_activation.reconciliation import (
    reconcile_portfolio,
    apply_reconciliation_halt,
)
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.domain import KillSwitchScope


class PaperGovError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PaperActivationGovernanceService:
    def __init__(self) -> None:
        self.approvals = ActivationApprovalCenter()
        self.activation = PaperActivationService(self.approvals)
        self.portfolios = PaperPortfolioEngine()
        self.journal = PaperActivationJournal()
        self.kill_switches = KillSwitchStore()

    def posture(self) -> dict[str, Any]:
        return {
            "paper_only": True,
            "live_trading_authorized": False,
            "live_order_capable": False,
            "broker_credential_support": False,
            "exchange_connected": False,
            "funds_label": "SIMULATED",
            "activation_states": [s.value for s in PaperActivationState],
            "llm_boundary": {
                "may_explain": True,
                "may_summarize": True,
                "may_recommend": True,
                "may_approve": False,
                "may_change_metrics": False,
                "may_modify_journals": False,
                "may_alter_history": False,
                "may_execute_trades": False,
                "may_override_owner_approval": False,
            },
            "flow": [
                "Historical Research",
                "Qualification",
                "Owner Approval",
                "Paper Activation",
                "Paper Orders",
                "Paper Portfolio",
                "Risk Monitoring",
                "Analytics",
                "Journal",
                "Reconciliation",
                "Evidence",
            ],
            "disclaimer": "PAPER ACTIVATION GOVERNANCE — NO LIVE ORDERS — SIMULATED FUNDS",
        }

    # ── portfolios ───────────────────────────────────────────────────────────
    def create_portfolio(self, **kwargs: Any) -> dict[str, Any]:
        try:
            p = self.portfolios.create(**kwargs)
        except PortfolioEngineError as e:
            raise PaperGovError(e.code, e.message) from e
        return {"portfolio": p.to_public(), "paper_only": True}

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        p = self.portfolios.get(portfolio_id)
        if not p:
            raise PaperGovError("NOT_FOUND", "portfolio not found")
        return {"portfolio": p.to_public(), "paper_only": True}

    def list_portfolios(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "portfolios": [p.to_public() for p in self.portfolios.list(**kwargs)],
            "paper_only": True,
        }

    # ── activation ───────────────────────────────────────────────────────────
    def request_approval(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.activation.request_activation_approval(**kwargs)
        except ActivationError as e:
            raise PaperGovError(e.code, e.message) from e

    def decide_approval(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.activation.decide_approval(**kwargs)
        except ActivationError as e:
            raise PaperGovError(e.code, e.message) from e

    def list_approvals(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "approvals": [a.to_public() for a in self.approvals.list(**kwargs)],
            "paper_only": True,
            "llm_may_approve": False,
        }

    def activate_strategy(
        self,
        *,
        strategy_slug: str,
        approval_id: str,
        portfolio_id: str | None = None,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
        portfolio_name: str = "",
        starting_cash: str = "100000",
    ) -> dict[str, Any]:
        # kill switch blocks activation
        blocked = self.kill_switches.is_blocked(org_id=org_id, workspace_id=workspace_id)
        if blocked.get("blocked"):
            raise PaperGovError("KILL_SWITCH", f"kill switch blocks paper activation: {blocked.get('reason')}")

        if not portfolio_id:
            p = self.portfolios.create(
                name=portfolio_name or f"Paper:{strategy_slug}",
                starting_cash=starting_cash,
                org_id=org_id,
                workspace_id=workspace_id,
            )
            portfolio_id = p.id
        else:
            p = self.portfolios.get(portfolio_id)
            if not p:
                raise PaperGovError("NOT_FOUND", "portfolio not found")

        try:
            rec = self.activation.activate(
                strategy_slug,
                approval_id=approval_id,
                portfolio_id=portfolio_id,
                operator_identity=operator_identity,
                org_id=org_id,
                workspace_id=workspace_id,
            )
        except ActivationError as e:
            raise PaperGovError(e.code, e.message) from e
        return {
            "activation": rec.to_public(),
            "portfolio": p.to_public() if p else self.portfolios.get(portfolio_id).to_public(),
            "paper_only": True,
            "live_authorized": False,
        }

    def halt_strategy(self, strategy_slug: str, *, reason: str, **kwargs: Any) -> dict[str, Any]:
        try:
            rec = self.activation.halt(strategy_slug, reason=reason, **kwargs)
        except ActivationError as e:
            raise PaperGovError(e.code, e.message) from e
        if rec.portfolio_id:
            from saathi.platform.tg.paper_activation.models import RiskHaltReason
            try:
                self.portfolios.halt(rec.portfolio_id, reason=RiskHaltReason.STRATEGY_NOT_ACTIVE, detail=reason)
            except PortfolioEngineError:
                pass
        return {"activation": rec.to_public(), "paper_only": True}

    def list_activations(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "activations": [r.to_public() for r in self.activation.list_records(**kwargs)],
            "paper_only": True,
        }

    # ── orders ───────────────────────────────────────────────────────────────
    def place_order(
        self,
        *,
        portfolio_id: str,
        strategy_slug: str,
        symbol: str,
        side: str,
        quantity: str | Decimal,
        order_type: str = "MARKET",
        tif: str = "DAY",
        limit_price: str | None = None,
        stop_price: str | None = None,
        notes: str = "",
        reason: str = "",
        signal: dict | None = None,
        confidence: str = "",
        market_regime: str = "",
        stop: str = "",
        target: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        owner_notes: str = "",
        llm_explanation: str = "",
    ) -> dict[str, Any]:
        if self.kill_switches.is_blocked(org_id=org_id, workspace_id=workspace_id).get("blocked"):
            raise PaperGovError("KILL_SWITCH", "kill switch active — paper orders blocked")

        active = self.activation.is_paper_active(
            strategy_slug, org_id=org_id, workspace_id=workspace_id,
        )
        try:
            ot = SimOrderType(order_type.upper())
            tf = SimTimeInForce(tif.upper())
        except ValueError as e:
            raise PaperGovError("VALIDATION", f"invalid order type/tif: {e}") from e

        order = SimOrder(
            portfolio_id=portfolio_id,
            strategy_slug=strategy_slug,
            symbol=symbol.upper(),
            side=side.upper(),
            order_type=ot,
            tif=tf,
            quantity=D(quantity),
            limit_price=D(limit_price) if limit_price is not None else None,
            stop_price=D(stop_price) if stop_price is not None else None,
            notes=notes,
        )
        try:
            order = self.portfolios.submit_order(order, strategy_active=active)
        except PortfolioEngineError as e:
            raise PaperGovError(e.code, e.message) from e

        # journal always on accept path
        entry = JournalEntry(
            portfolio_id=portfolio_id,
            strategy_slug=strategy_slug,
            order_id=order.id,
            symbol=symbol.upper(),
            side=side.upper(),
            reason=reason or notes or "paper_order",
            signal=dict(signal or {}),
            confidence=confidence,
            market_regime=market_regime,
            risk={"limits": "see portfolio risk_limits"},
            stop=stop,
            target=target,
            entry=str(limit_price or stop_price or ""),
            notes=notes,
            owner_notes=owner_notes,
            llm_explanation=llm_explanation,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        self.journal.append(entry)

        return {
            "order": order.to_public(),
            "journal_entry_id": entry.id,
            "strategy_active": active,
            "paper_only": True,
            "live_order": False,
            "exchange_connected": False,
        }

    def process_market(
        self,
        portfolio_id: str,
        *,
        symbol: str,
        bid: str,
        ask: str,
        last: str,
        volume: str = "1000000",
        gap_open: bool = False,
    ) -> dict[str, Any]:
        tick = MarketTick(
            symbol=symbol.upper(),
            bid=D(bid),
            ask=D(ask),
            last=D(last),
            volume=D(volume),
            gap_open=gap_open,
        )
        try:
            return self.portfolios.process_tick(portfolio_id, tick)
        except PortfolioEngineError as e:
            raise PaperGovError(e.code, e.message) from e

    def list_orders(self, portfolio_id: str) -> dict[str, Any]:
        return {
            "orders": [o.to_public() for o in self.portfolios.list_orders(portfolio_id)],
            "paper_only": True,
        }

    def list_positions(self, portfolio_id: str) -> dict[str, Any]:
        return {
            "positions": self.portfolios.list_positions(portfolio_id),
            "paper_only": True,
            "funds_label": "SIMULATED",
        }

    # ── analytics / journal / reconcile ──────────────────────────────────────
    def analytics(self, portfolio_id: str) -> dict[str, Any]:
        p = self.portfolios.get(portfolio_id)
        if not p:
            raise PaperGovError("NOT_FOUND", "portfolio not found")
        return {"analytics": compute_analytics(p), "paper_only": True}

    def compare(self, portfolio_ids: list[str]) -> dict[str, Any]:
        ps = [self.portfolios.get(i) for i in portfolio_ids]
        ps = [p for p in ps if p]
        return compare_portfolios(ps)

    def list_journal(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "entries": [e.to_public() for e in self.journal.list(**kwargs)],
            "paper_only": True,
            "immutable": True,
        }

    def reconcile(self, portfolio_id: str, *, auto_halt: bool = True) -> dict[str, Any]:
        p = self.portfolios.get(portfolio_id)
        if not p:
            raise PaperGovError("NOT_FOUND", "portfolio not found")
        orders = self.portfolios.list_orders(portfolio_id)
        result = reconcile_portfolio(
            p,
            orders=orders,
            journal_count=len(self.journal.list(portfolio_id=portfolio_id)),
        )
        if auto_halt and result.get("fail_closed"):
            apply_reconciliation_halt(p, result)
        return {"reconciliation": result, "portfolio": p.to_public(), "paper_only": True}

    # ── kill switch ──────────────────────────────────────────────────────────
    def activate_kill_switch(self, **kwargs: Any) -> dict[str, Any]:
        ks = self.kill_switches.activate(**kwargs)
        # halt all active portfolios
        for p in self.portfolios.list():
            if p.status.value == "ACTIVE":
                from saathi.platform.tg.paper_activation.models import RiskHaltReason
                self.portfolios.halt(p.id, reason=RiskHaltReason.KILL_SWITCH, detail=kwargs.get("reason", ""))
        return {"kill_switch": ks.to_public(), "paper_only": True}

    def kill_switch_status(self, **kwargs: Any) -> dict[str, Any]:
        return {"kill_switches": self.kill_switches.status(**kwargs), "paper_only": True}

    def status(self, *, org_id: str = "local", workspace_id: str = "local") -> dict[str, Any]:
        return {
            "posture": self.posture(),
            "portfolios": len(self.portfolios.list(org_id=org_id, workspace_id=workspace_id)),
            "activations": [r.to_public() for r in self.activation.list_records(org_id=org_id, workspace_id=workspace_id)],
            "pending_approvals": len(self.approvals.list(org_id=org_id, workspace_id=workspace_id, status="PENDING")),
            "kill_switch": self.kill_switches.status(org_id=org_id, workspace_id=workspace_id),
            "paper_only": True,
            "live_authorized": False,
        }


_default: PaperActivationGovernanceService | None = None


def default_paper_gov() -> PaperActivationGovernanceService:
    global _default
    if _default is None:
        _default = PaperActivationGovernanceService()
    return _default


def reset_paper_gov_for_tests() -> PaperActivationGovernanceService:
    global _default
    _default = PaperActivationGovernanceService()
    return _default
