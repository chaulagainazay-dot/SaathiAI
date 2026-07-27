"""M62.4 — StrategyService: server-authoritative strategy + backtest orchestration.

Permission-gated, audited, tenant-scoped, optimistic-concurrency on the mutable
strategy definition. Drives a durable, restart-safe backtest state machine and
persists reproducible evidence (manifest + result hash). Research theses are read
ONLY (never as market data). NO execution authority: this service never imports the
runtime, gateway, approval-consumption path, or any broker.
"""
from __future__ import annotations

import time as _time
from decimal import Decimal
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.market_data.models import Timeframe
from saathi.platform.market_data.fixtures import build_bars as md_build_bars, dataset_hash, fixture_manifest, DATASETS

from saathi.platform.strategy.models import (
    StrategyDefinition, StrategyType, StrategyStatus, can_strategy_transition,
    FeatureSpec, FeatureKind, SignalRule, Comparator, SignalAction, SizingRule, SizingMethod,
    CostModel, REALISTIC_COST, ZERO_COST, STRESSED_COST, ThesisReference, DatasetReference,
    strategy_hash, ENGINE_VERSION, D,
)
from saathi.platform.strategy.models import BacktestStatus, can_backtest_transition, BACKTEST_TERMINAL
from saathi.platform.strategy.store import StrategyStore
from saathi.platform.strategy.validation import (
    validate_strategy, is_runnable, evaluate_backtest, SufficiencyPolicy,
)
from saathi.platform.strategy.engine import run_backtest
from saathi.platform.strategy import stress as stress_mod
from saathi.platform.strategy import walk_forward as wf
from saathi.platform.strategy.guardian_sim import simulate_guardian_review

_COST_TIERS = {"zero": ZERO_COST, "realistic": REALISTIC_COST, "stressed": STRESSED_COST}
MAX_FEATURES = 32
MAX_SIGNALS = 32
MAX_BARS = 5000


class StrategyService:
    def __init__(self, store: StrategyStore | None = None, research_store=None):
        self.store = store or StrategyStore()
        self._research_store = research_store
        self._audit_sink = None

    def bind_audit(self, platform_store):
        self._audit_sink = platform_store
        return self

    def _audit(self, ctx, event, sid, **extra):
        if not self._audit_sink:
            return
        try:
            self._audit_sink.append_audit(event, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                          user_id=ctx.user_id, role=ctx.role, outcome=extra.pop("outcome", "ok"),
                                          detail={"strategy_id": sid, **extra})
        except Exception:
            pass

    # ── build a declarative definition from an API body ──────────────────
    def _build_definition(self, ctx, body: dict, *, sid: str) -> StrategyDefinition:
        feats_in = body.get("features", [])
        sigs_in = body.get("signals", [])
        if len(feats_in) > MAX_FEATURES or len(sigs_in) > MAX_SIGNALS:
            raise PlatformContextError("VALIDATION_FAILED", "too many features/signals")
        try:
            features = [FeatureSpec(name=f["name"], kind=FeatureKind(f["kind"]),
                                    lookback=int(f.get("lookback", 1)), forward_offset=int(f.get("forward_offset", 0)),
                                    source=f.get("source", "close")) for f in feats_in]
            signals = [SignalRule(left=s["left"], comparator=Comparator(s["comparator"]),
                                  right=str(s["right"]), action=SignalAction(s["action"])) for s in sigs_in]
            sz = body.get("sizing", {})
            sizing = SizingRule(method=SizingMethod(sz.get("method", "EQUITY_FRACTION")),
                                value=D(sz.get("value", "0.5")),
                                max_position_fraction=D(sz.get("max_position_fraction", "1")))
            tf = Timeframe(body.get("timeframe", "1d"))
            stype = StrategyType(body.get("strategy_type", "MOMENTUM"))
        except (KeyError, ValueError) as e:
            raise PlatformContextError("VALIDATION_FAILED", f"invalid strategy spec: {e}") from e

        cost = _COST_TIERS.get(body.get("cost_tier", "realistic"), REALISTIC_COST)
        return StrategyDefinition(
            id=sid, org_id=ctx.org_id, workspace_id=ctx.workspace_id, name=body.get("name", "strategy"),
            description=body.get("description", ""), strategy_type=stype,
            instrument_universe=list(body.get("instrument_universe", []) or [body.get("instrument", "TRENDING")]),
            timeframe=tf, features=features, signals=signals, sizing=sizing,
            benchmark=body.get("benchmark", ""), cost_model=cost, warmup_bars=int(body.get("warmup_bars", 0)),
            risk_max_position_fraction=D(body.get("risk_max_position_fraction", "1")),
            status=StrategyStatus.DRAFT, created_by=ctx.user_id,
        )

    # ── strategy CRUD ────────────────────────────────────────────────────
    def create_strategy(self, ctx, body: dict) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_CREATE)
        sid = new_id("strat_")
        defn = self._build_definition(ctx, body, sid=sid)
        findings = validate_strategy(defn)
        critical = [f.to_public() for f in findings if f.severity == "critical"]
        if critical:
            raise PlatformContextError("VALIDATION_FAILED", "structural: " + ", ".join(c["code"] for c in critical))
        rec = self.store.create_strategy(org_id=ctx.org_id, workspace_id=ctx.workspace_id, name=defn.name,
                                         definition=defn.to_public(), created_by=ctx.user_id)
        self._audit(ctx, "strategy.created", rec["strategy_id"], name=defn.name)
        return {**rec, "findings": [f.to_public() for f in findings]}

    def list_strategies(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return self.store.list_strategies(ctx.org_id)

    def get_strategy(self, ctx, sid) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        rec = self.store.get_strategy(ctx.org_id, sid)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "strategy not found for tenant")
        return rec

    def update_strategy(self, ctx, sid, body: dict, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        cur = self.get_strategy(ctx, sid)
        defn = self._build_definition(ctx, body, sid=sid)
        defn.status = StrategyStatus(cur["definition"].get("status", "DRAFT"))
        findings = validate_strategy(defn)
        if any(f.severity == "critical" for f in findings):
            raise PlatformContextError("VALIDATION_FAILED", "structural errors block save")
        kind, rec = self.store.update_strategy(ctx.org_id, sid, expected_version=expected_version,
                                               definition=defn.to_public())
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "strategy version conflict — reload")
        if kind == "not_found":
            raise PlatformContextError("NOT_FOUND", "strategy not found")
        self._audit(ctx, "strategy.updated", sid)
        return rec

    def set_status(self, ctx, sid, target: str, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        cur = self.get_strategy(ctx, sid)
        cur_status = StrategyStatus(cur["definition"].get("status", "DRAFT"))
        tgt = StrategyStatus(target)
        if cur_status != tgt and not can_strategy_transition(cur_status, tgt):
            raise PlatformContextError("VALIDATION_FAILED", f"illegal status transition {cur_status.value}->{tgt.value}")
        defn = dict(cur["definition"]); defn["status"] = tgt.value
        kind, rec = self.store.update_strategy(ctx.org_id, sid, expected_version=expected_version,
                                               definition=defn, status=tgt.value)
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "version conflict")
        self._audit(ctx, "strategy.status", sid, status=tgt.value)
        return rec

    # ── research thesis reference (READ ONLY) ────────────────────────────
    def _resolve_thesis(self, ctx, project_id: str, version: int | None) -> ThesisReference:
        ref = ThesisReference(project_id=project_id, thesis_version=int(version or 0))
        if not self._research_store:
            ref.note = "research store unavailable"
            return ref
        th = (self._research_store.thesis_version(ctx.org_id, project_id, version)
              if version else self._research_store.latest_thesis(ctx.org_id, project_id))
        if not th:
            ref.note = "thesis not found (non-authoritative)"
            return ref
        ref.thesis_version = th["version"]
        ref.published = bool(th.get("published"))
        conf = th.get("confidence", {}) or {}
        ref.confidence_score = float(conf.get("score", 0.0))
        # authoritative ONLY when published and state PUBLISHED (never expired/unpublished)
        ref.authoritative = ref.published and th.get("state") == "PUBLISHED"
        ref.note = "authoritative" if ref.authoritative else "non-authoritative research context"
        return ref

    def link_research(self, ctx, sid, *, project_id, thesis_version=None, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        cur = self.get_strategy(ctx, sid)
        ref = self._resolve_thesis(ctx, project_id, thesis_version)
        defn = dict(cur["definition"])
        defn.setdefault("thesis_refs", []).append(ref.to_public())
        cur_status = StrategyStatus(defn.get("status", "DRAFT"))
        if can_strategy_transition(cur_status, StrategyStatus.RESEARCH_LINKED):
            defn["status"] = StrategyStatus.RESEARCH_LINKED.value
        kind, rec = self.store.update_strategy(ctx.org_id, sid, expected_version=expected_version,
                                               definition=defn, status=defn["status"])
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "version conflict")
        self._audit(ctx, "strategy.research_linked", sid, project_id=project_id, authoritative=ref.authoritative)
        return {**rec, "thesis_ref": ref.to_public()}

    # ── immutable versions ───────────────────────────────────────────────
    def create_version(self, ctx, sid, *, parameters=None, rationale="") -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        cur = self.get_strategy(ctx, sid)
        defn = self._reconstruct(cur["definition"])
        parameters = parameters or {}
        code_hash = strategy_hash(defn, parameters)
        prev = self.store.latest_version(ctx.org_id, sid)
        rec = self.store.add_version(ctx.org_id, sid, code_hash=code_hash, config=defn.config_snapshot(),
                                     parameters=parameters, dataset_req={"universe": defn.instrument_universe,
                                                                         "timeframe": defn.timeframe.value},
                                     parent_version=(prev["version"] if prev else None), rationale=rationale,
                                     created_by=ctx.user_id)
        self._audit(ctx, "strategy.version.created", sid, version=rec["version"], code_hash=code_hash)
        return rec

    def list_versions(self, ctx, sid) -> list[dict]:
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        self.get_strategy(ctx, sid)
        return self.store.list_versions(ctx.org_id, sid)

    def get_version(self, ctx, sid, version) -> dict:
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        self.get_strategy(ctx, sid)
        rec = self.store.get_version(ctx.org_id, sid, int(version))
        if not rec:
            raise PlatformContextError("NOT_FOUND", "strategy version not found")
        return rec

    # ── reconstruct a StrategyDefinition from a stored public dict ───────
    def _reconstruct(self, pub: dict) -> StrategyDefinition:
        features = [FeatureSpec(name=f["name"], kind=FeatureKind(f["kind"]), lookback=int(f["lookback"]),
                                forward_offset=int(f.get("forward_offset", 0)), source=f.get("source", "close"))
                    for f in pub.get("features", [])]
        signals = [SignalRule(left=s["left"], comparator=Comparator(s["comparator"]), right=str(s["right"]),
                              action=SignalAction(s["action"])) for s in pub.get("signals", [])]
        sz = pub.get("sizing", {})
        sizing = SizingRule(method=SizingMethod(sz.get("method", "EQUITY_FRACTION")), value=D(sz.get("value", "0.5")),
                            max_position_fraction=D(sz.get("max_position_fraction", "1")))
        cm = pub.get("cost_model", {})
        cost = CostModel(fixed_fee=D(cm.get("fixed_fee", 0)), pct_fee=D(cm.get("pct_fee", 0)),
                         per_unit_fee=D(cm.get("per_unit_fee", 0)), min_fee=D(cm.get("min_fee", 0)),
                         slippage_bps=D(cm.get("slippage_bps", 0)), spread_slippage=bool(cm.get("spread_slippage", False)),
                         max_volume_participation=D(cm.get("max_volume_participation", 1)))
        return StrategyDefinition(
            id=pub["id"], org_id=pub["org_id"], workspace_id=pub["workspace_id"], name=pub["name"],
            description=pub.get("description", ""), strategy_type=StrategyType(pub["strategy_type"]),
            instrument_universe=list(pub["instrument_universe"]), timeframe=Timeframe(pub["timeframe"]),
            features=features, signals=signals, sizing=sizing, benchmark=pub.get("benchmark", ""),
            cost_model=cost, warmup_bars=int(pub.get("warmup_bars", 0)),
            risk_max_position_fraction=D(pub.get("risk_max_position_fraction", "1")),
            status=StrategyStatus(pub.get("status", "DRAFT")), created_by=pub.get("created_by", ""),
        )

    # ── backtest orchestration (durable state machine) ───────────────────
    def create_backtest(self, ctx, sid, *, dataset: str, cost_tier="realistic", seed=0, n=30) -> dict:
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        cur = self.get_strategy(ctx, sid)
        if dataset not in DATASETS:
            raise PlatformContextError("VALIDATION_FAILED", f"unknown dataset {dataset}")
        if not (1 <= int(n) <= MAX_BARS):
            raise PlatformContextError("VALIDATION_FAILED", "bar count out of bounds")
        defn = self._reconstruct(cur["definition"])
        version = (self.store.latest_version(ctx.org_id, sid) or self.create_version(ctx, sid))["version"]
        tf = defn.timeframe
        bars = md_build_bars(dataset, tf, int(n))
        dh = dataset_hash(dataset, tf, int(n))
        ds_ref = DatasetReference(provider="fixture", dataset_version=fixture_manifest(tf, int(n))["version"],
                                  instrument=dataset, timeframe=tf,
                                  start_epoch=bars[0].start_time.timestamp(), end_epoch=bars[-1].start_time.timestamp(),
                                  content_hash=dh, source="fixture", bar_count=len(bars))
        dsid = self.store.add_dataset(ctx.org_id, ds_ref.to_public())
        cfg = {"dataset": dataset, "cost_tier": cost_tier, "seed": int(seed), "n": int(n),
               "dataset_hash": dh, "strategy_version": version}
        corr = new_id("corr_")
        run = self.store.create_run(org_id=ctx.org_id, workspace_id=ctx.workspace_id, strategy_id=sid,
                                    strategy_version=version, dataset_id=dsid, config=cfg, seed=int(seed),
                                    created_by=ctx.user_id, correlation_id=corr)
        self._audit(ctx, "backtest.created", sid, run_id=run["run_id"], dataset=dataset)
        return run

    def _advance_run(self, ctx, rid, target: BacktestStatus) -> dict:
        run = self.store.get_run(ctx.org_id, rid)
        if not run:
            raise PlatformContextError("NOT_FOUND", "run not found")
        cur = BacktestStatus(run["status"])
        if cur != target and not can_backtest_transition(cur, target):
            raise PlatformContextError("VALIDATION_FAILED", f"illegal run transition {cur.value}->{target.value}")
        kind, rec = self.store.update_run_status(ctx.org_id, rid, expected_version=run["version"], status=target.value)
        if kind == "immutable":
            raise PlatformContextError("VALIDATION_FAILED", "run already completed (immutable)")
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "run version conflict")
        return rec

    def run_backtest(self, ctx, sid, rid) -> dict:
        """Execute a created run through its full state machine and freeze evidence."""
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        run = self.store.get_run(ctx.org_id, rid)
        if not run or run["strategy_id"] != sid:
            raise PlatformContextError("NOT_FOUND", "run not found for strategy/tenant")
        if run["completed"]:
            raise PlatformContextError("VALIDATION_FAILED", "run already completed")
        cur = self.get_strategy(ctx, sid)
        defn = self._reconstruct(cur["definition"])
        cfg = run["config"]
        cost = _COST_TIERS.get(cfg.get("cost_tier", "realistic"), REALISTIC_COST)
        tf = defn.timeframe
        bars = md_build_bars(cfg["dataset"], tf, int(cfg.get("n", 30)))
        bench = md_build_bars(defn.benchmark, tf, int(cfg.get("n", 30))) if defn.benchmark in DATASETS else None

        self._advance_run(ctx, rid, BacktestStatus.QUEUED)
        self._advance_run(ctx, rid, BacktestStatus.VALIDATING_DATA)
        runnable, findings = is_runnable(defn)
        if not runnable:
            self._advance_run(ctx, rid, BacktestStatus.FAILED if False else BacktestStatus.REJECTED)
            self.store.finalize_run(ctx.org_id, rid, status="REJECTED",
                                    manifest={"findings": [f.to_public() for f in findings]},
                                    result_hash="", engine_version=ENGINE_VERSION)
            self._audit(ctx, "backtest.rejected", sid, run_id=rid, reason="structural")
            return self.store.get_run(ctx.org_id, rid)

        self._advance_run(ctx, rid, BacktestStatus.GENERATING_FEATURES)
        self._advance_run(ctx, rid, BacktestStatus.RUNNING)
        result = run_backtest(defn, bars, cost=cost, seed=int(cfg.get("seed", 0)), benchmark_bars=bench,
                              parameters={"strategy_version": run["strategy_version"]})

        if result.status != "COMPLETE":
            # data-quality/look-ahead rejection or invariant failure — preserve evidence
            term = BacktestStatus.REJECTED if result.status == "REJECTED" else BacktestStatus.FAILED
            self.store.save_orders(ctx.org_id, rid, [o.to_public() for o in result.fills])
            self.store.save_result(ctx.org_id, rid, "metrics", {k: v.to_public() for k, v in result.metrics.items()})
            self.store.finalize_run(ctx.org_id, rid, status=term.value, manifest=result.manifest,
                                    result_hash=result.result_hash, engine_version=ENGINE_VERSION)
            self._audit(ctx, "backtest.failed", sid, run_id=rid, reason=result.reason, status=term.value)
            return self.store.get_run(ctx.org_id, rid)

        self._advance_run(ctx, rid, BacktestStatus.CALCULATING_METRICS)
        # stress + cost resilience
        self._advance_run(ctx, rid, BacktestStatus.RUNNING_STRESS_TESTS)
        stress = stress_mod.run_stress(defn, cost=cost)
        cost_res = stress_mod.cost_resilience(defn, bars)
        # sensitivity over the first feature's lookback (bounded neighbours)
        self._advance_run(ctx, rid, BacktestStatus.RUNNING_SENSITIVITY)
        sens = self._sensitivity(defn, bars, cost)
        # walk-forward
        wfres = self._walk_forward(defn, bars, run["strategy_version"], cfg["dataset_hash"])
        # guardian simulation review (veto only)
        peak_qty = self._peak_quantity(result)
        guardian = simulate_guardian_review(instrument=defn.instrument_universe[0], intended_quantity=peak_qty,
                                            reference_price=bars[-1].close, starting_cash=Decimal("100000"))

        # validation
        self._advance_run(ctx, rid, BacktestStatus.VALIDATION_REQUIRED)
        from saathi.platform.strategy.metrics import _trade_pnls
        pnls = _trade_pnls(result.fills)
        val = evaluate_backtest(result.metrics, oos_observations=wfres.get("ok", 0) * 5,
                                trade_pnls=pnls, data_quality_ok=(result.quality_summary.get("blocking", 0) == 0),
                                cost_sensitive=cost_res["cost_sensitive"], param_unstable=sens["unstable"],
                                walk_forward_consistent=wfres.get("consistent", True))

        # persist artifacts + freeze
        self.store.save_orders(ctx.org_id, rid, [o.to_public() for o in result.fills])
        self.store.save_equity(ctx.org_id, rid, [p.to_public() for p in result.equity_curve])
        self.store.save_result(ctx.org_id, rid, "metrics", {k: v.to_public() for k, v in result.metrics.items()})
        self.store.save_result(ctx.org_id, rid, "stress", stress)
        self.store.save_result(ctx.org_id, rid, "cost_resilience", cost_res)
        self.store.save_result(ctx.org_id, rid, "sensitivity", sens)
        self.store.save_result(ctx.org_id, rid, "walk_forward", wfres)
        self.store.save_result(ctx.org_id, rid, "guardian", guardian)
        self.store.save_result(ctx.org_id, rid, "validation", val.to_public())
        self.store.finalize_run(ctx.org_id, rid, status="COMPLETE", manifest=result.manifest,
                                result_hash=result.result_hash, engine_version=ENGINE_VERSION)
        self.store.set_version_validation(ctx.org_id, sid, run["strategy_version"], val.outcome)
        self._audit(ctx, "backtest.completed", sid, run_id=rid, result_hash=result.result_hash, outcome=val.outcome)
        return self.store.get_run(ctx.org_id, rid)

    def _peak_quantity(self, result) -> Decimal:
        peak = Decimal("0"); qty = Decimal("0")
        for f in result.fills:
            if f.side == "BUY":
                qty += D(f.quantity)
            else:
                qty -= D(f.quantity)
            peak = max(peak, qty)
        return peak

    def _sensitivity(self, defn, bars, cost) -> dict:
        if not defn.features:
            return {"parameter": "none", "surface": [], "cliffs": [], "unstable": False}
        base_feature = defn.features[0]
        base_lb = base_feature.lookback
        values = [max(1, base_lb - 2), max(1, base_lb - 1), base_lb, base_lb + 1, base_lb + 2]

        def rebuild(d, v):
            import copy
            nd = copy.deepcopy(d)
            nd.features[0] = FeatureSpec(name=base_feature.name, kind=base_feature.kind, lookback=int(v),
                                         forward_offset=0, source=base_feature.source)
            return nd
        return stress_mod.run_sensitivity(defn, bars, parameter=f"{base_feature.name}.lookback",
                                          values=values, rebuild=rebuild, cost=cost)

    def _walk_forward(self, defn, bars, strategy_version, dhash) -> dict:
        epochs = [b.start_time.timestamp() for b in bars]
        try:
            fold_ranges = wf.build_folds(epochs, n_folds=3, mode="expanding", train_min=max(10, defn.required_warmup()),
                                         test_size=max(3, len(bars) // 6))
        except ValueError:
            return {"n_folds": 0, "ok": 0, "failed": 0, "empty": 0, "consistent": True, "folds": []}
        folds = []
        for k, (tr, va, te) in enumerate(fold_ranges):
            test_bars = [b for b in bars if te[0] <= b.start_time.timestamp() < te[1]]
            fold = wf.Fold(index=k, train_range=tr, validation_range=va, test_range=te,
                           parameters={"lookback": defn.features[0].lookback if defn.features else 0},
                           dataset_hash=dhash, strategy_version=strategy_version)
            if len(test_bars) < 2:
                fold.status = "EMPTY"
                folds.append(fold); continue
            res = run_backtest(defn, test_bars, cost=defn.cost_model, strict_quality=False)
            fold.status = "OK" if res.status == "COMPLETE" else "FAILED"
            fold.trade_count = len(res.fills)
            tr_m = res.metrics.get("total_return"); dd_m = res.metrics.get("max_drawdown")
            fold.metrics = {"total_return": (tr_m.value if tr_m and tr_m.value is not None else None),
                            "max_drawdown": (dd_m.value if dd_m and dd_m.value is not None else None)}
            folds.append(fold)
        return wf.aggregate_folds(folds)

    def cancel_backtest(self, ctx, sid, rid) -> dict:
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        run = self.store.get_run(ctx.org_id, rid)
        if not run or run["strategy_id"] != sid:
            raise PlatformContextError("NOT_FOUND", "run not found")
        if run["completed"]:
            raise PlatformContextError("VALIDATION_FAILED", "completed run cannot be cancelled")
        kind, rec = self.store.update_run_status(ctx.org_id, rid, expected_version=run["version"],
                                                 status=BacktestStatus.CANCELLED.value)
        if kind == "immutable":
            raise PlatformContextError("VALIDATION_FAILED", "run already completed")
        self.store.finalize_run(ctx.org_id, rid, status="CANCELLED", manifest=run.get("manifest", {}),
                                result_hash=run.get("result_hash", ""), engine_version=ENGINE_VERSION)
        self._audit(ctx, "backtest.cancelled", sid, run_id=rid)
        return self.store.get_run(ctx.org_id, rid)

    # ── read backtest evidence ───────────────────────────────────────────
    def _run(self, ctx, sid, rid) -> dict:
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        run = self.store.get_run(ctx.org_id, rid)
        if not run or run["strategy_id"] != sid:
            raise PlatformContextError("NOT_FOUND", "run not found for tenant")
        return run

    def list_backtests(self, ctx, sid=None) -> list[dict]:
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return self.store.list_runs(ctx.org_id, strategy_id=sid)

    def get_backtest(self, ctx, sid, rid) -> dict:
        return self._run(ctx, sid, rid)

    def metrics(self, ctx, sid, rid) -> dict:
        self._run(ctx, sid, rid)
        return self.store.get_result(ctx.org_id, rid, "metrics") or {}

    def trades(self, ctx, sid, rid, *, limit=1000, offset=0) -> list[dict]:
        self._run(ctx, sid, rid)
        return self.store.list_orders(ctx.org_id, rid, limit=min(int(limit), 1000), offset=int(offset))

    def equity(self, ctx, sid, rid, *, limit=5000, offset=0) -> list[dict]:
        self._run(ctx, sid, rid)
        return self.store.list_equity(ctx.org_id, rid, limit=min(int(limit), 5000), offset=int(offset))

    def validation(self, ctx, sid, rid) -> dict:
        self._run(ctx, sid, rid)
        return self.store.get_result(ctx.org_id, rid, "validation") or {}

    def stress(self, ctx, sid, rid) -> dict:
        self._run(ctx, sid, rid)
        return self.store.get_result(ctx.org_id, rid, "stress") or {}

    def sensitivity(self, ctx, sid, rid) -> dict:
        self._run(ctx, sid, rid)
        return self.store.get_result(ctx.org_id, rid, "sensitivity") or {}

    def manifest(self, ctx, sid, rid) -> dict:
        run = self._run(ctx, sid, rid)
        return {"manifest": run.get("manifest", {}), "result_hash": run.get("result_hash", ""),
                "status": run["status"], "completed": bool(run["completed"])}

    # ── validation decision (owner/admin marks the strategy VALIDATED) ───
    def certify_strategy(self, ctx, sid, *, expected_version, decision: str) -> dict:
        """Owner+ marks a strategy VALIDATED or REJECTED. This is a TECHNICAL verdict.
        No agent may self-certify: this requires STRATEGY_VALIDATE (owner/admin)."""
        ctx.require_permission(PlatformPermission.STRATEGY_VALIDATE)
        cur = self.get_strategy(ctx, sid)
        cur_status = StrategyStatus(cur["definition"].get("status", "DRAFT"))
        target = StrategyStatus.VALIDATED if decision == "validate" else StrategyStatus.REJECTED
        if target == StrategyStatus.VALIDATED and cur_status != StrategyStatus.VALIDATION_REQUIRED:
            raise PlatformContextError("VALIDATION_FAILED", "strategy must be VALIDATION_REQUIRED before VALIDATED")
        defn = dict(cur["definition"]); defn["status"] = target.value
        kind, rec = self.store.update_strategy(ctx.org_id, sid, expected_version=expected_version,
                                               definition=defn, status=target.value)
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "version conflict")
        self._audit(ctx, "strategy.certified", sid, decision=target.value)
        return rec
