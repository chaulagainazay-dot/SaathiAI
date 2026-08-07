"""M200–M207 — Durable Paper Governance Service.

Persists portfolios, approvals, orders, fills, events, campaigns.
Restart-safe order queue. PAPER ONLY.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import make_event, fingerprint
from saathi.platform.tg.paper_activation.durable.recovery import (
    create_backup,
    verify_backup,
    restore_isolated,
    replay_portfolio_cash,
)
from saathi.platform.tg.paper_activation.durable.store import (
    DurablePaperStore,
    DurableStoreError,
    IdempotencyConflict,
    VersionConflict,
)
from saathi.platform.tg.paper_activation.models import (
    D,
    JournalEntry,
    PaperActivationState,
    RiskLimits,
    SimOrder,
    SimOrderStatus,
    SimOrderType,
    SimTimeInForce,
    PortfolioStatus,
    RiskHaltReason,
)
from saathi.platform.tg.paper_activation.order_simulator import MarketTick, OrderSimulator
from saathi.platform.tg.paper_activation.risk_controls import RiskController
from saathi.platform.tg.paper_activation.reconciliation import reconcile_portfolio
from saathi.platform.tg.paper_activation.analytics import compute_analytics
from saathi.platform.tg.domain import StrategyEvaluationVerdict
from saathi.platform.tg.data_contract import is_authoritative, NON_AUTHORITATIVE


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class DurableGovError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


FORBIDDEN_APPROVER = ("llm:", "strategy:", "agent:", "model:", "bot:")


def _assert_human(identity: str) -> None:
    low = (identity or "").lower()
    if not low.strip():
        raise DurableGovError("OPERATOR_REQUIRED", "operator required")
    for p in FORBIDDEN_APPROVER:
        if low.startswith(p):
            raise DurableGovError("SELF_APPROVAL_FORBIDDEN", f"{identity} cannot approve/activate")


class DurablePaperGovernanceService:
    def __init__(self, store: DurablePaperStore | None = None, db_path: str | Path | None = None):
        self.store = store or DurablePaperStore(db_path)
        self.worker_id = f"worker_{uuid.uuid4().hex[:8]}"

    def posture(self) -> dict[str, Any]:
        h = self.store.health()
        return {
            "paper_only": True,
            "live_trading_authorized": False,
            "live_order_capable": False,
            "broker_credential_support": False,
            "exchange_connected": False,
            "funds_label": "SIMULATED",
            "durable": True,
            "storage": h,
            "llm_boundary": {
                "llm_may_approve": False,
                "llm_may_execute": False,
                "llm_may_modify_ledger": False,
                "llm_may_release_kill_switch": False,
                "llm_may_authorize_live": False,
                "may_explain": True,
                "may_summarize": True,
                "may_recommend": True,
            },
            "disclaimer": "DURABLE PAPER OPERATIONS — LIVE TRADING NOT AUTHORIZED",
        }

    def storage_status(self) -> dict[str, Any]:
        return self.store.health()

    def migrate(self) -> dict[str, Any]:
        return self.store.migrate()

    # ── portfolios ───────────────────────────────────────────────────────────
    def create_portfolio(
        self,
        *,
        name: str = "Paper Fund",
        starting_cash: str = "100000",
        base_currency: str = "USD",
        org_id: str = "local",
        workspace_id: str = "local",
        idempotency_key: str = "",
        risk_limits: Any = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if idempotency_key:
            prev = self.store.get_idempotent("portfolio.create", idempotency_key)
            if prev:
                return prev["result"]
        cash = str(D(starting_cash))
        if D(cash) <= 0:
            raise DurableGovError("VALIDATION", "starting cash must be positive")
        pid = _id("pport")
        limits = risk_limits.to_public() if hasattr(risk_limits, "to_public") else (risk_limits or RiskLimits().to_public())
        p = {
            "id": pid, "name": name, "status": "ACTIVE", "org_id": org_id, "workspace_id": workspace_id,
            "starting_cash": cash, "cash": cash, "reserved_cash": "0", "realized_pnl": "0",
            "fees_paid": "0", "slippage_paid": "0", "peak_equity": cash,
            "day_start_equity": cash, "week_start_equity": cash, "month_start_equity": cash,
            "halt_reason": "NONE", "halt_detail": "", "risk_limits": limits,
            "marks": {}, "base_currency": base_currency, "created_at": time.time(),
        }
        self.store.save_portfolio(p)
        self.store.append_event(make_event(
            "portfolio.created", aggregate_type="portfolio", aggregate_id=pid,
            payload={"name": name, "starting_cash": cash},
            actor_type="operator", idempotency_key=idempotency_key or f"pc:{pid}",
        ))
        out = {"portfolio": self._public_portfolio(p), "paper_only": True}
        if idempotency_key:
            self.store.put_idempotent("portfolio.create", idempotency_key, fingerprint(p), out)
        return out

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            raise DurableGovError("NOT_FOUND", "portfolio not found")
        positions = self.store.list_positions(portfolio_id)
        return {"portfolio": self._public_portfolio(p, positions), "paper_only": True}

    def list_portfolios(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "portfolios": [self._public_portfolio(p) for p in self.store.list_portfolios(**kwargs)],
            "paper_only": True,
        }

    def _public_portfolio(self, p: dict[str, Any], positions: list | None = None) -> dict[str, Any]:
        pos_val = Decimal("0")
        marks = p.get("marks") or {}
        positions = positions if positions is not None else self.store.list_positions(p["id"])
        pos_pub = {}
        for pos in positions:
            q = D(pos["quantity"])
            if q == 0:
                continue
            mark = D(marks.get(pos["symbol"], pos["avg_price"]))
            pos_val += q * mark
            pos_pub[pos["symbol"]] = {
                "symbol": pos["symbol"], "quantity": pos["quantity"],
                "avg_price": pos["avg_price"], "realized_pnl": pos["realized_pnl"],
                "unrealized_pnl": str((mark - D(pos["avg_price"])) * q),
                "market_value": str(q * mark), "strategy_slug": pos.get("strategy_slug", ""),
                "paper_only": True,
            }
        equity = D(p["cash"]) + pos_val
        peak = D(p.get("peak_equity", p["cash"]))
        if equity > peak:
            peak = equity
        dd = ((peak - equity) / peak * 100) if peak > 0 else Decimal("0")
        return {
            **{k: p[k] for k in p if k not in ("risk_limits", "marks")},
            "risk_limits": p.get("risk_limits", {}),
            "marks": marks,
            "equity": str(equity),
            "buying_power": p["cash"],
            "positions": pos_pub,
            "drawdown_pct": str(dd),
            "daily_pnl": str(equity - D(p.get("day_start_equity", p["cash"]))),
            "weekly_pnl": str(equity - D(p.get("week_start_equity", p["cash"]))),
            "monthly_pnl": str(equity - D(p.get("month_start_equity", p["cash"]))),
            "funds_label": "SIMULATED",
            "paper_only": True,
            "live_authorized": False,
            "exchange_connected": False,
            "disclaimer": "SIMULATED FUNDS — PAPER ONLY — NO LIVE ORDERS",
        }

    # ── approvals / activation ───────────────────────────────────────────────
    def request_approval(
        self,
        *,
        strategy_slug: str,
        qualification: dict[str, Any],
        reason: str,
        operator_id: str,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
        dataset_id: str = "",
        dataset_fingerprint: str = "",
        strategy_version: str = "1.0.0",
    ) -> dict[str, Any]:
        _assert_human(operator_identity)
        if not (reason or "").strip():
            raise DurableGovError("REASON_REQUIRED", "reason required")
        verdict = str(qualification.get("verdict") or "")
        cls = str(qualification.get("data_classification") or "")
        gates = qualification.get("gates") or {}
        ok = (
            verdict == StrategyEvaluationVerdict.PAPER_ELIGIBLE.value
            and (qualification.get("authoritative") or is_authoritative(cls))
            and gates.get("walk_forward_completed")
            and gates.get("stress_completed")
            and gates.get("monte_carlo_completed")
            and gates.get("acceptable_risk_of_ruin")
        )
        if not ok:
            raise DurableGovError("NOT_PAPER_ELIGIBLE", "strategy not eligible for paper activation")
        aid = _id("paap")
        qfp = fingerprint(qualification)
        a = {
            "id": aid, "org_id": org_id, "workspace_id": workspace_id,
            "strategy_slug": strategy_slug, "strategy_version": strategy_version,
            "dataset_id": dataset_id, "dataset_fingerprint": dataset_fingerprint,
            "qualification_fingerprint": qfp, "status": "PENDING", "reason": reason.strip(),
            "operator_id": operator_id, "operator_identity": operator_identity,
            "created_at": time.time(), "expires_at": time.time() + 7 * 86400,
            "single_use": True, "evidence": {"qualification_verdict": verdict},
        }
        self.store.save_approval(a)
        self.store.append_event(make_event(
            "journal.created",
            aggregate_type="approval", aggregate_id=aid,
            payload={"action": "approval_requested", "strategy_slug": strategy_slug, "status": "PENDING"},
            actor_type="operator", actor_id=operator_identity,
            idempotency_key=f"appr_req:{aid}",
        ))
        act = {
            "id": _id("pact"), "org_id": org_id, "workspace_id": workspace_id,
            "strategy_slug": strategy_slug, "strategy_version": strategy_version,
            "state": PaperActivationState.APPROVAL_PENDING.value,
            "qualification_verdict": verdict, "qualification_fingerprint": qfp,
            "dataset_id": dataset_id, "dataset_fingerprint": dataset_fingerprint,
            "approval_id": aid, "history": [{"event": "approval_requested", "ts": time.time()}],
        }
        self.store.save_activation(act)
        return {
            "approval": self.store.get_approval(aid),
            "activation": self.store.get_activation(strategy_slug, org_id=org_id, workspace_id=workspace_id),
            "paper_only": True,
        }

    def decide_approval(
        self, approval_id: str, *, decision: str, operator_id: str, operator_identity: str,
        notes: str = "", reason: str = "",
    ) -> dict[str, Any]:
        _assert_human(operator_identity)
        a = self.store.get_approval(approval_id)
        if not a:
            raise DurableGovError("NOT_FOUND", "approval not found")
        if a["status"] != "PENDING":
            raise DurableGovError("NOT_PENDING", f"status={a['status']}")
        d = decision.lower().strip()
        if d == "approve":
            a["status"] = "APPROVED"
            evt = "strategy.approved"
        elif d == "reject":
            a["status"] = "REJECTED"
            a["rejection_reason"] = reason or notes
            evt = "order.rejected"  # not ideal - use audit
            evt = "reconciliation.failed"  # no - just use strategy event with payload
        else:
            raise DurableGovError("INVALID_DECISION", decision)
        a["decided_at"] = time.time()
        a["operator_identity"] = operator_identity
        a["notes"] = notes
        a["immutable"] = True
        self.store.save_approval(a)
        if d == "approve":
            self.store.append_event(make_event(
                "strategy.approved", aggregate_type="approval", aggregate_id=approval_id,
                payload={"strategy_slug": a["strategy_slug"]},
                actor_type="operator", actor_id=operator_identity,
                idempotency_key=f"appr_dec:{approval_id}:approve",
            ))
            act = self.store.get_activation(a["strategy_slug"], org_id=a["org_id"], workspace_id=a["workspace_id"])
            if act:
                act["state"] = PaperActivationState.PAPER_APPROVED.value
                act["history"] = list(act.get("history") or []) + [{"event": "approved", "ts": time.time()}]
                self.store.save_activation(act)
        return {"approval": self.store.get_approval(approval_id), "paper_only": True, "llm_may_approve": False}

    def activate_strategy(
        self,
        *,
        strategy_slug: str,
        approval_id: str,
        portfolio_id: str | None = None,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
        starting_cash: str = "100000",
        portfolio_name: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        _assert_human(operator_identity)
        if self.store.kill_switch_active(org_id=org_id, workspace_id=workspace_id):
            raise DurableGovError("KILL_SWITCH", "kill switch blocks activation")
        if not self.store.health().get("status") == "HEALTHY":
            raise DurableGovError("STORE_UNHEALTHY", "durable store not healthy")
        if idempotency_key:
            prev = self.store.get_idempotent("activation", idempotency_key)
            if prev:
                return prev["result"]
        try:
            self.store.consume_approval_once(approval_id, actor=operator_identity)
        except DurableStoreError as e:
            raise DurableGovError(e.code, e.message) from e
        self.store.append_event(make_event(
            "approval.consumed", aggregate_type="approval", aggregate_id=approval_id,
            payload={"strategy_slug": strategy_slug},
            actor_type="operator", actor_id=operator_identity,
            idempotency_key=f"consume:{approval_id}",
        ))
        if not portfolio_id:
            created = self.create_portfolio(
                name=portfolio_name or f"Paper:{strategy_slug}",
                starting_cash=starting_cash, org_id=org_id, workspace_id=workspace_id,
            )
            portfolio_id = created["portfolio"]["id"]
        # recon required
        recon = self.reconcile(portfolio_id, auto_halt=False)
        if recon["reconciliation"].get("fail_closed"):
            raise DurableGovError("UNRECONCILED", "portfolio unreconciled — cannot activate")
        act = self.store.get_activation(strategy_slug, org_id=org_id, workspace_id=workspace_id) or {
            "id": _id("pact"), "org_id": org_id, "workspace_id": workspace_id,
            "strategy_slug": strategy_slug, "history": [],
        }
        if act.get("state") == PaperActivationState.PAPER_ACTIVE.value and act.get("portfolio_id") == portfolio_id:
            out = {"activation": act, "portfolio": self.get_portfolio(portfolio_id)["portfolio"], "paper_only": True}
            return out
        act["state"] = PaperActivationState.PAPER_ACTIVE.value
        act["approval_id"] = approval_id
        act["portfolio_id"] = portfolio_id
        act["activated_at"] = time.time()
        act["history"] = list(act.get("history") or []) + [{"event": "activated", "ts": time.time()}]
        self.store.save_activation(act)
        self.store.append_event(make_event(
            "strategy.activated", aggregate_type="activation", aggregate_id=act["id"],
            payload={"strategy_slug": strategy_slug, "portfolio_id": portfolio_id},
            actor_type="operator", actor_id=operator_identity,
            idempotency_key=idempotency_key or f"act:{approval_id}",
        ))
        out = {
            "activation": self.store.get_activation(strategy_slug, org_id=org_id, workspace_id=workspace_id),
            "portfolio": self.get_portfolio(portfolio_id)["portfolio"],
            "paper_only": True,
            "live_authorized": False,
        }
        if idempotency_key:
            self.store.put_idempotent("activation", idempotency_key, fingerprint(out), out)
        return out

    # ── orders ───────────────────────────────────────────────────────────────
    def place_order(
        self,
        *,
        portfolio_id: str,
        strategy_slug: str,
        symbol: str,
        side: str,
        quantity: str,
        order_type: str = "MARKET",
        tif: str = "DAY",
        limit_price: str | None = None,
        stop_price: str | None = None,
        reason: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        idempotency_key: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if self.store.kill_switch_active(org_id=org_id, workspace_id=workspace_id):
            raise DurableGovError("KILL_SWITCH", "kill switch active")
        if idempotency_key:
            prev = self.store.get_idempotent(f"order:{portfolio_id}", idempotency_key)
            if prev:
                return prev["result"]
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            raise DurableGovError("NOT_FOUND", "portfolio not found")
        if p["status"] != "ACTIVE":
            raise DurableGovError("PORTFOLIO_HALTED", f"status={p['status']}")
        if p.get("halt_reason") not in ("NONE", "", None):
            raise DurableGovError("PORTFOLIO_HALTED", p.get("halt_reason", ""))
        act = self.store.get_activation(strategy_slug, org_id=org_id, workspace_id=workspace_id)
        if not act or act.get("state") != PaperActivationState.PAPER_ACTIVE.value:
            raise DurableGovError("STRATEGY_NOT_ACTIVE", "strategy not PAPER_ACTIVE")

        order = {
            "id": _id("pord"), "portfolio_id": portfolio_id, "strategy_slug": strategy_slug,
            "symbol": symbol.upper(), "side": side.upper(), "order_type": order_type.upper(),
            "tif": tif.upper(), "quantity": str(D(quantity)), "filled_qty": "0",
            "limit_price": limit_price, "stop_price": stop_price, "status": "ACCEPTED",
            "reject_reason": "", "avg_fill_price": "0", "fees": "0", "slippage": "0",
            "fills": [], "notes": notes, "correlation_id": _id("corr"),
            "idempotency_key": idempotency_key, "sim_inputs": {"fee_bps": "5", "slippage_bps": "5"},
            "created_at": time.time(),
        }
        # risk pre-check
        sim_order = SimOrder(
            id=order["id"], portfolio_id=portfolio_id, strategy_slug=strategy_slug,
            symbol=order["symbol"], side=order["side"],
            order_type=SimOrderType(order["order_type"]) if order["order_type"] in SimOrderType.__members__ else SimOrderType.MARKET,
            tif=SimTimeInForce(order["tif"]) if order["tif"] in SimTimeInForce.__members__ else SimTimeInForce.DAY,
            quantity=D(quantity),
            limit_price=D(limit_price) if limit_price else None,
            stop_price=D(stop_price) if stop_price else None,
        )
        # minimal portfolio adapter for risk
        from saathi.platform.tg.paper_activation.models import PaperPortfolio, PaperPosition
        pp = PaperPortfolio(
            id=portfolio_id, cash=D(p["cash"]), status=PortfolioStatus.ACTIVE,
            risk_limits=RiskLimits(), marks={k: D(v) for k, v in (p.get("marks") or {}).items()},
        )
        for pos in self.store.list_positions(portfolio_id):
            pp.positions[pos["symbol"]] = PaperPosition(
                symbol=pos["symbol"], quantity=D(pos["quantity"]), avg_price=D(pos["avg_price"]),
            )
        gate = RiskController(pp.risk_limits).pre_trade_check(pp, sim_order)
        if not gate["ok"]:
            order["status"] = "REJECTED"
            order["reject_reason"] = gate["reason"]
            self.store.save_order(order)
            self.store.append_event(make_event(
                "order.rejected", aggregate_type="order", aggregate_id=order["id"],
                payload={"reason": gate["reason"]}, actor_type="system",
            ))
            out = {"order": order, "paper_only": True, "live_order": False}
            if idempotency_key:
                self.store.put_idempotent(f"order:{portfolio_id}", idempotency_key, fingerprint(order), out)
            return out

        try:
            self.store.save_order(order)
        except IdempotencyConflict as e:
            raise DurableGovError(e.code, e.message) from e
        self.store.enqueue_order(order["id"], portfolio_id)
        self.store.append_event(make_event(
            "order.submitted", aggregate_type="order", aggregate_id=order["id"],
            payload={"symbol": order["symbol"], "side": order["side"], "qty": order["quantity"]},
            actor_type="operator", idempotency_key=idempotency_key or f"sub:{order['id']}",
        ))
        self.store.append_event(make_event(
            "order.accepted", aggregate_type="order", aggregate_id=order["id"],
            payload={"status": "ACCEPTED"}, actor_type="system",
            idempotency_key=f"acc:{order['id']}",
        ))
        jid = _id("pjnl")
        self.store.append_journal({
            "id": jid, "portfolio_id": portfolio_id, "strategy_slug": strategy_slug,
            "order_id": order["id"], "symbol": order["symbol"], "side": order["side"],
            "reason": reason or notes or "paper_order", "org_id": org_id, "workspace_id": workspace_id,
            "created_at": time.time(),
        })
        self.store.append_event(make_event(
            "journal.created", aggregate_type="journal", aggregate_id=jid,
            payload={"order_id": order["id"]}, actor_type="system",
        ))
        out = {
            "order": self.store.get_order(order["id"]),
            "journal_entry_id": jid,
            "paper_only": True,
            "live_order": False,
            "exchange_connected": False,
        }
        if idempotency_key:
            self.store.put_idempotent(f"order:{portfolio_id}", idempotency_key, fingerprint(order), out)
        return out

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
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            raise DurableGovError("NOT_FOUND", "portfolio not found")
        p["marks"] = {**(p.get("marks") or {}), symbol.upper(): last}
        self.store.save_portfolio(p, expected_version=p.get("version"))

        tick = MarketTick(
            symbol=symbol.upper(), bid=D(bid), ask=D(ask), last=D(last),
            volume=D(volume), gap_open=gap_open, ts=time.time(),
        )
        sim = OrderSimulator()
        results = []
        for o in self.store.list_orders(portfolio_id):
            if o["symbol"] != symbol.upper():
                continue
            if o["status"] in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
                continue
            order = SimOrder(
                id=o["id"], portfolio_id=portfolio_id, strategy_slug=o["strategy_slug"],
                symbol=o["symbol"], side=o["side"],
                order_type=SimOrderType(o["order_type"]) if o["order_type"] in SimOrderType.__members__ else SimOrderType.MARKET,
                tif=SimTimeInForce(o["tif"]) if o["tif"] in SimTimeInForce.__members__ else SimTimeInForce.DAY,
                quantity=D(o["quantity"]), filled_qty=D(o["filled_qty"]),
                limit_price=D(o["limit_price"]) if o.get("limit_price") else None,
                stop_price=D(o["stop_price"]) if o.get("stop_price") else None,
                status=SimOrderStatus(o["status"]) if o["status"] in SimOrderStatus.__members__ else SimOrderStatus.OPEN,
                avg_fill_price=D(o.get("avg_fill_price", 0)),
                fees=D(o.get("fees", 0)), slippage=D(o.get("slippage", 0)),
                fills=list(o.get("fills") or []),
            )
            r = sim.try_fill(order, tick)
            if r.get("filled"):
                effect_key = f"fill:{order.id}:{order.filled_qty}:{r['price']}:{r['qty']}"
                if not self.store.mark_effect(effect_key, order_id=order.id, fill_ref=r["price"]):
                    results.append({"order_id": order.id, "filled": False, "reason": "duplicate_effect"})
                    continue
                self._apply_fill_durable(portfolio_id, order, r)
                evt_type = "order.filled" if order.status == SimOrderStatus.FILLED else "order.partially_filled"
                self.store.append_event(make_event(
                    evt_type, aggregate_type="order", aggregate_id=order.id,
                    payload=r, actor_type="system", idempotency_key=effect_key,
                ))
            # persist order state
            o2 = self.store.get_order(order.id) or o
            o2["status"] = order.status.value
            o2["filled_qty"] = str(order.filled_qty)
            o2["avg_fill_price"] = str(order.avg_fill_price)
            o2["fees"] = str(order.fees)
            o2["slippage"] = str(order.slippage)
            o2["fills"] = order.fills
            o2["reject_reason"] = order.reject_reason
            self.store.save_order(o2, expected_version=o2.get("version"))
            results.append({"order_id": order.id, **r, "status": order.status.value})

        # risk post-check
        p2 = self.store.get_portfolio(portfolio_id)
        from saathi.platform.tg.paper_activation.models import PaperPortfolio, PaperPosition
        pp = PaperPortfolio(
            id=portfolio_id, cash=D(p2["cash"]), peak_equity=D(p2.get("peak_equity", p2["cash"])),
            day_start_equity=D(p2.get("day_start_equity", p2["cash"])),
            week_start_equity=D(p2.get("week_start_equity", p2["cash"])),
            marks={k: D(v) for k, v in (p2.get("marks") or {}).items()},
            risk_limits=RiskLimits(),
        )
        for pos in self.store.list_positions(portfolio_id):
            pp.positions[pos["symbol"]] = PaperPosition(
                symbol=pos["symbol"], quantity=D(pos["quantity"]), avg_price=D(pos["avg_price"]),
            )
        post = RiskController().post_trade_check(pp)
        if post.get("halt"):
            p2["status"] = "HALTED"
            p2["halt_reason"] = post["reason"]
            p2["halt_detail"] = post.get("detail", "")
            self.store.save_portfolio(p2, expected_version=p2.get("version"))
            self.store.append_event(make_event(
                "risk.limit_breached", aggregate_type="portfolio", aggregate_id=portfolio_id,
                payload=post, actor_type="system",
            ))
            self.store.append_event(make_event(
                "portfolio.halted", aggregate_type="portfolio", aggregate_id=portfolio_id,
                payload={"reason": post["reason"]}, actor_type="system",
            ))
        return {"results": results, "portfolio": self.get_portfolio(portfolio_id)["portfolio"], "risk": post, "paper_only": True}

    def _apply_fill_durable(self, portfolio_id: str, order: SimOrder, fill: dict[str, Any]) -> None:
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            return
        qty = D(fill["qty"])
        px = D(fill["price"])
        fee = D(fill.get("fee", 0))
        side = order.side.upper()
        sym = order.symbol
        positions = {pos["symbol"]: pos for pos in self.store.list_positions(portfolio_id)}
        pos = positions.get(sym) or {
            "symbol": sym, "quantity": "0", "avg_price": "0", "realized_pnl": "0",
            "fees": "0", "strategy_slug": order.strategy_slug, "lots": [], "history": [],
        }
        if side == "BUY":
            cost = qty * px + fee
            p["cash"] = str(D(p["cash"]) - cost)
            p["fees_paid"] = str(D(p.get("fees_paid", 0)) + fee)
            old_q = D(pos["quantity"])
            new_q = old_q + qty
            if new_q > 0:
                pos["avg_price"] = str((D(pos["avg_price"]) * old_q + px * qty) / new_q)
            pos["quantity"] = str(new_q)
            pos["fees"] = str(D(pos.get("fees", 0)) + fee)
            lots = list(pos.get("lots") or [])
            lots.append({"lot_id": _id("lot"), "quantity": str(qty), "avg_price": str(px), "fees": str(fee)})
            pos["lots"] = lots
            hist = list(pos.get("history") or [])
            hist.append({"event": "buy", "qty": str(qty), "price": str(px), "fee": str(fee)})
            pos["history"] = hist
            self.store.append_event(make_event(
                "position.opened" if old_q == 0 else "position.increased",
                aggregate_type="position", aggregate_id=f"{portfolio_id}:{sym}",
                payload={"qty": str(qty), "price": str(px)}, actor_type="system",
            ))
            self.store.append_event(make_event(
                "fee.charged", aggregate_type="portfolio", aggregate_id=portfolio_id,
                payload={"fee": str(fee), "order_id": order.id}, actor_type="system",
            ))
        else:
            old_q = D(pos["quantity"])
            if old_q < qty:
                return
            proceeds = qty * px - fee
            pnl = (px - D(pos["avg_price"])) * qty - fee
            pos["realized_pnl"] = str(D(pos.get("realized_pnl", 0)) + pnl)
            p["realized_pnl"] = str(D(p.get("realized_pnl", 0)) + pnl)
            p["cash"] = str(D(p["cash"]) + proceeds)
            p["fees_paid"] = str(D(p.get("fees_paid", 0)) + fee)
            pos["quantity"] = str(old_q - qty)
            hist = list(pos.get("history") or [])
            hist.append({"event": "sell", "qty": str(qty), "price": str(px), "pnl": str(pnl)})
            pos["history"] = hist
            self.store.append_event(make_event(
                "position.closed" if D(pos["quantity"]) == 0 else "position.partially_closed",
                aggregate_type="position", aggregate_id=f"{portfolio_id}:{sym}",
                payload={"qty": str(qty), "pnl": str(pnl)}, actor_type="system",
            ))
        self.store.save_portfolio(p, expected_version=p.get("version"))
        self.store.save_position(portfolio_id, pos)
        self.store.append_trade_ledger(portfolio_id, {
            "ts": time.time(), "order_id": order.id, "symbol": sym, "side": side,
            "qty": str(qty), "price": str(px), "fee": str(fee),
            "strategy_slug": order.strategy_slug, "paper_only": True,
        })

    def process_queue_once(self) -> dict[str, Any]:
        """Restart-safe worker claim — processes one queued order metadata only (fills via process_market)."""
        claim = self.store.claim_queue(self.worker_id, lease_sec=30)
        if not claim:
            return {"claimed": False, "worker_id": self.worker_id}
        self.store.append_event(make_event(
            "worker.lease_acquired", aggregate_type="worker", aggregate_id=self.worker_id,
            payload=claim, actor_type="system",
        ))
        order = self.store.get_order(claim["order_id"])
        if not order:
            self.store.complete_queue(claim["order_id"], poison=True, error="missing_order")
            return {"claimed": True, "poison": True}
        # Order remains WORKING until market tick fills it; release lease for next claim after success path
        self.store.complete_queue(claim["order_id"], poison=False)
        return {"claimed": True, "order": order, "worker_id": self.worker_id, "paper_only": True}

    # ── reconcile / analytics / events ───────────────────────────────────────
    def reconcile(self, portfolio_id: str, *, auto_halt: bool = True) -> dict[str, Any]:
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            raise DurableGovError("NOT_FOUND", "portfolio not found")
        self.store.append_event(make_event(
            "reconciliation.started", aggregate_type="portfolio", aggregate_id=portfolio_id,
            payload={}, actor_type="system",
        ))
        from saathi.platform.tg.paper_activation.models import PaperPortfolio, PaperPosition
        pp = PaperPortfolio(
            id=portfolio_id, cash=D(p["cash"]), realized_pnl=D(p.get("realized_pnl", 0)),
            fees_paid=D(p.get("fees_paid", 0)), status=PortfolioStatus(p["status"]) if p["status"] in PortfolioStatus.__members__ else PortfolioStatus.ACTIVE,
            marks={k: D(v) for k, v in (p.get("marks") or {}).items()},
            trade_ledger=self.store.list_trade_ledger(portfolio_id),
        )
        for pos in self.store.list_positions(portfolio_id):
            lots = []
            from saathi.platform.tg.paper_activation.models import PositionLot
            for lot in pos.get("lots") or []:
                lots.append(PositionLot(
                    lot_id=lot.get("lot_id", _id("lot")),
                    quantity=D(lot.get("quantity", 0)),
                    avg_price=D(lot.get("avg_price", 0)),
                ))
            pp.positions[pos["symbol"]] = PaperPosition(
                symbol=pos["symbol"], quantity=D(pos["quantity"]), avg_price=D(pos["avg_price"]),
                realized_pnl=D(pos.get("realized_pnl", 0)), fees=D(pos.get("fees", 0)),
                lots=lots, history=list(pos.get("history") or []),
            )
        orders = self.store.list_orders(portfolio_id)
        # adapt orders for recon
        class _O:
            pass
        adapted = []
        for o in orders:
            a = _O()
            a.id = o["id"]
            a.status = type("S", (), {"value": o["status"]})()
            a.filled_qty = o["filled_qty"]
            a.quantity = o["quantity"]
            a.fills = o.get("fills") or []
            adapted.append(a)
        result = reconcile_portfolio(pp, orders=adapted, journal_count=len(self.store.list_journal(portfolio_id)))
        rid = _id("precon")
        self.store.save_reconciliation({
            "id": rid, "portfolio_id": portfolio_id, "verdict": result["verdict"],
            "findings": result.get("findings", []), "warnings": result.get("warnings", []),
        })
        if result.get("fail_closed"):
            self.store.append_event(make_event(
                "reconciliation.failed", aggregate_type="portfolio", aggregate_id=portfolio_id,
                payload=result, actor_type="system",
            ))
            if auto_halt:
                p["status"] = "HALTED"
                p["halt_reason"] = "UNRECONCILED"
                p["halt_detail"] = str(result.get("findings"))
                self.store.save_portfolio(p, expected_version=p.get("version"))
                self.store.append_event(make_event(
                    "portfolio.halted", aggregate_type="portfolio", aggregate_id=portfolio_id,
                    payload={"reason": "UNRECONCILED"}, actor_type="system",
                ))
        else:
            self.store.append_event(make_event(
                "reconciliation.passed", aggregate_type="portfolio", aggregate_id=portfolio_id,
                payload={"verdict": result["verdict"]}, actor_type="system",
            ))
        return {"reconciliation": result, "portfolio": self.get_portfolio(portfolio_id)["portfolio"], "paper_only": True}

    def analytics(self, portfolio_id: str) -> dict[str, Any]:
        p = self.store.get_portfolio(portfolio_id)
        if not p:
            raise DurableGovError("NOT_FOUND", "portfolio not found")
        from saathi.platform.tg.paper_activation.models import PaperPortfolio, PaperPosition, PortfolioSnapshot
        pp = PaperPortfolio(
            id=portfolio_id, cash=D(p["cash"]), starting_cash=D(p["starting_cash"]),
            realized_pnl=D(p.get("realized_pnl", 0)), peak_equity=D(p.get("peak_equity", p["cash"])),
            marks={k: D(v) for k, v in (p.get("marks") or {}).items()},
            trade_ledger=self.store.list_trade_ledger(portfolio_id),
        )
        for pos in self.store.list_positions(portfolio_id):
            pp.positions[pos["symbol"]] = PaperPosition(
                symbol=pos["symbol"], quantity=D(pos["quantity"]), avg_price=D(pos["avg_price"]),
                history=list(pos.get("history") or []),
            )
        # synthetic equity curve points from ledger length
        pp.snapshot("now")
        return {"analytics": compute_analytics(pp), "paper_only": True}

    def list_events(self, **kwargs: Any) -> dict[str, Any]:
        events = self.store.list_events(**kwargs)
        return {"events": [e.to_public() for e in events], "paper_only": True, "immutable": True}

    def list_orders(self, portfolio_id: str) -> dict[str, Any]:
        return {"orders": self.store.list_orders(portfolio_id), "paper_only": True}

    def list_positions(self, portfolio_id: str) -> dict[str, Any]:
        return {"positions": self.store.list_positions(portfolio_id), "paper_only": True, "funds_label": "SIMULATED"}

    def list_journal(self, portfolio_id: str) -> dict[str, Any]:
        return {"entries": self.store.list_journal(portfolio_id), "immutable": True, "paper_only": True}

    # ── kill switch ──────────────────────────────────────────────────────────
    def activate_kill_switch(
        self,
        *,
        reason: str = "operator_halt",
        activated_by: str = "operator",
        org_id: str = "",
        workspace_id: str = "",
        scope=None,
        source_identity: str = "operator",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        actor = activated_by if activated_by.startswith(("operator:", "llm:", "strategy:", "agent:")) else f"operator:{activated_by}"
        if actor.startswith(("llm:", "strategy:", "agent:")) or source_identity in ("llm", "strategy", "agent"):
            self.store.append_event(make_event(
                "operator.override_attempted", aggregate_type="kill_switch", aggregate_id="GLOBAL",
                payload={"actor": actor, "denied": True}, actor_type="llm",
            ))
            raise DurableGovError("SELF_APPROVAL_FORBIDDEN", "LLM cannot engage/release kill switch")
        _assert_human(actor)
        ks = self.store.set_kill_switch(
            scope="GLOBAL", active=True, reason=reason, activated_by=activated_by,
            org_id=org_id, workspace_id=workspace_id,
        )
        self.store.append_event(make_event(
            "kill_switch.engaged", aggregate_type="kill_switch", aggregate_id="GLOBAL",
            payload={"reason": reason}, actor_type="operator", actor_id=activated_by,
        ))
        for p in self.store.list_portfolios(org_id=org_id or ""):
            if p["status"] == "ACTIVE":
                p["status"] = "HALTED"
                p["halt_reason"] = "KILL_SWITCH"
                p["halt_detail"] = reason
                self.store.save_portfolio(p, expected_version=p.get("version"))
                self.store.append_event(make_event(
                    "portfolio.halted", aggregate_type="portfolio", aggregate_id=p["id"],
                    payload={"reason": "KILL_SWITCH"}, actor_type="system",
                ))
        return {"kill_switch": ks, "paper_only": True}

    def kill_switch_status(self, **_kwargs: Any) -> dict[str, Any]:
        return {"kill_switches": self.store.list_kill_switches(), "paper_only": True}

    # ── campaigns ────────────────────────────────────────────────────────────
    def campaign_create(
        self,
        *,
        strategy_slug: str,
        initial_cash: str = "100000",
        operator_notes: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        planned_end_date: float | None = None,
        min_trade_count: int = 0,
        qualification_fingerprint: str = "",
        dataset_fingerprint: str = "",
    ) -> dict[str, Any]:
        cid = _id("pcamp")
        c = {
            "id": cid, "org_id": org_id, "workspace_id": workspace_id,
            "strategy_slug": strategy_slug, "status": "DRAFT",
            "initial_cash": initial_cash, "operator_notes": operator_notes,
            "planned_end_date": planned_end_date or (time.time() + 30 * 86400),
            "min_trade_count": min_trade_count,
            "qualification_fingerprint": qualification_fingerprint,
            "dataset_fingerprint": dataset_fingerprint,
            "created_at": time.time(),
        }
        self.store.save_campaign(c)
        self.store.append_event(make_event(
            "campaign.created", aggregate_type="campaign", aggregate_id=cid,
            payload={"strategy_slug": strategy_slug}, actor_type="operator",
        ))
        return {"campaign": self.store.get_campaign(cid), "paper_only": True, "live_authorized": False}

    def campaign_approve(self, campaign_id: str, *, approval_id: str, operator_identity: str) -> dict[str, Any]:
        _assert_human(operator_identity)
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        a = self.store.get_approval(approval_id)
        if not a or a["status"] not in ("APPROVED", "CONSUMED"):
            # allow PENDING_APPROVAL state set
            if not a:
                raise DurableGovError("NOT_FOUND", "approval not found")
        c["status"] = "APPROVED"
        c["approval_id"] = approval_id
        self.store.save_campaign(c)
        self.store.append_event(make_event(
            "campaign.approved", aggregate_type="campaign", aggregate_id=campaign_id,
            payload={"approval_id": approval_id}, actor_type="operator", actor_id=operator_identity,
        ))
        return {"campaign": self.store.get_campaign(campaign_id), "paper_only": True}

    def campaign_start(
        self,
        campaign_id: str,
        *,
        operator_identity: str,
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> dict[str, Any]:
        _assert_human(operator_identity)
        if self.store.kill_switch_active(org_id=org_id, workspace_id=workspace_id):
            raise DurableGovError("KILL_SWITCH", "cannot start campaign")
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        if c["status"] not in ("APPROVED", "PAUSED"):
            raise DurableGovError("INVALID_STATE", f"campaign status {c['status']}")
        if not c.get("approval_id"):
            raise DurableGovError("APPROVAL_REQUIRED", "campaign needs approval")
        # activate strategy if needed
        act = self.store.get_activation(c["strategy_slug"], org_id=org_id, workspace_id=workspace_id)
        if not act or act.get("state") != PaperActivationState.PAPER_ACTIVE.value:
            act_out = self.activate_strategy(
                strategy_slug=c["strategy_slug"],
                approval_id=c["approval_id"],
                operator_identity=operator_identity,
                org_id=org_id,
                workspace_id=workspace_id,
                starting_cash=c.get("initial_cash", "100000"),
                portfolio_name=f"Campaign:{c['strategy_slug']}",
            )
            c["portfolio_id"] = act_out["portfolio"]["id"]
        else:
            c["portfolio_id"] = act.get("portfolio_id", c.get("portfolio_id", ""))
        # recon
        if c["portfolio_id"]:
            r = self.reconcile(c["portfolio_id"], auto_halt=False)
            if r["reconciliation"].get("fail_closed"):
                raise DurableGovError("UNRECONCILED", "cannot start with unreconciled portfolio")
        c["status"] = "ACTIVE"
        c["start_date"] = time.time()
        self.store.save_campaign(c)
        self.store.append_event(make_event(
            "campaign.started", aggregate_type="campaign", aggregate_id=campaign_id,
            payload={"portfolio_id": c["portfolio_id"]}, actor_type="operator", actor_id=operator_identity,
        ))
        return {"campaign": self.store.get_campaign(campaign_id), "paper_only": True, "live_authorized": False}

    def campaign_pause(self, campaign_id: str, *, reason: str = "operator") -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        c["status"] = "PAUSED"
        self.store.save_campaign(c)
        self.store.append_event(make_event(
            "campaign.paused", aggregate_type="campaign", aggregate_id=campaign_id,
            payload={"reason": reason}, actor_type="operator",
        ))
        return {"campaign": self.store.get_campaign(campaign_id), "paper_only": True}

    def campaign_complete(self, campaign_id: str, *, operator_identity: str) -> dict[str, Any]:
        _assert_human(operator_identity)
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        c["status"] = "COMPLETED"
        c["actual_end_date"] = time.time()
        c["evidence"] = {
            "completed_by": operator_identity,
            "not_live_eligible": True,
            "live_authorized": False,
        }
        self.store.save_campaign(c)
        self.store.append_event(make_event(
            "campaign.completed", aggregate_type="campaign", aggregate_id=campaign_id,
            payload={"not_live_eligible": True}, actor_type="operator", actor_id=operator_identity,
        ))
        return {
            "campaign": self.store.get_campaign(campaign_id),
            "paper_only": True,
            "live_authorized": False,
            "note": "Campaign completion does not authorize live trading.",
        }

    def list_campaigns(self, **kwargs: Any) -> dict[str, Any]:
        return {"campaigns": self.store.list_campaigns(**kwargs), "paper_only": True}

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        return {"campaign": c, "paper_only": True}

    # ── backup / recovery / reports / scheduler ──────────────────────────────
    def backup_create(self, dest_dir: str | Path) -> dict[str, Any]:
        man = create_backup(self.store, dest_dir)
        self.store.append_event(make_event(
            "backup.created", aggregate_type="store", aggregate_id="paper_gov",
            payload=man, actor_type="operator",
        ))
        return man

    def backup_verify(self, path: str | Path) -> dict[str, Any]:
        return verify_backup(path)

    def recovery_test(self, source_backup: str | Path, recovery_db: str | Path) -> dict[str, Any]:
        result = restore_isolated(source_backup, recovery_db)
        self.store.append_event(make_event(
            "state.recovered", aggregate_type="store", aggregate_id="paper_gov",
            payload={"verdict": result.get("verdict"), "isolated": True},
            actor_type="system",
        ))
        return result

    def snapshot(self, portfolio_id: str) -> dict[str, Any]:
        p = self.get_portfolio(portfolio_id)
        events = self.store.list_events(aggregate_id=portfolio_id, limit=1)
        seq = events[-1].seq if events else 0
        # also max global
        all_e = self.store.list_events(limit=1)
        # use store max
        snap = self.store.save_snapshot({
            "id": _id("psnap"),
            "portfolio_id": portfolio_id,
            "seq_upto": self.store._event_seq,
            "state": p["portfolio"],
        })
        self.store.append_event(make_event(
            "snapshot.created", aggregate_type="portfolio", aggregate_id=portfolio_id,
            payload={"snapshot_id": snap["id"], "fingerprint": snap["fingerprint"]},
            actor_type="system",
        ))
        return {"snapshot": snap, "paper_only": True}

    def replay(self, portfolio_id: str) -> dict[str, Any]:
        cash = replay_portfolio_cash(self.store, portfolio_id)
        return {"replay": cash, "paper_only": True}

    def run_scheduled_jobs(self, *, enable: bool = False) -> dict[str, Any]:
        """Local-first scheduler; disabled by default."""
        results = []
        for job_id in (
            "daily_snapshot", "daily_reconciliation", "storage_health",
            "stale_worker_check", "analytics_checkpoint",
        ):
            self.store.upsert_job(job_id, enabled=enable)
        if not enable:
            return {"enabled": False, "jobs": self.store.list_jobs(), "paper_only": True, "note": "scheduler disabled by default"}
        for job in self.store.list_jobs():
            if not job["enabled"]:
                continue
            try:
                if job["job_id"] == "storage_health":
                    h = self.store.health()
                    if h.get("status") != "HEALTHY":
                        self.store.open_incident({
                            "id": _id("inc"), "severity": "critical", "kind": "storage",
                            "message": f"store unhealthy: {h}",
                        })
                elif job["job_id"] == "daily_reconciliation":
                    for p in self.store.list_portfolios():
                        self.reconcile(p["id"], auto_halt=True)
                elif job["job_id"] == "daily_snapshot":
                    for p in self.store.list_portfolios():
                        self.snapshot(p["id"])
                self.store.mark_job_run(job["job_id"], status="OK")
                results.append({"job_id": job["job_id"], "status": "OK"})
            except Exception as e:
                self.store.mark_job_run(job["job_id"], status="ERROR", error=str(e)[:200])
                results.append({"job_id": job["job_id"], "status": "ERROR", "error": str(e)[:200]})
        return {"enabled": True, "results": results, "paper_only": True}

    def report_daily(self) -> dict[str, Any]:
        ports = self.store.list_portfolios()
        return {
            "kind": "daily_paper_operations",
            "portfolios": len(ports),
            "kill_switch": self.store.kill_switch_active(),
            "storage": self.store.health(),
            "incidents_open": len(self.store.list_incidents()),
            "campaigns_active": len(self.store.list_campaigns(status="ACTIVE")),
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": "Paper report. Historical paper results are not future results.",
        }

    def report_weekly(self) -> dict[str, Any]:
        d = self.report_daily()
        d["kind"] = "weekly_paper_performance"
        d["events"] = len(self.store.list_events(limit=10000))
        return d

    def list_incidents(self) -> dict[str, Any]:
        return {"incidents": self.store.list_incidents(), "paper_only": True}

    def status(self, *, org_id: str = "local", workspace_id: str = "local") -> dict[str, Any]:
        return {
            "posture": self.posture(),
            "portfolios": len(self.store.list_portfolios(org_id=org_id)),
            "campaigns": self.store.list_campaigns(org_id=org_id),
            "kill_switches": self.store.list_kill_switches(),
            "jobs": self.store.list_jobs(),
            "paper_only": True,
            "live_authorized": False,
        }

    def list_approvals(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "approvals": self.store.list_approvals(**kwargs),
            "paper_only": True,
            "llm_may_approve": False,
        }


_default_durable: DurablePaperGovernanceService | None = None


def default_durable_gov(db_path: str | Path | None = None) -> DurablePaperGovernanceService:
    global _default_durable
    if _default_durable is None:
        _default_durable = DurablePaperGovernanceService(db_path=db_path)
    return _default_durable


def reset_durable_gov_for_tests(db_path: str | Path | None = None) -> DurablePaperGovernanceService:
    global _default_durable
    if _default_durable is not None:
        try:
            _default_durable.store.close()
        except Exception:
            pass
    _default_durable = DurablePaperGovernanceService(db_path=db_path)
    return _default_durable
