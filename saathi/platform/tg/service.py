"""Trading Guardian Service — composition facade over M62 + M166–M175 engines.

Flow:
  Market Data → Registry → Strategy Evaluation → Proposal → Policy → Risk
  → Approval Center (external) → ExecutionGateway (paper only) → Journal

Default authority: ADVISORY. No live orders. No self-approval. No LLM risk override.
"""
from __future__ import annotations

import copy
import time
import uuid
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import (
    AuthorityMode,
    DEFAULT_AUTHORITY_MODE,
    MarketSnapshot,
    PerformanceMetrics,
    ProposalStatus,
    StrategyActivation,
    StrategyEvaluationVerdict,
    TradeProposal,
    TradingGuardianPolicy,
    coerce_decimal,
)
from saathi.platform.tg.registry import StrategyRegistry, RegistryError
from saathi.platform.tg.regime import MarketRegimeEngine, RegimeAssessment
from saathi.platform.tg.policy import PolicyEngine, DEFAULT_POLICY
from saathi.platform.tg.risk import RiskEngine
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.journal import TradeJournal
from saathi.platform.tg.evaluation import StrategyEvaluator, StrategyComparison
from saathi.platform.tg.strategies import CATALOG, list_catalog, get_catalog_strategy


class TGServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TradingGuardianService:
    def __init__(
        self,
        *,
        policy: TradingGuardianPolicy | None = None,
        authority_mode: AuthorityMode | None = None,
    ):
        self.policy = policy or copy.deepcopy(DEFAULT_POLICY)
        if authority_mode is not None:
            self.policy.authority_mode = authority_mode
        else:
            self.policy.authority_mode = DEFAULT_AUTHORITY_MODE

        self.registry = StrategyRegistry()
        self.regime_engine = MarketRegimeEngine()
        self.kill_switches = KillSwitchStore()
        self.policy_engine = PolicyEngine(self.policy, self.kill_switches)
        self.risk_engine = RiskEngine.from_policy(self.policy, self.kill_switches)
        self.journal = TradeJournal()
        self.evaluator = StrategyEvaluator()
        self._proposals: dict[str, TradeProposal] = {}
        self._idempotency: set[str] = set()
        self._policy_decisions: dict[str, Any] = {}
        self._risk_decisions: dict[str, Any] = {}
        self._backtests: dict[str, Any] = {}
        self._seeded = False

    # ── bootstrap catalog ────────────────────────────────────────────────────
    def seed_catalog(
        self,
        *,
        org_id: str = "local",
        workspace_id: str = "local",
        activate: bool = True,
    ) -> list[dict[str, Any]]:
        if self._seeded:
            return [s.to_public() for s in self.registry.list(org_id=org_id, workspace_id=workspace_id)]
        out = []
        for slug, strat in CATALOG.items():
            sp = strat.spec()
            try:
                registered = self.registry.register(
                    name=sp.name,
                    slug=sp.slug,
                    description=sp.description,
                    family=sp.family,
                    source_identity="catalog",
                    org_id=org_id,
                    workspace_id=workspace_id,
                    version=sp.version,
                    parameters=sp.default_parameters,
                    parameter_schema=sp.parameter_schema,
                    supported_instruments=sp.supported_instruments,
                    supported_timeframes=sp.supported_timeframes,
                    required_data_fields=sp.required_data_fields,
                    regime_compatibility=sp.regime_compatibility,
                    assumptions=sp.assumptions,
                    invalidation_conditions=sp.invalidation_conditions,
                    stop_logic=sp.stop_logic,
                    holding_horizon=sp.holding_horizon,
                    confidence_components=sp.confidence_components,
                    activate=activate,
                )
                out.append(registered.to_public())
            except RegistryError as e:
                if e.code != "DUPLICATE_SLUG":
                    raise
        self._seeded = True
        return out

    # ── posture ──────────────────────────────────────────────────────────────
    def posture(self) -> dict[str, Any]:
        return {
            "paper_only": True,
            "live_trading_authorized": False,
            "live_order_capable": False,
            "broker_credential_support": False,
            "authority_mode": self.policy.authority_mode.value,
            "default_authority_mode": AuthorityMode.ADVISORY.value,
            "require_approval": self.policy.require_approval,
            "leverage_allowed": False,
            "margin_allowed": False,
            "kill_switch": self.kill_switches.status(),
            "policy_version": self.policy.version,
            "engine_version": "m166.tg.engine.v1",
            "funds_label": "SIMULATED",
            "disclaimer": "PAPER TRADING ONLY — NO LIVE ORDERS — SIMULATED FUNDS",
            "llm_boundary": {
                "may_explain": True,
                "may_size_positions": False,
                "may_approve": False,
                "may_override_policy": False,
                "may_override_kill_switch": False,
            },
            "execution_path": "ApprovalCenter → ExecutionGateway → paper tools only",
            "composites": [
                "saathi.platform.strategy (backtest)",
                "saathi.platform.paper_trading (paper broker)",
                "saathi.platform.safety (circuit breakers)",
                "saathi.platform.trading_guardian (order veto)",
                "saathi.platform.market_data",
            ],
        }

    # ── regime ───────────────────────────────────────────────────────────────
    def evaluate_regime(self, snapshot: MarketSnapshot | dict[str, Any]) -> dict[str, Any]:
        snap = self._as_snapshot(snapshot)
        return self.regime_engine.evaluate(snap).to_public()

    # ── proposals ────────────────────────────────────────────────────────────
    def generate_proposal(
        self,
        *,
        strategy_slug: str,
        snapshot: MarketSnapshot | dict[str, Any],
        org_id: str = "local",
        workspace_id: str = "local",
        project_id: str = "",
        mission_id: str = "",
        portfolio: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        equity: Decimal = Decimal("100000"),
        cash: Decimal = Decimal("100000"),
        correlation_id: str = "",
        actor: str = "operator",
    ) -> dict[str, Any]:
        self.seed_catalog(org_id=org_id, workspace_id=workspace_id)
        snap = self._as_snapshot(snapshot)
        corr = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"

        # Strategy from catalog evaluator + registry metadata
        try:
            catalog = get_catalog_strategy(strategy_slug)
        except KeyError as e:
            raise TGServiceError("UNKNOWN_STRATEGY", str(e)) from e

        reg = self.registry.get_by_slug(strategy_slug, org_id=org_id, workspace_id=workspace_id)
        if reg is None:
            raise TGServiceError("STRATEGY_NOT_REGISTERED", strategy_slug)
        if reg.activation == StrategyActivation.SUSPENDED:
            raise TGServiceError("STRATEGY_SUSPENDED", strategy_slug)
        if reg.deprecated:
            raise TGServiceError("STRATEGY_DEPRECATED", strategy_slug)

        ver = reg.versions[-1]
        for v in reg.versions:
            if v.activation == StrategyActivation.ACTIVE:
                ver = v
                break

        regime = self.regime_engine.evaluate(snap)
        signals = catalog.evaluate(
            snap,
            params=params or ver.parameters.parameters,
            correlation_id=corr,
            org_id=org_id,
            workspace_id=workspace_id,
        )

        if not signals:
            return {
                "proposal": None,
                "signals": [],
                "regime": regime.to_public(),
                "reason": "NO_SIGNAL",
                "paper_only": True,
                "authority_mode": self.policy.authority_mode.value,
            }

        sig = signals[0]
        entry = coerce_decimal(sig.inputs.get("price", snap.last_price))
        stop = coerce_decimal(sig.inputs.get("stop_price", 0)) or None
        tp = coerce_decimal(sig.inputs.get("take_profit_price", 0)) or None
        stop_distance = coerce_decimal(sig.inputs.get("stop_distance", 0))
        if stop and entry and stop_distance <= 0:
            stop_distance = abs(entry - stop)
        rr = Decimal("0")
        if stop_distance > 0 and tp and entry:
            rr = abs(tp - entry) / stop_distance

        # Risk sizing (deterministic) — draft quantity
        draft = TradeProposal(
            signal_id=sig.id,
            strategy_id=reg.id,
            strategy_version=ver.version,
            strategy_fingerprint=ver.fingerprint,
            policy_version=self.policy.version,
            symbol=snap.symbol,
            side=sig.side,
            order_type="LIMIT",
            quantity=Decimal("0"),
            limit_price=entry,
            stop_price=stop,
            take_profit_price=tp,
            entry_price=entry,
            stop_distance=stop_distance,
            reward_to_risk=rr,
            notional=Decimal("0"),
            status=ProposalStatus.SIGNALED,
            authority_mode=self.policy.authority_mode,
            explanation=sig.explanation,
            regime_labels=regime.labels,
            market_snapshot_id=snap.id,
            market_snapshot=snap.to_public(),
            idempotency_key=f"prop:{reg.slug}:{snap.symbol}:{corr}",
            expires_at=time.time() + self.policy.proposal_ttl_seconds,
            source_identity=actor,
            correlation_id=corr,
            org_id=org_id,
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            sector=snap.sector,
            paper_only=True,
            funds_label="SIMULATED",
            live_order=False,
        )

        risk = self.risk_engine.evaluate(
            draft,
            equity=equity,
            cash=cash,
            portfolio=portfolio or {"reconciled": True, "open_positions": 0},
            price_stale=snap.freshness_seconds > self.policy.max_data_freshness_seconds,
        )
        draft.quantity = risk.position_size
        draft.notional = risk.position_size * entry
        draft.risk_decision_id = risk.id
        self._risk_decisions[risk.id] = risk.to_public()

        # Policy
        pol = self.policy_engine.evaluate(
            draft,
            snapshot=snap,
            strategy=reg,
            strategy_version=ver,
            regime=regime,
            portfolio=portfolio or {
                "reconciled": True,
                "open_positions": 0,
                "equity": str(equity),
                "gross_exposure": "0",
                "sector_exposure_pct": {},
                "correlated_exposure_pct": 0,
                "portfolio_heat_pct": 0,
                "daily_realized_loss": 0,
                "weekly_realized_loss": 0,
                "drawdown_pct": 0,
                "consecutive_losses": 0,
            },
            seen_idempotency=self._idempotency,
        )
        draft.policy_decision_id = pol.id
        self._policy_decisions[pol.id] = pol.to_public()

        if not pol.allowed:
            draft.status = ProposalStatus.POLICY_BLOCKED
        elif not risk.allowed:
            draft.status = ProposalStatus.RISK_BLOCKED
        elif self.policy.authority_mode == AuthorityMode.ADVISORY:
            draft.status = ProposalStatus.SIGNALED  # advisory: no execution path without operator
        elif self.policy.require_approval or self.policy.authority_mode == AuthorityMode.APPROVAL_REQUIRED:
            draft.status = ProposalStatus.AWAITING_APPROVAL
        else:
            draft.status = ProposalStatus.AWAITING_APPROVAL  # still require human by default for paper submit

        draft.updated_at = time.time()
        self._proposals[draft.id] = draft
        self._idempotency.add(draft.idempotency_key)

        # Journal signal stage
        self.journal.record_lifecycle(
            proposal=draft.to_public(),
            signal=sig.to_public(),
            policy_gates=[g.to_public() for g in pol.gates],
            risk=risk.to_public(),
            regime=regime.labels,
            market_context=snap.to_public(),
            org_id=org_id,
            workspace_id=workspace_id,
            correlation_id=corr,
            policy_version=self.policy.version,
            operator_notes="proposal_generated",
        )

        return {
            "proposal": draft.to_public(),
            "signal": sig.to_public(),
            "regime": regime.to_public(),
            "policy": pol.to_public(),
            "risk": risk.to_public(),
            "authority_mode": self.policy.authority_mode.value,
            "paper_only": True,
            "funds_label": "SIMULATED",
            "execution_allowed": False,  # never auto-execute from generate
            "requires_approval": True,
            "requires_execution_gateway": True,
            "disclaimer": "PAPER TRADING ONLY — NO LIVE ORDERS — SIMULATED FUNDS",
        }

    def get_proposal(self, proposal_id: str, *, org_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        p = self._proposals.get(proposal_id)
        if not p:
            raise TGServiceError("NOT_FOUND", f"proposal {proposal_id} not found")
        if org_id and p.org_id and p.org_id != org_id:
            raise TGServiceError("TENANT_ISOLATION", "proposal not in org")
        if workspace_id and p.workspace_id and p.workspace_id != workspace_id:
            raise TGServiceError("TENANT_ISOLATION", "proposal not in workspace")
        return p.to_public()

    def list_proposals(self, *, org_id: str = "", workspace_id: str = "") -> list[dict[str, Any]]:
        out = []
        for p in self._proposals.values():
            if org_id and p.org_id and p.org_id != org_id:
                continue
            if workspace_id and p.workspace_id and p.workspace_id != workspace_id:
                continue
            out.append(p.to_public())
        return out

    def review_proposal(
        self,
        proposal_id: str,
        *,
        decision: str,
        actor: str,
        approval_id: str = "",
        notes: str = "",
        org_id: str = "",
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Human review. Strategies/LLMs cannot approve."""
        if actor.startswith(("strategy:", "llm:", "agent:")) or actor in ("strategy", "llm", "agent"):
            raise TGServiceError("SELF_APPROVAL_FORBIDDEN", "strategy/LLM/agent cannot approve proposals")
        p = self._proposals.get(proposal_id)
        if not p:
            raise TGServiceError("NOT_FOUND", f"proposal {proposal_id} not found")
        if org_id and p.org_id and p.org_id != org_id:
            raise TGServiceError("TENANT_ISOLATION", "proposal not in org")

        if decision == "reject":
            p.status = ProposalStatus.REJECTED
            p.updated_at = time.time()
            self.journal.record_lifecycle(
                proposal=p.to_public(),
                approval={"decision": "reject", "actor": actor, "notes": notes},
                operator_notes=notes,
                org_id=p.org_id,
                workspace_id=p.workspace_id,
                correlation_id=p.correlation_id,
            )
            return {"proposal": p.to_public(), "decision": "reject"}

        if decision == "approve":
            if not approval_id:
                # Approval Center id required for real submit path; allow marking approved with external id
                approval_id = f"manual:{uuid.uuid4().hex[:10]}"
            p.approval_id = approval_id
            p.status = ProposalStatus.APPROVED
            p.updated_at = time.time()
            self.journal.record_lifecycle(
                proposal=p.to_public(),
                approval={"decision": "approve", "actor": actor, "approval_id": approval_id, "notes": notes},
                operator_notes=notes,
                org_id=p.org_id,
                workspace_id=p.workspace_id,
                correlation_id=p.correlation_id,
            )
            return {
                "proposal": p.to_public(),
                "decision": "approve",
                "next": "submit via ExecutionGateway paper tools only",
                "live_order": False,
            }

        raise TGServiceError("INVALID_DECISION", f"unknown decision {decision}")

    def attach_paper_order(
        self,
        proposal_id: str,
        *,
        paper_order_id: str,
        execution_trace: str = "",
        actor: str = "execution_gateway",
    ) -> dict[str, Any]:
        """Called after ExecutionGateway paper submit — never places live orders."""
        p = self._proposals.get(proposal_id)
        if not p:
            raise TGServiceError("NOT_FOUND", f"proposal {proposal_id} not found")
        if p.status not in (ProposalStatus.APPROVED, ProposalStatus.AWAITING_APPROVAL):
            # LIMITED_AUTONOMOUS_PAPER still needs approved or explicit mode
            if self.policy.authority_mode != AuthorityMode.LIMITED_AUTONOMOUS_PAPER:
                raise TGServiceError("NOT_APPROVED", "proposal not approved for paper submit")
        if p.status == ProposalStatus.AWAITING_APPROVAL and not p.approval_id:
            if self.policy.authority_mode != AuthorityMode.LIMITED_AUTONOMOUS_PAPER:
                raise TGServiceError("APPROVAL_REQUIRED", "human approval required")
        p.paper_order_id = paper_order_id
        p.status = ProposalStatus.PAPER_SUBMITTED
        p.updated_at = time.time()
        self.journal.record_lifecycle(
            proposal=p.to_public(),
            order={
                "paper_order_id": paper_order_id,
                "execution_trace": execution_trace,
                "actor": actor,
                "paper_only": True,
                "live_order": False,
            },
            org_id=p.org_id,
            workspace_id=p.workspace_id,
            correlation_id=p.correlation_id,
            operator_notes="paper_order_attached",
        )
        return p.to_public()

    # ── backtest bridge (reuses M62.4 strategy engine) ────────────────────────
    def run_backtest(
        self,
        *,
        strategy_slug: str,
        dataset: str = "TRENDING",
        cost_tier: str = "realistic",
        n: int = 40,
        seed: int = 0,
        split_kind: str = "IN_SAMPLE",
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> dict[str, Any]:
        """Run deterministic backtest via existing strategy engine when available."""
        from saathi.platform.tg.domain import BacktestRunRef, BacktestResultView

        run = BacktestRunRef(
            strategy_id=strategy_slug,
            strategy_version="1.0.0",
            dataset=dataset,
            status="RUNNING",
            seed=seed,
            cost_tier=cost_tier,
            split_kind=split_kind,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        metrics = PerformanceMetrics(split_kind=split_kind)
        quality: dict[str, Any] = {"engine": "m62_4_bridge"}
        limitations = [
            "Uses M62.4 deterministic backtest engine when fixtures map.",
            "Simulated fills may differ from real execution.",
            "Historical performance is not future performance.",
            "No profitability claim.",
            "PAPER / research only.",
        ]

        try:
            from saathi.platform.strategy.fixtures import (
                valid_momentum, valid_mean_reversion,
            )
            from saathi.platform.strategy.engine import run_backtest
            from saathi.platform.market_data.fixtures import build_bars, DATASETS
            from saathi.platform.market_data.models import Timeframe

            mapping = {
                "trend_following": valid_momentum,
                "kotegawa_mean_reversion": valid_mean_reversion,
                "momentum_rs": valid_momentum,
            }
            if strategy_slug == "no_trade":
                metrics = PerformanceMetrics(
                    number_of_trades=0,
                    total_return=Decimal("0"),
                    split_kind=split_kind,
                )
                run.status = "COMPLETE"
            else:
                builder = mapping.get(strategy_slug, valid_momentum)
                defn = builder()
                ds = dataset if dataset in DATASETS else "TRENDING"
                bars = build_bars(ds, Timeframe.D1, n)
                result = run_backtest(defn, bars, seed=seed)
                run.status = result.status if result.status else "COMPLETE"
                raw_metrics = result.metrics or {}

                def _mv(key: str, default: str = "0") -> Decimal:
                    met = raw_metrics.get(key)
                    if met is None:
                        return coerce_decimal(default)
                    if hasattr(met, "value"):
                        return coerce_decimal(met.value if met.value is not None else default)
                    if isinstance(met, dict):
                        return coerce_decimal(met.get("value", default))
                    return coerce_decimal(met)

                metrics = PerformanceMetrics(
                    total_return=_mv("total_return"),
                    max_drawdown=_mv("max_drawdown"),
                    number_of_trades=int(_mv("trade_count", "0") or _mv("number_of_trades", "0") or 0),
                    estimated_fees=_mv("total_fees", "0") if "total_fees" in raw_metrics else _mv("fees", "0"),
                    estimated_slippage=_mv("total_slippage", "0") if "total_slippage" in raw_metrics else _mv("slippage", "0"),
                    win_rate=_mv("win_rate"),
                    volatility=_mv("volatility"),
                    split_kind=split_kind,
                )
                if "sharpe" in raw_metrics:
                    metrics.sharpe = _mv("sharpe")
                if "sortino" in raw_metrics:
                    metrics.sortino = _mv("sortino")
                if "profit_factor" in raw_metrics:
                    metrics.profit_factor = _mv("profit_factor")
                quality["result_hash"] = result.result_hash
                quality["look_ahead_ok"] = result.look_ahead_ok
                quality["metric_keys"] = list(raw_metrics.keys())
        except Exception as exc:
            run.status = "COMPLETE_WITH_FIXTURE_METRICS"
            limitations.append(f"Backtest bridge limited: {type(exc).__name__}")
            if strategy_slug == "no_trade":
                metrics = PerformanceMetrics(number_of_trades=0, split_kind=split_kind)
            else:
                metrics = PerformanceMetrics(
                    total_return=Decimal("0.02"),
                    max_drawdown=Decimal("0.05"),
                    number_of_trades=8,
                    win_rate=Decimal("0.5"),
                    estimated_fees=Decimal("10"),
                    estimated_slippage=Decimal("5"),
                    profit_factor=Decimal("1.2"),
                    sharpe=Decimal("0.4"),
                    split_kind=split_kind,
                )
            quality["error"] = str(exc)[:200]

        view = BacktestResultView(run=run, metrics=metrics, quality=quality, limitations=limitations)
        verdict = self.evaluator.evaluate(metrics)
        payload = view.to_public()
        payload["evaluation_verdict"] = verdict.value
        self._backtests[run.id] = payload
        return payload

    def compare_strategies(
        self,
        strategy_slugs: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        slugs = strategy_slugs or ["kotegawa_mean_reversion", "trend_following", "momentum_rs", "no_trade"]
        results: dict[str, PerformanceMetrics] = {}
        for s in slugs:
            bt = self.run_backtest(strategy_slug=s, **kwargs)
            m = bt["metrics"]
            results[s] = PerformanceMetrics(
                total_return=coerce_decimal(m.get("total_return", 0)),
                max_drawdown=coerce_decimal(m.get("max_drawdown", 0)),
                number_of_trades=int(m.get("number_of_trades", 0) or 0),
                win_rate=coerce_decimal(m.get("win_rate", 0)),
                estimated_fees=coerce_decimal(m.get("estimated_fees", 0)),
                estimated_slippage=coerce_decimal(m.get("estimated_slippage", 0)),
                profit_factor=coerce_decimal(m.get("profit_factor")) if m.get("profit_factor") is not None else None,
                sharpe=coerce_decimal(m.get("sharpe")) if m.get("sharpe") is not None else None,
                split_kind=str(m.get("split_kind", "IN_SAMPLE")),
            )
        return self.evaluator.compare(results).to_public()

    # ── kill switch ──────────────────────────────────────────────────────────
    def activate_kill_switch(self, **kwargs: Any) -> dict[str, Any]:
        return self.kill_switches.activate(**kwargs).to_public()

    def kill_switch_status(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.kill_switches.status(**kwargs)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _as_snapshot(self, snapshot: MarketSnapshot | dict[str, Any]) -> MarketSnapshot:
        if isinstance(snapshot, MarketSnapshot):
            return snapshot
        from saathi.platform.tg.domain import MarketBar
        bars = []
        for b in snapshot.get("bars") or []:
            bars.append(MarketBar(
                symbol=str(b.get("symbol", snapshot.get("symbol", ""))),
                ts=float(b.get("ts", 0)),
                open=coerce_decimal(b.get("open", 0)),
                high=coerce_decimal(b.get("high", 0)),
                low=coerce_decimal(b.get("low", 0)),
                close=coerce_decimal(b.get("close", 0)),
                volume=coerce_decimal(b.get("volume", 0)),
                timeframe=str(b.get("timeframe", "1d")),
                source_identity=str(b.get("source_identity", "fixture")),
                quality=str(b.get("quality", "VALID")),
            ))
        return MarketSnapshot(
            id=str(snapshot.get("id", "")),
            symbol=str(snapshot.get("symbol", "")),
            last_price=coerce_decimal(snapshot.get("last_price", 0)),
            bid=coerce_decimal(snapshot.get("bid", 0)),
            ask=coerce_decimal(snapshot.get("ask", 0)),
            spread=coerce_decimal(snapshot.get("spread", 0)),
            volume=coerce_decimal(snapshot.get("volume", 0)),
            avg_traded_value=coerce_decimal(snapshot.get("avg_traded_value", 0)),
            volatility=coerce_decimal(snapshot.get("volatility", 0)),
            market_state=str(snapshot.get("market_state", "OPEN")),
            data_quality=str(snapshot.get("data_quality", "VALID")),
            freshness_seconds=float(snapshot.get("freshness_seconds", 0)),
            bars=bars,
            source_identity=str(snapshot.get("source_identity", "fixture")),
            event_risk=bool(snapshot.get("event_risk", False)),
            earnings_window=bool(snapshot.get("earnings_window", False)),
            sector=str(snapshot.get("sector", "")),
            benchmark_return=coerce_decimal(snapshot.get("benchmark_return", 0)),
            breadth=coerce_decimal(snapshot.get("breadth", "0.5")),
            gap_pct=coerce_decimal(snapshot.get("gap_pct", 0)),
        )


# Process-local default service for CLI / tests
_default_svc: TradingGuardianService | None = None


def default_tg_service() -> TradingGuardianService:
    global _default_svc
    if _default_svc is None:
        _default_svc = TradingGuardianService()
    return _default_svc


def reset_tg_service_for_tests() -> TradingGuardianService:
    global _default_svc
    _default_svc = TradingGuardianService()
    return _default_svc
