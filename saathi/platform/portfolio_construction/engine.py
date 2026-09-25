"""PortfolioConstructionEngine — proposals only, zero execution authority."""
from __future__ import annotations

import hashlib
import json
import time as _time
from datetime import datetime
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
    CandidatePortfolio,
    CandidatePortfolioStatus,
    ConstructionMethod,
    ConstructionReasonCode,
    ConstraintEffect,
    InstrumentAllocation,
    MarkQuote,
    PortfolioConstructionRequest,
    PortfolioProposal,
    ProposalStatus,
    RC_EXPIRED,
    RC_INSUFFICIENT_CASH,
    RC_LEDGER_UNRECONCILED,
    RC_RISK_BLOCKED,
    RC_STALE_PRICE,
    RC_STALE_PROPOSAL,
    RC_SUPERSEDED,
    RejectedIntent,
    StrategyQualificationStatus,
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

    # ── V2 canonical intent construction ────────────────────────────────
    def construct_from_intents(self, request: PortfolioConstructionRequest) -> CandidatePortfolio:
        """Translate proposal-only strategy intents into a candidate portfolio.

        This pure path neither reads nor writes the ledger, proposal store,
        approvals, Guardian state, OMS, or ExecutionGateway.  Strategy strength,
        research confidence, and historical return are deliberately absent from
        the request contract and therefore cannot become position size.
        """
        if request.construction_policy_version != self.policy.version:
            raise ValueError(
                f"construction policy mismatch: {request.construction_policy_version} != {self.policy.version}"
            )

        snapshot = request.portfolio_snapshot
        current = {
            p.instrument_id: D(p.market_value) / D(snapshot.nav)
            for p in snapshot.positions
        }
        positions = {p.instrument_id: p for p in snapshot.positions}
        metadata = {m.instrument_id: m for m in request.instrument_metadata}
        qualifications = {q.intent_id: q for q in request.qualifications}
        target = dict(current)
        effects: list[ConstraintEffect] = []
        rejected: list[RejectedIntent] = []
        reasons: list[ConstructionReasonCode] = []
        allocation_reasons: dict[str, list[ConstructionReasonCode]] = {
            instrument_id: [] for instrument_id in current
        }
        provenance: dict[str, tuple[set[str], set[str]]] = {}

        def add_reason(instrument_id: str, reason: ConstructionReasonCode) -> None:
            if reason not in reasons:
                reasons.append(reason)
            rows = allocation_reasons.setdefault(instrument_id, [])
            if reason not in rows:
                rows.append(reason)

        def constrain(
            instrument_id: str,
            before: Decimal,
            after: Decimal,
            reason: ConstructionReasonCode,
            detail: str = "",
        ) -> Decimal:
            after = max(Decimal("0"), D(after))
            if after != before:
                effects.append(
                    ConstraintEffect(
                        instrument_id,
                        reason,
                        before,
                        after,
                        self.policy.version,
                        detail,
                    )
                )
            add_reason(instrument_id, reason)
            return after

        globally_usable = (
            request.market_data_quality == "VALID"
            and request.market_data_mode in {"HISTORICAL", "REPLAY", "LIVE"}
            and snapshot.source_authority == "CANONICAL_FUND_LEDGER"
            and snapshot.reconciliation_status == "HEALTHY"
        )
        if not globally_usable:
            global_reason = (
                ConstructionReasonCode.RECONCILIATION_REQUIRED
                if snapshot.reconciliation_status != "HEALTHY"
                else ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT
            )
            for intent in request.intents:
                rejected.append(RejectedIntent(intent.intent_id, intent.instrument_id, global_reason))
                add_reason(intent.instrument_id, global_reason)

        eligible_by_instrument: dict[str, list[tuple[Any, Any]]] = {}
        if globally_usable:
            for intent in request.intents:
                reason: ConstructionReasonCode | None = None
                qualification = qualifications.get(intent.intent_id)
                meta = metadata.get(intent.instrument_id)
                if request.decision_time > intent.valid_until:
                    reason = ConstructionReasonCode.EXPIRED_INTENT
                elif intent.quality != "VALID":
                    reason = ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT
                elif intent.data_mode not in {"HISTORICAL", "REPLAY", "LIVE"}:
                    reason = ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT
                elif intent.generated_at is None or intent.generated_at > request.decision_time:
                    reason = ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT
                elif qualification is None or qualification.status is not StrategyQualificationStatus.PAPER_CANDIDATE:
                    reason = ConstructionReasonCode.STRATEGY_NOT_ELIGIBLE
                elif not qualification.quality.startswith("CERTIFIED"):
                    reason = ConstructionReasonCode.STRATEGY_NOT_ELIGIBLE
                elif qualification.instrument_id != intent.instrument_id or qualification.signal_ref not in intent.signal_refs:
                    reason = ConstructionReasonCode.STRATEGY_NOT_ELIGIBLE
                elif meta is None:
                    reason = ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT
                elif not meta.enabled:
                    reason = ConstructionReasonCode.INSTRUMENT_DISABLED
                elif not meta.venue_enabled:
                    reason = ConstructionReasonCode.VENUE_DISABLED
                elif meta.quote_currency != snapshot.reporting_currency:
                    reason = ConstructionReasonCode.CURRENCY_MISMATCH
                elif meta.market_type != "SPOT" or meta.asset_class not in {meta.asset_class.CRYPTO, meta.asset_class.EQUITY}:
                    reason = ConstructionReasonCode.UNSUPPORTED_MARKET
                elif meta.asset_class == meta.asset_class.EQUITY and self.policy.max_nepse_exposure <= 0:
                    reason = ConstructionReasonCode.NEPSE_SLEEVE_DISABLED
                if reason is not None:
                    rejected.append(RejectedIntent(intent.intent_id, intent.instrument_id, reason))
                    add_reason(intent.instrument_id, reason)
                    continue
                eligible_by_instrument.setdefault(intent.instrument_id, []).append((intent, qualification))

        # Existing positions participate in correlation/concentration even when
        # they have no fresh eligible intent. New candidates are deterministic
        # in canonical instrument order.
        for instrument_id in sorted(eligible_by_instrument):
            pairs = eligible_by_instrument[instrument_id]
            intents = [p[0] for p in pairs]
            quals = [p[1] for p in pairs]
            meta = metadata[instrument_id]
            current_weight = current.get(instrument_id, Decimal("0"))
            provenance[instrument_id] = (
                {q.strategy_id for q in quals},
                {i.intent_id for i in intents},
            )
            directions = {i.direction.value for i in intents}
            has_long = "LONG_BIAS" in directions
            has_reduce = bool(directions & {"REDUCE_BIAS", "EXIT_BIAS"})

            if has_long and has_reduce:
                target[instrument_id] = current_weight
                add_reason(instrument_id, ConstructionReasonCode.CONFLICTING_INTENTS)
                continue
            if not has_long:
                if has_reduce:
                    target[instrument_id] = Decimal("0")
                continue

            desired = D(self.policy.base_candidate_weight)
            if current_weight >= self.policy.max_position_weight:
                target[instrument_id] = current_weight
                add_reason(instrument_id, ConstructionReasonCode.CURRENT_POSITION_AT_CAP)
                continue

            if desired > self.policy.max_position_weight:
                desired = constrain(
                    instrument_id,
                    desired,
                    self.policy.max_position_weight,
                    ConstructionReasonCode.POSITION_CAP,
                )

            # PIT-safe realized volatility. Unknown volatility is not assumed to
            # be zero; it produces no new risk.
            visible, future_count = self._visible_history(request, instrument_id)
            if future_count:
                add_reason(instrument_id, ConstructionReasonCode.FUTURE_DATA_EXCLUDED)
            volatility = self._annualized_volatility(visible, meta.asset_class.value)
            if volatility is None:
                desired = constrain(
                    instrument_id,
                    desired,
                    Decimal("0"),
                    ConstructionReasonCode.VOLATILITY_DATA_INSUFFICIENT,
                )
            elif volatility > self.policy.volatility_target:
                scaled = desired * self.policy.volatility_target / volatility
                desired = constrain(
                    instrument_id,
                    desired,
                    scaled,
                    ConstructionReasonCode.VOLATILITY_REDUCTION,
                    f"annualized_volatility={volatility}",
                )

            factor = self._drawdown_factor(snapshot.current_drawdown)
            if factor < 1:
                desired = constrain(
                    instrument_id,
                    desired,
                    desired * factor,
                    ConstructionReasonCode.DRAWDOWN_REDUCTION,
                    f"drawdown={snapshot.current_drawdown}",
                )

            if meta.liquidity_limit_weight is None:
                desired = constrain(
                    instrument_id,
                    desired,
                    min(desired, self.policy.missing_liquidity_cap),
                    ConstructionReasonCode.LIQUIDITY_DATA_INSUFFICIENT,
                )
            elif desired > meta.liquidity_limit_weight:
                desired = constrain(
                    instrument_id,
                    desired,
                    meta.liquidity_limit_weight,
                    ConstructionReasonCode.LIQUIDITY_LIMIT,
                )

            sleeve_cap = (
                self.policy.max_crypto_exposure
                if meta.asset_class.value == "CRYPTO"
                else self.policy.max_nepse_exposure
            )
            other_sleeve = sum(
                weight
                for other_id, weight in target.items()
                if other_id != instrument_id
                and (metadata.get(other_id).asset_class if metadata.get(other_id) else positions[other_id].asset_class)
                == meta.asset_class
            )
            sleeve_room = max(Decimal("0"), sleeve_cap - other_sleeve)
            if desired > sleeve_room:
                desired = constrain(
                    instrument_id,
                    desired,
                    sleeve_room,
                    ConstructionReasonCode.CRYPTO_SLEEVE_CAP
                    if meta.asset_class.value == "CRYPTO"
                    else ConstructionReasonCode.NEPSE_SLEEVE_DISABLED,
                )

            # Treat unknown correlation conservatively. The cap is a robust
            # cluster bound, not a covariance optimizer.
            for other_id, other_weight in sorted(target.items()):
                if other_id == instrument_id or other_weight <= 0:
                    continue
                other_meta = metadata.get(other_id)
                other_class = other_meta.asset_class if other_meta else positions[other_id].asset_class
                if other_class != meta.asset_class:
                    continue
                correlation = self._pairwise_correlation(request, instrument_id, other_id)
                if correlation is None:
                    desired = constrain(
                        instrument_id,
                        desired,
                        min(desired, max(Decimal("0"), self.policy.correlated_cluster_cap - other_weight)),
                        ConstructionReasonCode.CORRELATION_DATA_INSUFFICIENT,
                        f"pair={other_id}",
                    )
                elif abs(correlation) >= self.policy.high_correlation_threshold:
                    desired = constrain(
                        instrument_id,
                        desired,
                        min(desired, max(Decimal("0"), self.policy.correlated_cluster_cap - other_weight)),
                        ConstructionReasonCode.CORRELATION_CONCENTRATION,
                        f"pair={other_id};correlation={correlation}",
                    )

            desired = max(current_weight, desired)

            # Use authoritative available cash. Reserved/unsettled amounts are
            # never silently assumed deployable.
            cash_room = max(
                Decimal("0"),
                D(snapshot.available_cash) / D(snapshot.nav) - D(self.policy.min_cash_buffer),
            )
            new_weight = max(Decimal("0"), desired - current_weight)
            if new_weight > cash_room:
                desired = constrain(
                    instrument_id,
                    desired,
                    current_weight + cash_room,
                    ConstructionReasonCode.CASH_FLOOR,
                )

            delta = abs(desired - current_weight)
            minimum_delta = max(
                D(self.policy.min_weight_delta),
                D(self.policy.min_trade_notional) / D(snapshot.nav),
            )
            if Decimal("0") < delta < minimum_delta:
                desired = constrain(
                    instrument_id,
                    desired,
                    current_weight,
                    ConstructionReasonCode.COST_INEFFICIENT_REBALANCE,
                )
            target[instrument_id] = desired

        allocations: list[InstrumentAllocation] = []
        for instrument_id in sorted(set(target) | set(current)):
            meta = metadata.get(instrument_id)
            position = positions.get(instrument_id)
            if meta is None and position is None:
                continue
            current_weight = current.get(instrument_id, Decimal("0"))
            target_weight = max(Decimal("0"), target.get(instrument_id, current_weight))
            chosen_asset_class = meta.asset_class if meta else position.asset_class
            chosen_symbol = meta.symbol if meta else position.symbol
            chosen_currency = meta.quote_currency if meta else position.quote_currency
            cost_bps = meta.estimated_round_trip_cost_bps if meta else Decimal("0")
            estimated_cost = abs(target_weight - current_weight) * snapshot.nav * cost_bps / Decimal("10000")
            prov = provenance.get(instrument_id, (set(), set()))
            allocations.append(
                InstrumentAllocation(
                    instrument_id=instrument_id,
                    symbol=chosen_symbol,
                    asset_class=chosen_asset_class,
                    quote_currency=chosen_currency,
                    current_weight=current_weight,
                    target_weight=target_weight,
                    weight_change=target_weight - current_weight,
                    target_notional=target_weight * snapshot.nav,
                    estimated_cost=estimated_cost,
                    strategy_ids=tuple(sorted(prov[0])),
                    intent_ids=tuple(sorted(prov[1])),
                    reason_codes=tuple(allocation_reasons.get(instrument_id, ())),
                )
            )

        total_target = sum((a.target_weight for a in allocations), Decimal("0"))
        cash_target = max(D(self.policy.min_cash_buffer), Decimal("1") - total_target)
        cash_current = D(snapshot.cash) / D(snapshot.nav)
        turnover_value = sum((abs(a.weight_change) for a in allocations), Decimal("0"))
        estimated_cost = sum((a.estimated_cost for a in allocations), Decimal("0"))
        eligible_qualifications = tuple(
            sorted(
                (q for pairs in eligible_by_instrument.values() for _intent, q in pairs),
                key=lambda q: (q.intent_id, q.strategy_id),
            )
        )
        eligible_long = any(
            any(i.direction.value == "LONG_BIAS" for i, _q in pairs)
            for pairs in eligible_by_instrument.values()
        )
        new_allocation = sum((max(Decimal("0"), a.weight_change) for a in allocations), Decimal("0"))
        reduction_codes = {
            ConstructionReasonCode.POSITION_CAP,
            ConstructionReasonCode.CRYPTO_SLEEVE_CAP,
            ConstructionReasonCode.CASH_FLOOR,
            ConstructionReasonCode.VOLATILITY_REDUCTION,
            ConstructionReasonCode.VOLATILITY_DATA_INSUFFICIENT,
            ConstructionReasonCode.DRAWDOWN_REDUCTION,
            ConstructionReasonCode.CORRELATION_CONCENTRATION,
            ConstructionReasonCode.CORRELATION_DATA_INSUFFICIENT,
            ConstructionReasonCode.LIQUIDITY_LIMIT,
            ConstructionReasonCode.LIQUIDITY_DATA_INSUFFICIENT,
        }
        if not eligible_long or (new_allocation == 0 and total_target == 0):
            status = CandidatePortfolioStatus.ZERO_ALLOCATION
        elif any(r in reduction_codes for r in reasons):
            status = CandidatePortfolioStatus.REDUCED_ALLOCATION
        else:
            status = CandidatePortfolioStatus.CANDIDATE_ALLOCATION

        identity = {
            "request_id": request.request_id,
            "allocations": [a.to_public() for a in allocations],
            "cash_target_weight": str(cash_target),
            "reason_codes": [r.value for r in reasons],
        }
        candidate_id = "pcand_" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return CandidatePortfolio(
            candidate_portfolio_id=candidate_id,
            request_id=request.request_id,
            fund_id=snapshot.fund_id,
            status=status,
            portfolio_snapshot_ref=snapshot.snapshot_ref,
            market_data_snapshot_ref=request.market_data_snapshot_ref,
            construction_policy_version=request.construction_policy_version,
            risk_budget_version=request.risk_budget_version,
            decision_time=request.decision_time,
            allocations=tuple(allocations),
            cash_current_weight=cash_current,
            cash_target_weight=cash_target,
            turnover=turnover_value,
            estimated_cost=estimated_cost,
            rejected_intents=tuple(sorted(rejected, key=lambda x: x.intent_id)),
            constraint_effects=tuple(effects),
            reason_codes=tuple(reasons),
            intent_ids=tuple(sorted({q.intent_id for q in eligible_qualifications})),
            strategy_ids=tuple(sorted({q.strategy_id for q in eligible_qualifications})),
            qualification_artifact_sha256=tuple(
                sorted({q.qualification_artifact_sha256 for q in eligible_qualifications})
            ),
            dataset_versions=tuple(sorted({q.dataset_version for q in eligible_qualifications})),
            selected_config_hashes=tuple(
                sorted({q.selected_config_hash for q in eligible_qualifications})
            ),
            policy_assumption_status=self.policy.assumption_status,
            quality="VALID_WITH_LIMITATIONS" if globally_usable else "DATA_INSUFFICIENT",
            market_data_mode=request.market_data_mode,
        )

    def build_risk_handoff(
        self,
        request: PortfolioConstructionRequest,
        candidate: CandidatePortfolio,
    ) -> tuple[RiskTradeProposal, ...]:
        """Adapt candidate deltas to the existing risk engine contract only.

        The returned objects are risk-evaluation proposals. They have no
        approval or execution authority and are never submitted here.
        """
        if candidate.request_id != request.request_id:
            raise ValueError("candidate/request identity mismatch")
        proposals: list[RiskTradeProposal] = []
        for allocation in candidate.allocations:
            if allocation.weight_change == 0:
                continue
            visible, _future_count = self._visible_history(request, allocation.instrument_id)
            if not visible or visible[-1].close <= 0:
                continue
            notional = abs(allocation.weight_change) * request.portfolio_snapshot.nav
            proposals.append(
                RiskTradeProposal(
                    symbol=allocation.symbol,
                    side="BUY" if allocation.weight_change > 0 else "SELL",
                    quantity=notional / visible[-1].close,
                    price=visible[-1].close,
                    security_id=allocation.instrument_id,
                )
            )
        return tuple(proposals)

    def _visible_history(
        self,
        request: PortfolioConstructionRequest,
        instrument_id: str,
    ) -> tuple[tuple[Any, ...], int]:
        rows = request.history_for(instrument_id)
        visible = tuple(
            b
            for b in rows
            if b.available_at <= request.decision_time
            and b.quality.value == "VALID"
            and b.status not in {"SUPERSEDED", "RETRACTED"}
        )
        return visible, len(rows) - len(visible)

    def _returns(self, rows: tuple[Any, ...], lookback: int) -> tuple[Decimal, ...]:
        closes = [D(b.close) for b in rows if D(b.close) > 0]
        if len(closes) < 2:
            return ()
        returns = tuple((closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes)))
        return returns[-lookback:]

    def _annualized_volatility(self, rows: tuple[Any, ...], asset_class: str) -> Decimal | None:
        returns = self._returns(rows, self.policy.volatility_lookback_returns)
        if len(returns) < self.policy.volatility_min_observations:
            return None
        mean = sum(returns, Decimal("0")) / Decimal(len(returns))
        variance = sum(((x - mean) ** 2 for x in returns), Decimal("0")) / Decimal(len(returns) - 1)
        days = (
            self.policy.crypto_annualization_days
            if asset_class == "CRYPTO"
            else self.policy.nepse_annualization_days
        )
        return variance.sqrt() * Decimal(days).sqrt()

    def _pairwise_correlation(
        self,
        request: PortfolioConstructionRequest,
        left_id: str,
        right_id: str,
    ) -> Decimal | None:
        left_rows, _ = self._visible_history(request, left_id)
        right_rows, _ = self._visible_history(request, right_id)
        left_by_time = {b.as_of: D(b.close) for b in left_rows}
        right_by_time = {b.as_of: D(b.close) for b in right_rows}
        common = sorted(set(left_by_time) & set(right_by_time))
        if len(common) < self.policy.correlation_min_observations + 1:
            return None
        common = common[-(self.policy.correlation_lookback_returns + 1) :]
        left = tuple(left_by_time[t] for t in common)
        right = tuple(right_by_time[t] for t in common)
        lr = tuple(left[i] / left[i - 1] - 1 for i in range(1, len(left)))
        rr = tuple(right[i] / right[i - 1] - 1 for i in range(1, len(right)))
        if len(lr) < self.policy.correlation_min_observations:
            return None
        lm = sum(lr, Decimal("0")) / Decimal(len(lr))
        rm = sum(rr, Decimal("0")) / Decimal(len(rr))
        lvar = sum(((x - lm) ** 2 for x in lr), Decimal("0"))
        rvar = sum(((x - rm) ** 2 for x in rr), Decimal("0"))
        if lvar == 0 or rvar == 0:
            return None
        covariance = sum(((x - lm) * (y - rm) for x, y in zip(lr, rr)), Decimal("0"))
        return covariance / (lvar * rvar).sqrt()

    def _drawdown_factor(self, drawdown: Decimal) -> Decimal:
        value = D(drawdown)
        if value >= self.policy.severe_drawdown:
            return Decimal("0")
        if value >= self.policy.elevated_drawdown:
            return D(self.policy.elevated_drawdown_factor)
        if value >= self.policy.moderate_drawdown:
            return D(self.policy.moderate_drawdown_factor)
        return Decimal("1")

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
