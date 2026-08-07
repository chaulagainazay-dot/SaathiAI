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
        # M184–M191 historical research subsystem
        from saathi.platform.tg.historical.store import HistoricalDatasetStore
        from saathi.platform.tg.historical.import_service import HistoricalImportService
        from saathi.platform.tg.historical.research import HistoricalResearchRunner
        self.historical_store = HistoricalDatasetStore()
        self.historical_import = HistoricalImportService(self.historical_store)
        self.historical_research = HistoricalResearchRunner(self.historical_store)

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
        if p.status == ProposalStatus.PAPER_SUBMITTED and p.paper_order_id:
            # Idempotent re-attach: same paper order is allowed; different id rejected
            if p.paper_order_id != paper_order_id:
                raise TGServiceError("DUPLICATE_PAPER_ORDER", "proposal already has a different paper order")
            return p.to_public()
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
        classification: str | None = None,
        is_test_context: bool = False,
        allow_fixture_demo: bool = True,
        source_path: str = "",
        bars: list | None = None,
    ) -> dict[str, Any]:
        """Run deterministic backtest with mandatory data classification.

        Hard policy: never silently substitute fixture metrics into failed runs.
        M62 fixture datasets are labeled SYNTHETIC_VALIDATION or FIXTURE_TEST_ONLY.
        """
        from saathi.platform.tg.domain import BacktestRunRef, BacktestResultView
        from saathi.platform.tg.data_contract import (
            DataClassification,
            classify_dataset,
            build_provenance,
            incomplete_result,
            rejected_result,
            is_authoritative,
            M62_FIXTURE_DATASETS,
        )
        from saathi.platform.tg.evaluation import EligibilityContext

        cls = classify_dataset(
            dataset,
            explicit=classification,
            is_test_context=is_test_context,
            source_path=source_path,
        )
        # Unknown non-fixture without bars/path → incomplete (fail closed)
        if cls == DataClassification.INCOMPLETE and bars is None and not source_path:
            if dataset.upper() not in M62_FIXTURE_DATASETS and not allow_fixture_demo:
                payload = incomplete_result(
                    reason="missing_dataset_provenance",
                    dataset_id=dataset,
                    strategy_version="1.0.0",
                )
                self._backtests[payload.get("provenance", {}).get("dataset_fingerprint", "inc")] = payload
                return payload

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
        quality: dict[str, Any] = {"engine": "m62_4_bridge"}
        limitations = [
            "Simulated fills may differ from real execution.",
            "Historical performance is not future performance.",
            "No profitability claim.",
            "PAPER / research only.",
            "Synthetic and fixture results are not market evidence.",
        ]

        try:
            from saathi.platform.strategy.fixtures import (
                valid_momentum, valid_mean_reversion,
            )
            from saathi.platform.strategy.engine import run_backtest
            from saathi.platform.strategy.models import REALISTIC_COST, ZERO_COST, STRESSED_COST
            from saathi.platform.market_data.fixtures import build_bars, DATASETS
            from saathi.platform.market_data.models import Timeframe

            cost_map = {"realistic": REALISTIC_COST, "zero": ZERO_COST, "stressed": STRESSED_COST}
            cost = cost_map.get(cost_tier, REALISTIC_COST)

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
                used_bars = bars or []
                if not used_bars and dataset.upper() in M62_FIXTURE_DATASETS | set(DATASETS):
                    used_bars = build_bars(
                        dataset if dataset in DATASETS else "TRENDING", Timeframe.D1, n,
                    )
                prov = build_provenance(
                    dataset_id=dataset,
                    bars=used_bars,
                    classification=cls,
                    strategy_version="1.0.0",
                    fee_bps=str(getattr(cost, "fee_bps", "0")),
                    slippage_bps=str(getattr(cost, "slippage_bps", "0")),
                    is_test_context=is_test_context,
                    source_path=source_path,
                    notes=["no_trade_control"],
                )
            else:
                builder = mapping.get(strategy_slug)
                if builder is None:
                    payload = rejected_result(
                        reason="unknown_strategy_mapping",
                        dataset_id=dataset,
                        error=strategy_slug,
                    )
                    return payload
                defn = builder()
                if bars is not None:
                    used_bars = bars
                else:
                    if dataset not in DATASETS and dataset.upper() not in M62_FIXTURE_DATASETS:
                        # Fail closed — do not invent bars or metrics
                        return incomplete_result(
                            reason="dataset_not_available_or_unmapped",
                            dataset_id=dataset,
                            strategy_version="1.0.0",
                            error="AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA",
                        )
                    ds = dataset if dataset in DATASETS else dataset
                    if ds not in DATASETS:
                        return incomplete_result(
                            reason="fixture_dataset_name_unknown",
                            dataset_id=dataset,
                        )
                    used_bars = build_bars(ds, Timeframe.D1, n)
                    if classification is None:
                        cls = (
                            DataClassification.FIXTURE_TEST_ONLY
                            if is_test_context
                            else DataClassification.SYNTHETIC_VALIDATION
                        )

                result = run_backtest(defn, used_bars, seed=seed, cost=cost)
                run.status = result.status if result.status else "COMPLETE"
                if result.status not in ("COMPLETE",):
                    # Fail closed — do not fabricate metrics
                    prov = build_provenance(
                        dataset_id=dataset, bars=used_bars, classification=DataClassification.INCOMPLETE,
                        strategy_version="1.0.0", notes=[result.reason or result.status],
                    )
                    payload = {
                        "run": run.to_public(),
                        "metrics": None,
                        "status": result.status,
                        "reason": result.reason,
                        "quality": result.quality_summary,
                        "provenance": prov.to_public(),
                        "data_classification": DataClassification.INCOMPLETE.value,
                        "authoritative": False,
                        "evaluation_verdict": "INSUFFICIENT_EVIDENCE",
                        "fixture_metrics_used": False,
                        "paper_only": True,
                        "live_authorized": False,
                        "limitations": limitations + [f"engine_status={result.status}"],
                    }
                    self._backtests[run.id] = payload
                    return payload

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
                    number_of_trades=int(_mv("trade_count", "0") or _mv("number_of_trades", "0") or len(result.fills or [])),
                    estimated_fees=_mv("total_fees", "0") if "total_fees" in raw_metrics else _mv("fees", "0"),
                    estimated_slippage=_mv("total_slippage", "0") if "total_slippage" in raw_metrics else _mv("slippage", "0"),
                    win_rate=_mv("win_rate"),
                    volatility=_mv("volatility"),
                    split_kind=split_kind,
                )
                if metrics.number_of_trades == 0 and result.fills:
                    metrics.number_of_trades = len(result.fills)
                if "sharpe" in raw_metrics:
                    metrics.sharpe = _mv("sharpe")
                if "sortino" in raw_metrics:
                    metrics.sortino = _mv("sortino")
                if "profit_factor" in raw_metrics:
                    metrics.profit_factor = _mv("profit_factor")
                quality["result_hash"] = result.result_hash
                quality["look_ahead_ok"] = result.look_ahead_ok
                quality["metric_keys"] = list(raw_metrics.keys())
                prov = build_provenance(
                    dataset_id=dataset,
                    bars=used_bars,
                    classification=cls,
                    strategy_version="1.0.0",
                    fee_bps=str(getattr(cost, "fee_bps", "10")),
                    slippage_bps=str(getattr(cost, "slippage_bps", "5")),
                    is_test_context=is_test_context,
                    source_path=source_path,
                )
        except Exception as exc:
            # FAIL CLOSED — never COMPLETE_WITH_FIXTURE_METRICS
            return incomplete_result(
                reason="backtest_engine_exception",
                dataset_id=dataset,
                strategy_version="1.0.0",
                error=f"{type(exc).__name__}: {exc}"[:240],
            )

        el = EligibilityContext(
            data_classification=cls.value,
            trade_count=metrics.number_of_trades,
            costs_included=True,
            max_drawdown=abs(metrics.max_drawdown),
            reconciled=True,
            policy_risk_passed=False,
            strategy_version_immutable=True,
            audit_complete=False,
            oos_evaluated=split_kind in ("OUT_OF_SAMPLE", "WALK_FORWARD", "TEST"),
            walk_forward_evaluated=False,
            stress_completed=False,
        )
        verdict = self.evaluator.evaluate(metrics, eligibility=el)
        view = BacktestResultView(run=run, metrics=metrics, quality=quality, limitations=limitations)
        payload = view.to_public()
        payload["status"] = run.status
        payload["evaluation_verdict"] = verdict.value
        payload["data_classification"] = cls.value
        payload["authoritative"] = is_authoritative(cls)
        payload["provenance"] = prov.to_public()
        payload["fixture_metrics_used"] = False
        payload["paper_only"] = True
        payload["live_authorized"] = False
        if not is_authoritative(cls):
            payload["research_label"] = (
                "FIXTURE_TEST_ONLY" if cls == DataClassification.FIXTURE_TEST_ONLY
                else "SYNTHETIC_VALIDATION"
            )
            payload["limitations"] = limitations + [
                "Result is not authoritative market evidence.",
                "Cannot support PAPER_ELIGIBLE promotion alone.",
            ]
        self._backtests[run.id] = payload
        return payload

    def run_walk_forward(
        self,
        *,
        strategy_slug: str,
        dataset: str = "TRENDING",
        n: int = 60,
        mode: str = "expanding",
        n_folds: int = 3,
        is_test_context: bool = False,
        classification: str | None = None,
    ) -> dict[str, Any]:
        from saathi.platform.tg.walk_forward import run_walk_forward, WalkForwardConfig
        from saathi.platform.tg.data_contract import classify_dataset, DataClassification, M62_FIXTURE_DATASETS
        from saathi.platform.strategy.fixtures import valid_momentum, valid_mean_reversion
        from saathi.platform.strategy.engine import run_backtest
        from saathi.platform.market_data.fixtures import build_bars, DATASETS
        from saathi.platform.market_data.models import Timeframe

        if strategy_slug == "no_trade":
            return {
                "status": "COMPLETE",
                "strategy_slug": "no_trade",
                "n_folds": 0,
                "walk_forward_consistent": True,
                "final_test_untouched": True,
                "out_of_sample_expectancy": "0",
                "data_classification": classify_dataset(dataset, is_test_context=is_test_context).value,
                "authoritative": False,
                "paper_only": True,
                "note": "control baseline — zero trades by design",
            }

        cls = classify_dataset(dataset, explicit=classification, is_test_context=is_test_context)
        if dataset not in DATASETS:
            from saathi.platform.tg.data_contract import incomplete_result
            return incomplete_result(reason="dataset_unavailable_for_walk_forward", dataset_id=dataset)

        bars = build_bars(dataset, Timeframe.D1, n)
        if classification is None and dataset in DATASETS:
            cls = DataClassification.FIXTURE_TEST_ONLY if is_test_context else DataClassification.SYNTHETIC_VALIDATION

        mapping = {
            "trend_following": valid_momentum,
            "kotegawa_mean_reversion": valid_mean_reversion,
            "momentum_rs": valid_momentum,
        }
        base_builder = mapping.get(strategy_slug, valid_momentum)

        def strategy_builder(params: dict[str, Any]):
            d = base_builder()
            # bounded parameter perturbations via sizing fraction if provided
            if "equity_fraction" in params:
                from decimal import Decimal as D
                d.sizing.value = D(str(params["equity_fraction"]))
            return d

        candidates = [
            {},
            {"equity_fraction": "0.3"},
            {"equity_fraction": "0.5"},
        ]
        return run_walk_forward(
            strategy_slug=strategy_slug,
            bars=bars,
            dataset_id=dataset,
            classification=cls,
            strategy_builder=strategy_builder,
            run_backtest_fn=lambda defn, b, seed=0: run_backtest(defn, b, seed=seed),
            config=WalkForwardConfig(mode=mode, n_folds=n_folds, candidate_parameter_sets=candidates),
        )

    def run_stress(
        self,
        *,
        strategy_slug: str,
        dataset: str = "TRENDING",
        n: int = 40,
        is_test_context: bool = False,
    ) -> dict[str, Any]:
        from saathi.platform.tg.stress_lab import run_stress_lab
        from saathi.platform.tg.data_contract import classify_dataset, DataClassification
        from saathi.platform.strategy.fixtures import valid_momentum, valid_mean_reversion
        from saathi.platform.strategy.engine import run_backtest
        from saathi.platform.market_data.fixtures import build_bars, DATASETS
        from saathi.platform.market_data.models import Timeframe

        if strategy_slug == "no_trade":
            return {
                "status": "COMPLETE",
                "strategy_slug": "no_trade",
                "robustness_verdict": "ROBUST",
                "critical_failures": 0,
                "cases": [],
                "promote_blocked": False,
                "paper_only": True,
                "authoritative": False,
                "note": "control — no positions to stress",
            }
        if dataset not in DATASETS:
            from saathi.platform.tg.data_contract import incomplete_result
            return incomplete_result(reason="dataset_unavailable_for_stress", dataset_id=dataset)
        bars = build_bars(dataset, Timeframe.D1, n)
        cls = DataClassification.FIXTURE_TEST_ONLY if is_test_context else DataClassification.SYNTHETIC_VALIDATION
        mapping = {
            "trend_following": valid_momentum,
            "kotegawa_mean_reversion": valid_mean_reversion,
            "momentum_rs": valid_momentum,
        }
        defn = mapping.get(strategy_slug, valid_momentum)()
        return run_stress_lab(
            strategy_slug=strategy_slug,
            defn=defn,
            bars=bars,
            dataset_id=dataset,
            classification=cls,
            run_backtest_fn=lambda d, b, cost=None: run_backtest(d, b, cost=cost) if cost is not None else run_backtest(d, b),
        )

    def compare_strategies(
        self,
        strategy_slugs: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from saathi.platform.tg.evaluation import EligibilityContext
        from saathi.platform.tg.data_contract import DataClassification

        slugs = strategy_slugs or ["kotegawa_mean_reversion", "trend_following", "momentum_rs", "no_trade"]
        results: dict[str, PerformanceMetrics] = {}
        el_map: dict[str, EligibilityContext] = {}
        scorecards: dict[str, dict[str, Any]] = {}
        for s in slugs:
            bt = self.run_backtest(strategy_slug=s, **kwargs)
            cls = bt.get("data_classification", DataClassification.SYNTHETIC_VALIDATION.value)
            m_raw = bt.get("metrics")
            if m_raw is None:
                results[s] = PerformanceMetrics(number_of_trades=0)
                el_map[s] = EligibilityContext(data_classification=cls)
                scorecards[s] = self.evaluator.scorecard(s, results[s], eligibility=el_map[s], data_classification=cls)
                continue
            m = PerformanceMetrics(
                total_return=coerce_decimal(m_raw.get("total_return", 0)),
                max_drawdown=coerce_decimal(m_raw.get("max_drawdown", 0)),
                number_of_trades=int(m_raw.get("number_of_trades", 0) or 0),
                win_rate=coerce_decimal(m_raw.get("win_rate", 0)),
                estimated_fees=coerce_decimal(m_raw.get("estimated_fees", 0)),
                estimated_slippage=coerce_decimal(m_raw.get("estimated_slippage", 0)),
                profit_factor=coerce_decimal(m_raw.get("profit_factor")) if m_raw.get("profit_factor") is not None else None,
                sharpe=coerce_decimal(m_raw.get("sharpe")) if m_raw.get("sharpe") is not None else None,
                split_kind=str(m_raw.get("split_kind", "IN_SAMPLE")),
            )
            results[s] = m
            el_map[s] = EligibilityContext(
                data_classification=cls,
                trade_count=m.number_of_trades,
                costs_included=True,
                max_drawdown=abs(m.max_drawdown),
                strategy_version_immutable=True,
            )
            scorecards[s] = self.evaluator.scorecard(s, m, eligibility=el_map[s], data_classification=cls)
        return self.evaluator.compare(results, eligibility_map=el_map, scorecards=scorecards).to_public()

    def research_scorecard(self, strategy_slug: str, **kwargs: Any) -> dict[str, Any]:
        """Full research pack: backtest + walk-forward + stress + eligibility."""
        from saathi.platform.tg.evaluation import EligibilityContext
        from saathi.platform.tg.data_contract import is_authoritative

        bt = self.run_backtest(strategy_slug=strategy_slug, **kwargs)
        wf = self.run_walk_forward(strategy_slug=strategy_slug, **{k: v for k, v in kwargs.items() if k in ("dataset", "n", "is_test_context", "classification")})
        st = self.run_stress(strategy_slug=strategy_slug, **{k: v for k, v in kwargs.items() if k in ("dataset", "n", "is_test_context")})
        cls = bt.get("data_classification", "SYNTHETIC_VALIDATION")
        m_raw = bt.get("metrics") or {}
        metrics = PerformanceMetrics(
            total_return=coerce_decimal(m_raw.get("total_return", 0)),
            max_drawdown=coerce_decimal(m_raw.get("max_drawdown", 0)),
            number_of_trades=int(m_raw.get("number_of_trades", 0) or 0),
            estimated_fees=coerce_decimal(m_raw.get("estimated_fees", 0)),
            estimated_slippage=coerce_decimal(m_raw.get("estimated_slippage", 0)),
            profit_factor=coerce_decimal(m_raw.get("profit_factor")) if m_raw.get("profit_factor") is not None else None,
            sharpe=coerce_decimal(m_raw.get("sharpe")) if m_raw.get("sharpe") is not None else None,
        )
        el = EligibilityContext(
            data_classification=cls,
            trade_count=metrics.number_of_trades,
            oos_evaluated=bool(wf.get("n_folds", 0)),
            walk_forward_evaluated=wf.get("status") == "COMPLETE",
            walk_forward_consistent=bool(wf.get("walk_forward_consistent")),
            costs_included=True,
            stress_completed=st.get("status") == "COMPLETE",
            robustness_verdict=str(st.get("robustness_verdict", "")),
            critical_robustness_failure=bool(st.get("promote_blocked") or st.get("critical_failures", 0) > 0),
            max_drawdown=abs(metrics.max_drawdown),
            parameter_stable=coerce_decimal(wf.get("parameter_stability", 0)) >= Decimal("0.5"),
            reconciled=True,
            policy_risk_passed=False,
            strategy_version_immutable=True,
            audit_complete=True,
        )
        card = self.evaluator.scorecard(
            strategy_slug, metrics, eligibility=el, walk_forward=wf, stress=st, data_classification=cls,
        )
        return {
            "scorecard": card,
            "backtest": bt,
            "walk_forward": wf,
            "stress": st,
            "authoritative": is_authoritative(cls),
            "paper_only": True,
            "live_authorized": False,
        }

    # ── M184–M191 historical data + research ─────────────────────────────────
    def import_historical_dataset(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Import local historical file via read-only adapters. Paper research only."""
        return self.historical_import.import_file(path, **kwargs)

    def list_historical_datasets(self, *, org_id: str = "local", workspace_id: str = "local") -> dict[str, Any]:
        datasets = self.historical_store.list_datasets(org_id=org_id, workspace_id=workspace_id)
        return {
            "datasets": [d.to_public() for d in datasets],
            "store": self.historical_store.to_public_summary(),
            "paper_only": True,
            "live_authorized": False,
        }

    def inspect_historical_dataset(
        self,
        dataset_id: str,
        version: str | None = None,
        *,
        org_id: str = "local",
        workspace_id: str = "local",
    ) -> dict[str, Any]:
        if version:
            v = self.historical_store.get_version(dataset_id, version)
        else:
            v = self.historical_store.get_latest(dataset_id)
        if not v or (org_id and v.org_id and v.org_id != org_id):
            raise TGServiceError("NOT_FOUND", "dataset version not found")
        return {
            "version": v.to_public(include_bars=False),
            "promotable": v.promotable,
            "paper_only": True,
        }

    def quarantine_historical_dataset(
        self,
        dataset_id: str,
        version: str,
        *,
        reason: str = "operator_quarantine",
    ) -> dict[str, Any]:
        v = self.historical_store.get_version(dataset_id, version)
        if not v:
            raise TGServiceError("NOT_FOUND", "dataset version not found")
        if v.immutable and v.status.value.startswith("ACCEPTED"):
            # Accepted immutable versions cannot be mutated; record quarantine flag via notes only denied
            raise TGServiceError("IMMUTABLE", "accepted dataset version is immutable")
        rec = self.historical_store.quarantine(v, reason=reason)
        return {"quarantine": rec.to_public(), "version": v.to_public(), "paper_only": True}

    def list_historical_quarantine(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "quarantine": [q.to_public() for q in self.historical_store.list_quarantine(**kwargs)],
            "paper_only": True,
            "usable_for_promotion": False,
        }

    def historical_calendars(self) -> dict[str, Any]:
        from saathi.platform.tg.historical.calendars import list_calendars_public, SUPPORTED_MARKET_CALENDARS
        return {
            "calendars": list_calendars_public(),
            "supported": list(SUPPORTED_MARKET_CALENDARS),
            "paper_only": True,
        }

    def run_historical_research(
        self,
        *,
        strategy_slug: str,
        dataset_id: str = "",
        version: str | None = None,
        period: str = "FULL",
        seed: int = 42,
        fee_bps: str = "10",
        slippage_bps: str = "5",
        spread_model: str = "realistic",
        n_folds: int = 3,
        mc_simulations: int = 100,
        org_id: str = "local",
        workspace_id: str = "local",
        bars: list | None = None,
        classification: str | None = None,
    ) -> dict[str, Any]:
        from saathi.platform.tg.historical.research import HistoricalResearchRunner, ResearchConfig, ResearchPeriod
        from saathi.platform.tg.data_contract import DataClassification

        cfg = ResearchConfig(
            period=ResearchPeriod(period) if period in {p.value for p in ResearchPeriod} else ResearchPeriod.FULL,
            seed=seed,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            spread_model=spread_model,
            n_folds=n_folds,
            mc_simulations=min(int(mc_simulations), 500),
        )
        dver = None
        if dataset_id:
            dver = (
                self.historical_store.get_version(dataset_id, version)
                if version
                else self.historical_store.get_latest(dataset_id)
            )
            if dver is None:
                raise TGServiceError("NOT_FOUND", f"dataset {dataset_id} not found")
        cls = classification or (
            dver.classification.value if dver else DataClassification.INCOMPLETE.value
        )
        result = self.historical_research.run(
            strategy_slug=strategy_slug,
            dataset_version=dver,
            bars=bars,
            classification=cls,
            config=cfg,
            dataset_id=dataset_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        # Journal evidence (append-only)
        try:
            from saathi.platform.tg.domain import TradeJournalEntry
            self.journal.append(TradeJournalEntry(
                strategy_id=strategy_slug,
                operator_notes=(
                    f"historical_research_run run={result.get('run_id')} "
                    f"verdict={result.get('qualification_verdict')} dataset={dataset_id}"
                ),
                evidence_refs=[
                    str(result.get("run_id") or ""),
                    str(result.get("output_fingerprint") or "")[:32],
                ],
                market_context={
                    "kind": "historical_research",
                    "authoritative": result.get("authoritative"),
                    "data_classification": result.get("data_classification"),
                },
                org_id=org_id,
                workspace_id=workspace_id,
            ))
        except Exception:
            pass
        return result

    def historical_research_status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            r = self.historical_research.get_run(run_id)
            if not r:
                raise TGServiceError("NOT_FOUND", "research run not found")
            return r
        return {"runs": self.historical_research.list_runs(), "paper_only": True}

    def run_monte_carlo_analysis(
        self,
        *,
        strategy_slug: str = "trend_following",
        dataset: str = "TRENDING",
        n: int = 40,
        seed: int = 42,
        n_simulations: int = 100,
        dataset_id: str = "",
    ) -> dict[str, Any]:
        from saathi.platform.tg.historical.monte_carlo import run_monte_carlo, MonteCarloConfig
        if dataset_id:
            research = self.run_historical_research(
                strategy_slug=strategy_slug, dataset_id=dataset_id, seed=seed, mc_simulations=n_simulations,
            )
            return {
                "monte_carlo": research.get("monte_carlo"),
                "strategy_slug": strategy_slug,
                "dataset_id": dataset_id,
                "paper_only": True,
            }
        bt = self.run_backtest(strategy_slug=strategy_slug, dataset=dataset, n=n, is_test_context=True)
        mc = run_monte_carlo(
            backtest_result=bt,
            config=MonteCarloConfig(n_simulations=min(n_simulations, 500), seed=seed),
        )
        return {
            "monte_carlo": mc,
            "strategy_slug": strategy_slug,
            "dataset": dataset,
            "data_classification": bt.get("data_classification"),
            "authoritative": bt.get("authoritative"),
            "paper_only": True,
            "note": "Synthetic/fixture backtest MC is research-only and cannot promote strategies.",
        }

    def qualify_strategy_historical(
        self,
        strategy_slug: str,
        *,
        dataset_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        if dataset_id:
            research = self.run_historical_research(
                strategy_slug=strategy_slug, dataset_id=dataset_id, **{
                    k: v for k, v in kwargs.items()
                    if k in ("version", "period", "seed", "fee_bps", "slippage_bps", "n_folds", "mc_simulations", "org_id", "workspace_id")
                },
            )
            return {
                "qualification": research.get("scorecard"),
                "research_run_id": research.get("run_id"),
                "paper_only": True,
                "live_authorized": False,
            }
        # Fixture path — always non-eligible for PAPER
        bt_kwargs = {
            k: v for k, v in kwargs.items()
            if k in (
                "dataset", "n", "seed", "cost_tier", "split_kind",
                "is_test_context", "classification", "org_id", "workspace_id",
            )
        }
        pack = self.research_scorecard(strategy_slug=strategy_slug, **bt_kwargs)
        from saathi.platform.tg.historical.monte_carlo import run_monte_carlo, MonteCarloConfig
        n_sim = int(kwargs.get("mc_simulations") or 50)
        mc = run_monte_carlo(
            backtest_result=pack.get("backtest"),
            config=MonteCarloConfig(n_simulations=min(n_sim, 500), seed=int(kwargs.get("seed") or 0)),
        )
        from saathi.platform.tg.historical.qualification import qualify_strategy, build_gates_from_evidence
        from saathi.platform.tg.domain import PerformanceMetrics as PM
        m_raw = (pack.get("backtest") or {}).get("metrics") or {}
        metrics = PM(
            total_return=coerce_decimal(m_raw.get("total_return", 0)),
            max_drawdown=coerce_decimal(m_raw.get("max_drawdown", 0)),
            number_of_trades=int(m_raw.get("number_of_trades", 0) or 0),
        )
        gates = build_gates_from_evidence(
            data_classification=pack.get("scorecard", {}).get("data_classification", "SYNTHETIC_VALIDATION"),
            quality_verdict="",
            trade_count=metrics.number_of_trades,
            walk_forward=pack.get("walk_forward"),
            stress=pack.get("stress"),
            monte_carlo=mc,
            metrics=metrics,
            fee_bps="10",
            spread_model="realistic",
            slippage_bps="5",
        )
        q = qualify_strategy(
            strategy_slug,
            metrics=metrics,
            gates=gates,
            data_classification=pack.get("scorecard", {}).get("data_classification", "SYNTHETIC_VALIDATION"),
            walk_forward=pack.get("walk_forward"),
            stress=pack.get("stress"),
            monte_carlo=mc,
        )
        return {"qualification": q, "monte_carlo": mc, "paper_only": True, "live_authorized": False}

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
