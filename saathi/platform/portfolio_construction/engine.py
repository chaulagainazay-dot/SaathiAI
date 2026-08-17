"""PortfolioConstructionEngine — proposals only, zero execution authority."""
from __future__ import annotations

import hashlib
import json
import time as _time
from decimal import Decimal
from typing import Any, Callable

from saathi.platform.fund_ledger.money import D, q_money
from saathi.platform.portfolio_construction.construct import (
    ConstructionError,
    equal_weight_targets,
    fixed_target_weights,
    risk_budget_constrained,
    signal_proportional_targets,
)
from saathi.platform.portfolio_construction.models import (
    ConstructionMethod,
    MarkQuote,
    PortfolioProposal,
    ProposalStatus,
    RC_EXPIRED,
    RC_INSUFFICIENT_CASH,
    RC_LEDGER_UNRECONCILED,
    RC_RISK_BLOCKED,
    RC_STALE_PRICE,
    RC_STALE_PROPOSAL,
    RC_SUPERSEDED,
    UniverseMember,
    new_proposal_id,
)
from saathi.platform.portfolio_construction.policy import ConstructionPolicy, DEFAULT_POLICY
from saathi.platform.portfolio_construction.rebalance import (
    before_after_summary,
    build_trades,
    current_weights_from_ledger,
    turnover,
)
from saathi.platform.portfolio_construction.store import ProposalStore
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.models import RiskResult, TradeProposal as RiskTradeProposal
from saathi.platform.portfolio_risk_engine.metrics import project_trade


class PortfolioConstructionEngine:
    def __init__(
        self,
        *,
        policy: ConstructionPolicy | None = None,
        store: ProposalStore | None = None,
        risk_engine: PortfolioRiskEngine | None = None,
        get_ledger_state: Callable[[str], dict] | None = None,
        get_recon: Callable[[str], dict] | None = None,
    ):
        self.policy = policy or DEFAULT_POLICY
        self.store = store or ProposalStore()
        self.risk_engine = risk_engine
        self._get_state = get_ledger_state
        self._get_recon = get_recon

    def bind_ledger(
        self,
        get_ledger_state: Callable[[str], dict],
        get_recon: Callable[[str], dict] | None = None,
    ) -> "PortfolioConstructionEngine":
        self._get_state = get_ledger_state
        self._get_recon = get_recon
        return self

    def bind_risk(self, risk_engine: PortfolioRiskEngine) -> "PortfolioConstructionEngine":
        self.risk_engine = risk_engine
        return self

    # ── construction ─────────────────────────────────────────────────────
    def construct_target(
        self,
        fund_id: str,
        *,
        method: ConstructionMethod | str,
        universe: list[UniverseMember],
        marks: dict[str, MarkQuote],
        fixed_weights: dict[str, Decimal] | None = None,
        ledger_state: dict | None = None,
        recon: dict | None = None,
        evidence_refs: dict | None = None,
        source: str = "portfolio_construction",
        supersedes_proposal_id: str = "",
        ttl_seconds: float | None = None,
        now: float | None = None,
        skip_risk: bool = False,
    ) -> dict:
        """Build target + rebalance proposal. Never executes."""
        ts = now if now is not None else _time.time()
        method_e = method if isinstance(method, ConstructionMethod) else ConstructionMethod(method)
        state = ledger_state or (self._get_state(fund_id) if self._get_state else None)
        if not state:
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, ["NAV_MISSING"], ts, method_e)

        recon_st = recon
        if recon_st is None and self._get_recon:
            try:
                recon_st = self._get_recon(fund_id)
            except Exception:
                recon_st = None
        if recon_st and (recon_st.get("ok") is False or recon_st.get("portfolio_status") == "RECONCILIATION_REQUIRED"):
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, [RC_LEDGER_UNRECONCILED], ts, method_e)

        current_map, cash, nav = current_weights_from_ledger(state)
        if nav <= 0:
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, ["NAV_MISSING"], ts, method_e)

        # construct targets
        warnings: list[str] = []
        try:
            if method_e == ConstructionMethod.EQUAL_WEIGHT:
                targets, cash_w, warnings = equal_weight_targets(universe, policy=self.policy, nav=nav)
            elif method_e == ConstructionMethod.FIXED_TARGET:
                if not fixed_weights:
                    return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, ["WEIGHT_SUM_INVALID"], ts, method_e)
                targets, cash_w, warnings = fixed_target_weights(
                    {k: D(v) for k, v in fixed_weights.items()},
                    universe,
                    policy=self.policy,
                    nav=nav,
                )
            elif method_e == ConstructionMethod.SIGNAL_PROPORTIONAL:
                targets, cash_w, warnings = signal_proportional_targets(universe, policy=self.policy, nav=nav)
            elif method_e == ConstructionMethod.RISK_BUDGET_CONSTRAINED:
                # start equal then constrain
                targets, cash_w, warnings = equal_weight_targets(universe, policy=self.policy, nav=nav)
                targets, cash_w, w2 = risk_budget_constrained(targets, cash_w, policy=self.policy, nav=nav)
                warnings.extend(w2)
            else:
                return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, ["UNKNOWN_METHOD"], ts, method_e)
        except ConstructionError as e:
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, [e.code], ts, method_e, detail=e.detail)

        # fill quantities from marks
        for t in targets:
            m = marks.get(t.security_id)
            if m and m.price > 0 and not m.is_stale(ts):
                t.target_quantity = q_money(D(t.target_notional) / D(m.price))  # type: ignore
                # use qty scale properly
                from saathi.platform.fund_ledger.money import q_qty

                t.target_quantity = q_qty(D(t.target_notional) / D(m.price))

        trades, twarn, terr = build_trades(
            current=current_map,
            targets=targets,
            cash_weight=cash_w,
            nav=nav,
            marks=marks,
            policy=self.policy,
            now=ts,
        )
        warnings.extend(twarn)
        if terr:
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, list(dict.fromkeys(terr)), ts, method_e)

        # cash check for net buys
        buy_notional = sum((D(t.notional_delta) for t in trades if t.action.value == "BUY"), Decimal("0"))
        # available cash after buffer
        min_cash = q_money(nav * D(self.policy.min_cash_buffer))
        available = cash - min_cash
        # selling frees cash
        sell_notional = sum((abs(D(t.notional_delta)) for t in trades if t.action.value == "SELL"), Decimal("0"))
        if buy_notional > available + sell_notional + D("0.01"):
            return self._fail(fund_id, ProposalStatus.DATA_INSUFFICIENT, [RC_INSUFFICIENT_CASH], ts, method_e)

        projected_cash = q_money(cash - buy_notional + sell_notional)
        projected_nav = nav  # marks constant → NAV ~ stable ignoring fees
        t_over = turnover(trades, nav)

        snap_ref = self._snapshot_ref(state)
        price_ref = self._price_ref(marks)

        # risk on each material trade projected sequentially for summary, then aggregate
        current_risk = None
        projected_risk: dict = {}
        if self.risk_engine and not skip_risk:
            try:
                current_risk = self.risk_engine.evaluate_current_state(
                    fund_id, ledger_state=state, recon=recon_st, now=ts, record_history=False
                ).to_public()
            except Exception as e:
                warnings.append(f"current_risk_unavailable:{e}")

            # evaluate worst-case: each BUY/SELL material trade
            blocked = False
            risk_codes: list[str] = []
            last_risk = None
            sim_state = dict(state)
            for tr in trades:
                if tr.action.value not in ("BUY", "SELL") or D(tr.estimated_quantity) <= 0:
                    continue
                prop = RiskTradeProposal(
                    symbol=tr.symbol,
                    side=tr.action.value,
                    quantity=D(tr.estimated_quantity),
                    price=D(tr.reference_price),
                    security_id=tr.security_id,
                )
                rd = self.risk_engine.evaluate_proposed_trade(
                    fund_id, prop, ledger_state=sim_state, recon=recon_st, now=ts
                )
                last_risk = rd.to_public()
                if rd.result == RiskResult.BLOCK:
                    blocked = True
                    risk_codes.extend(rd.reason_codes)
                # advance sim state for sequential projection
                proj = project_trade(
                    sim_state,
                    side=tr.action.value,
                    symbol=tr.symbol,
                    quantity=D(tr.estimated_quantity),
                    price=D(tr.reference_price),
                )
                if proj.get("ok"):
                    sim_state = proj["projected_state"]
                    projected_cash = D(proj["projected_cash"])
                    projected_nav = D(proj["projected_nav"])

            if last_risk:
                projected_risk = last_risk
            if blocked:
                status = ProposalStatus.RISK_BLOCKED
                reason_codes = list(dict.fromkeys([RC_RISK_BLOCKED] + risk_codes + warnings))
            else:
                # any WARN?
                if last_risk and last_risk.get("result") == "WARN":
                    status = ProposalStatus.RISK_WARN
                else:
                    status = ProposalStatus.READY_FOR_APPROVAL
                # only READY_FOR_APPROVAL if not blocked; WARN can still go to approval with warnings
                if status == ProposalStatus.RISK_WARN:
                    # architecture: still allow inspection + approval-ready with warnings
                    status = ProposalStatus.READY_FOR_APPROVAL
                    warnings.append("RISK_WARN")
                reason_codes = list(dict.fromkeys(warnings + (last_risk or {}).get("reason_codes", [])))
        else:
            status = ProposalStatus.READY_FOR_RISK if not skip_risk else ProposalStatus.READY_FOR_APPROVAL
            reason_codes = list(warnings)

        # material trades empty → still a valid proposal
        material = [t for t in trades if t.action.value in ("BUY", "SELL")]
        if not material and status == ProposalStatus.READY_FOR_APPROVAL:
            warnings.append("NO_MATERIAL_TRADES")

        cur_s, prop_s, delta_s = before_after_summary(
            current_state=state,
            projected_cash=projected_cash,
            projected_nav=projected_nav,
            targets=targets,
            cash_weight=cash_w,
            current_risk=current_risk,
            projected_risk=projected_risk,
        )

        ttl = ttl_seconds if ttl_seconds is not None else self.policy.default_ttl_seconds
        proposal = PortfolioProposal(
            proposal_id=new_proposal_id(),
            fund_id=fund_id,
            created_at=ts,
            method=method_e,
            status=status,
            portfolio_snapshot_ref=snap_ref,
            risk_budget_version=(
                (self.risk_engine.budget.version if self.risk_engine else "unknown")
            ),
            source=source,
            cash_weight=cash_w,
            target_allocations=targets,
            trades=trades,
            projected_cash=projected_cash,
            projected_nav=projected_nav,
            projected_exposure={
                "gross": prop_s.get("gross_exposure"),
                "net": prop_s.get("net_exposure"),
            },
            projected_risk=projected_risk,
            current_summary=cur_s,
            proposed_summary=prop_s,
            delta_summary=delta_s,
            turnover=t_over,
            warnings=list(dict.fromkeys(warnings)),
            reason_codes=list(dict.fromkeys(reason_codes)),
            evidence_refs=dict(evidence_refs or {}),
            market_price_snapshot_ref=price_ref,
            valid_until=ts + ttl,
            supersedes_proposal_id=supersedes_proposal_id,
        )

        if supersedes_proposal_id:
            old = self.store.get(supersedes_proposal_id)
            if old:
                self.store.transition(supersedes_proposal_id, old["status"], ProposalStatus.SUPERSEDED.value, RC_SUPERSEDED)
                proposal.reason_codes.append(RC_SUPERSEDED)

        pub = proposal.to_public()
        self.store.save(pub)
        self.store.transition(proposal.proposal_id, ProposalStatus.DRAFT.value, status.value, "construct")
        return pub

    def build_rebalance_proposal(self, *args, **kwargs) -> dict:
        """Alias: construct_target with equal_weight default method if omitted."""
        kwargs.setdefault("method", ConstructionMethod.EQUAL_WEIGHT)
        return self.construct_target(*args, **kwargs)

    def validate_proposal(self, proposal_id: str, *, fund_id: str | None = None, now: float | None = None) -> dict:
        """Check expiry/staleness against current ledger snapshot."""
        ts = now if now is not None else _time.time()
        pub = self.store.get(proposal_id)
        if not pub:
            return {"ok": False, "status": "NOT_FOUND"}
        if pub.get("expires_at") and ts > float(pub["expires_at"]):
            self.store.transition(proposal_id, pub["status"], ProposalStatus.EXPIRED.value, RC_EXPIRED)
            pub["status"] = ProposalStatus.EXPIRED.value
            return {"ok": False, "status": ProposalStatus.EXPIRED.value, "reason_codes": [RC_EXPIRED], "proposal": pub}

        fid = fund_id or pub["fund_id"]
        if self._get_state:
            state = self._get_state(fid)
            cur_ref = self._snapshot_ref(state)
            if cur_ref != pub.get("portfolio_snapshot_ref"):
                # material change in portfolio books
                self.store.transition(proposal_id, pub["status"], ProposalStatus.STALE_PROPOSAL.value, RC_STALE_PROPOSAL)
                pub["status"] = ProposalStatus.STALE_PROPOSAL.value
                return {
                    "ok": False,
                    "status": ProposalStatus.STALE_PROPOSAL.value,
                    "reason_codes": [RC_STALE_PROPOSAL],
                    "proposal": pub,
                }
        return {"ok": True, "status": pub["status"], "proposal": pub}

    def get_proposal(self, proposal_id: str) -> dict | None:
        return self.store.get(proposal_id)

    def list_proposals(self, fund_id: str) -> list[dict]:
        return self.store.list_for_fund(fund_id)

    def command_proposal_contract(self, proposal_id: str) -> dict:
        pub = self.store.get(proposal_id)
        if not pub:
            return {"portfolio_proposal": None}
        # rebuild thin wrapper
        return {
            "portfolio_proposal": {
                "id": pub["id"],
                "status": pub["status"],
                "created_at": pub["created_at"],
                "expires_at": pub.get("expires_at"),
                "source": pub.get("source"),
                "method": pub.get("method"),
                "current": pub.get("current"),
                "proposed": pub.get("proposed"),
                "delta": pub.get("delta"),
                "trades": pub.get("trades"),
                "projected_risk": pub.get("projected_risk"),
                "warnings": pub.get("warnings"),
                "reason_codes": pub.get("reason_codes"),
                "evidence_refs": pub.get("evidence_refs"),
                "approval_status": None,
                "authorizes_execution": False,
                "mode": "PAPER",
            }
        }

    def approval_handoff_payload(self, proposal_id: str) -> dict:
        pub = self.store.get(proposal_id)
        if not pub:
            return {"ok": False, "error": "not_found"}
        if pub["status"] not in (
            ProposalStatus.READY_FOR_APPROVAL.value,
            ProposalStatus.RISK_WARN.value,
        ):
            # RISK_WARN may have been elevated to READY_FOR_APPROVAL
            if pub["status"] != ProposalStatus.READY_FOR_APPROVAL.value:
                return {"ok": False, "error": "not_ready_for_approval", "status": pub["status"]}
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "summary": {
                "method": pub.get("method"),
                "turnover": pub.get("turnover"),
                "trade_count": len([t for t in pub.get("trades") or [] if t.get("action") in ("BUY", "SELL")]),
            },
            "proposed_trades": [t for t in pub.get("trades") or [] if t.get("action") in ("BUY", "SELL")],
            "current_vs_proposed": {"current": pub.get("current"), "proposed": pub.get("proposed"), "delta": pub.get("delta")},
            "risk_result": pub.get("projected_risk"),
            "warnings": pub.get("warnings"),
            "expiry": pub.get("expires_at"),
            "evidence_references": pub.get("evidence_refs"),
            "authorizes_execution": False,
            "mode": "PAPER",
        }

    def attention_hints(self, fund_id: str) -> list[dict]:
        """Read-only attention seeds for UI (no UI redesign)."""
        items = []
        for p in self.store.list_for_fund(fund_id, limit=20):
            st = p.get("status")
            if st in (
                ProposalStatus.READY_FOR_APPROVAL.value,
                ProposalStatus.RISK_BLOCKED.value,
                ProposalStatus.STALE_PROPOSAL.value,
                ProposalStatus.EXPIRED.value,
                ProposalStatus.DATA_INSUFFICIENT.value,
            ):
                items.append(
                    {
                        "kind": f"proposal_{st.lower()}",
                        "proposal_id": p["proposal_id"],
                        "title": f"Portfolio proposal {st}",
                        "severity": "high" if st in (ProposalStatus.READY_FOR_APPROVAL.value, ProposalStatus.RISK_BLOCKED.value) else "medium",
                    }
                )
        return items

    def _snapshot_ref(self, state: dict) -> str:
        raw = json.dumps(
            {
                "nav": state.get("nav"),
                "cash": state.get("cash"),
                "positions": [
                    {"id": p.get("security_id"), "q": p.get("quantity"), "mv": p.get("market_value")}
                    for p in (state.get("positions") or [])
                ],
                "event_count": state.get("event_count"),
            },
            sort_keys=True,
        )
        return "psnap_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _price_ref(self, marks: dict[str, MarkQuote]) -> str:
        raw = json.dumps({k: m.to_public() for k, m in sorted(marks.items())}, sort_keys=True)
        return "pxsnap_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _fail(
        self,
        fund_id: str,
        status: ProposalStatus,
        codes: list[str],
        ts: float,
        method: ConstructionMethod,
        detail: str = "",
    ) -> dict:
        prop = PortfolioProposal(
            proposal_id=new_proposal_id(),
            fund_id=fund_id,
            created_at=ts,
            method=method,
            status=status,
            portfolio_snapshot_ref="",
            risk_budget_version=self.risk_engine.budget.version if self.risk_engine else "unknown",
            warnings=[detail] if detail else [],
            reason_codes=codes,
            valid_until=ts + self.policy.default_ttl_seconds,
        )
        pub = prop.to_public()
        self.store.save(pub)
        return pub
