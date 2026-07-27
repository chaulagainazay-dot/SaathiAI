"""M62.7 — SafetyService: automated circuit-breaker orchestration.

Authoritative flow:

  paper activity → metric collection → deterministic evaluation → threshold breach
  or integrity failure → durable trip → scope halted → submissions rejected →
  alert → acknowledgement → safe-condition verification → approval-backed reset
  request → bounded reset through Runtime/Gateway → audit evidence.

The service may HALT, FREEZE, REJECT, ACKNOWLEDGE and (fail-closed) RESET. It NEVER
repairs financial state, never mutates fills/positions/cash/ledger, and fails closed
on any prohibited capability. Reconciliation remains the authoritative integrity
verifier (M62.6); this service consumes its CRITICAL findings but never repairs.
"""
from __future__ import annotations

import time as _time
import sqlite3
from decimal import Decimal
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, ApprovalStatus, new_id
from saathi.platform.trading_models import D, Environment
from saathi.platform.paper_trading.store import PaperStore, IdempotencyConflict
from saathi.platform.paper_trading.models import AccountStatus, q2
from saathi.platform.safety.store import SafetyStore
from saathi.platform.safety.metrics import MetricsCollector
from saathi.platform.safety.evaluator import BreakerEvaluator, default_account_breakers
from saathi.platform.safety.models import (
    BreakerType, BreakerScope, BreakerState, Severity, AlertLevel, OpenOrderPolicy,
    CircuitBreakerDefinition, CircuitBreakerState, CircuitBreakerTrip, SafetyFinding,
    BreakerAcknowledgement, BreakerResetRequest, BreakerResetDecision,
    BLOCKING_STATES, BROAD_SCOPES, can_breaker_transition, default_alert_level,
    default_open_order_policy, assert_safety_safe, is_agent_actor, shash, trading_day,
    SAFETY_ENGINE_VERSION,
)

MAX_THRESHOLD = Decimal("1000000000")   # sane upper bound; reject absurd configs


class SafetyService:
    def __init__(self, paper_store: PaperStore | None = None, *, platform_store=None, recon_engine=None):
        assert_safety_safe()
        self.paper = paper_store or PaperStore()
        self.store = SafetyStore(self.paper)
        self.metrics = MetricsCollector(self.paper)
        self.evaluator = BreakerEvaluator()
        self._platform_store = platform_store
        self._recon = recon_engine
        self._paper_service = None   # optional: authorized in-process cancel orchestration

    # ── wiring ────────────────────────────────────────────────────────────────────
    def bind_audit(self, platform_store):
        self._platform_store = platform_store
        return self

    def bind_paper_service(self, paper_service):
        """Authorized internal safety orchestration path for CANCEL_REMAINING_QUANTITY
        (shares the same PaperStore, so the cancel commits to the same DB). When unset,
        cancellation routes through the canonical ExecutionGateway tool path."""
        self._paper_service = paper_service
        return self

    def _recon_engine(self):
        if self._recon is None:
            from saathi.platform.paper_trading.reconciliation import ReconciliationEngine
            self._recon = ReconciliationEngine(self.paper, platform_store=self._platform_store)
        return self._recon

    def _audit(self, ctx, event, **detail):
        if not self._platform_store:
            return
        try:
            self._platform_store.append_audit(event, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                              user_id=ctx.user_id, role=ctx.role,
                                              outcome=detail.pop("outcome", "ok"), detail=detail)
        except Exception:
            pass

    @staticmethod
    def _require_human(ctx, what: str):
        if is_agent_actor(ctx):
            raise PlatformContextError("PERMISSION_DENIED", f"agents cannot {what}")

    # ── definitions (configure) ─────────────────────────────────────────────────────
    def _validate_def(self, d: CircuitBreakerDefinition) -> None:
        assert_safety_safe(environment=Environment.PAPER)
        if D(d.threshold) < 0:
            raise PlatformContextError("VALIDATION_FAILED", "threshold must be >= 0")
        if D(d.threshold) > MAX_THRESHOLD:
            raise PlatformContextError("VALIDATION_FAILED", "threshold exceeds safe bound")
        if d.warning_threshold is not None and D(d.warning_threshold) < 0:
            raise PlatformContextError("VALIDATION_FAILED", "warning threshold must be >= 0")
        if d.breaker_type == BreakerType.POSITION_CONCENTRATION and D(d.threshold) > 100:
            raise PlatformContextError("VALIDATION_FAILED", "concentration percentage must be <= 100")
        if d.window_seconds < 0 or d.min_samples < 0:
            raise PlatformContextError("VALIDATION_FAILED", "window/min_samples must be >= 0")

    def create_breaker(self, ctx, *, breaker_type: str, scope: str, scope_ref: str = "", threshold: str = "0",
                       warning_threshold: str | None = None, window_seconds: int = 0, min_samples: int = 0,
                       severity: str = "ERROR", open_order_policy: str | None = None, timezone: str = "UTC",
                       auto_trip: bool = True, requires_config: bool = False) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        self._require_human(ctx, "configure breakers")
        bt = BreakerType(breaker_type); sc = BreakerScope(scope)
        d = CircuitBreakerDefinition(
            id=new_id("brk_"), org_id=ctx.org_id, breaker_type=bt, scope=sc, scope_ref=scope_ref,
            workspace_id=ctx.workspace_id, threshold=D(threshold),
            warning_threshold=(D(warning_threshold) if warning_threshold is not None else None),
            window_seconds=int(window_seconds), min_samples=int(min_samples), severity=Severity(severity),
            auto_trip=bool(auto_trip),
            open_order_policy=(OpenOrderPolicy(open_order_policy) if open_order_policy
                               else default_open_order_policy(bt)),
            timezone=timezone, requires_config=bool(requires_config), created_by=ctx.user_id)
        self._validate_def(d)
        if self.store.find_definition(ctx.org_id, bt, sc, scope_ref):
            raise PlatformContextError("VALIDATION_FAILED", "breaker already exists for scope; PATCH to update")
        self.store.upsert_definition(d)
        self._audit(ctx, "safety.breaker.created", definition_id=d.id, breaker_type=bt.value, scope=sc.value)
        return d.to_public()

    def update_breaker(self, ctx, definition_id: str, *, expected_version: int, updates: dict) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        self._require_human(ctx, "configure breakers")
        d = self.store.get_definition(ctx.org_id, definition_id)
        if not d:
            raise PlatformContextError("NOT_FOUND", "breaker not found for tenant")
        if d.version != int(expected_version):
            raise PlatformContextError("CONFLICT", "stale breaker version")
        allowed = {"threshold", "warning_threshold", "window_seconds", "min_samples", "severity",
                   "open_order_policy", "enabled", "auto_trip", "requires_config", "timezone"}
        for k, v in updates.items():
            if k not in allowed:
                raise PlatformContextError("VALIDATION_FAILED", f"field not updatable: {k}")
            if k == "threshold":
                d.threshold = D(v)
            elif k == "warning_threshold":
                d.warning_threshold = (D(v) if v is not None else None)
            elif k == "severity":
                d.severity = Severity(v)
            elif k == "open_order_policy":
                d.open_order_policy = OpenOrderPolicy(v)
            elif k in ("enabled", "auto_trip", "requires_config"):
                setattr(d, k, bool(v))
            elif k in ("window_seconds", "min_samples"):
                setattr(d, k, int(v))
            elif k == "timezone":
                d.timezone = str(v)
        d.version += 1
        d.updated_at = _time.time()
        self._validate_def(d)
        self.store.upsert_definition(d)
        self._audit(ctx, "safety.breaker.updated", definition_id=d.id, version=d.version)
        return d.to_public()

    def provision_account_defaults(self, ctx, account_id: str) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        self._require_human(ctx, "configure breakers")
        acct = self.paper.get_account(ctx.org_id, account_id)
        if not acct:
            raise PlatformContextError("NOT_FOUND", "paper account not found for tenant")
        return self._provision_defaults(ctx.org_id, account_id, acct.workspace_id)

    def _provision_defaults(self, org_id: str, account_id: str, workspace_id: str = "") -> list[dict]:
        out = []
        for d in default_account_breakers(org_id, account_id):
            d.workspace_id = workspace_id
            if not self.store.find_definition(org_id, d.breaker_type, d.scope, d.scope_ref):
                self.store.upsert_definition(d)
            out.append(d.to_public())
        return out

    # ── reads ────────────────────────────────────────────────────────────────────────
    def list_breakers(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return [d.to_public() for d in self.store.list_definitions(ctx.org_id)]

    def get_breaker(self, ctx, definition_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        d = self.store.get_definition(ctx.org_id, definition_id)
        if not d:
            raise PlatformContextError("NOT_FOUND", "breaker not found for tenant")
        return {**d.to_public(), "revisions": self.store.definition_revisions(ctx.org_id, definition_id)}

    def list_states(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return [s.to_public() for s in self.store.list_states(ctx.org_id)]

    def list_trips(self, ctx, *, definition_id: str | None = None, limit: int = 200) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return self.store.list_trips(ctx.org_id, definition_id=definition_id, limit=limit)

    def get_trip(self, ctx, trip_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        t = self.store.get_trip(ctx.org_id, trip_id)
        if not t:
            raise PlatformContextError("NOT_FOUND", "trip not found for tenant")
        return t

    def list_alerts(self, ctx, *, limit: int = 200) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return self.store.list_alerts(ctx.org_id, limit=limit)

    def list_metrics(self, ctx, definition_id: str, *, limit: int = 100) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return self.store.list_metrics(ctx.org_id, definition_id, limit=limit)

    def list_sweeps(self, ctx, *, limit: int = 100) -> list[dict]:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return self.store.list_sweeps(ctx.org_id, limit=limit)

    def get_sweep(self, ctx, sweep_id: str) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        s = self.store.get_sweep(ctx.org_id, sweep_id)
        if not s:
            raise PlatformContextError("NOT_FOUND", "sweep not found for tenant")
        return s

    # ── core: enforce a trip (atomic) ──────────────────────────────────────────────────
    def _alert_payload(self, defn, finding: SafetyFinding, trip_id: str) -> dict:
        return {"breaker_type": defn.breaker_type.value, "scope": defn.scope.value, "scope_ref": defn.scope_ref,
                "severity": finding.severity.value, "threshold": str(defn.threshold),
                "reason_codes": list(finding.reason_codes),
                "required_action": "operator acknowledgement then approval-backed reset after safe conditions",
                "trip_id": trip_id, "open_order_policy": defn.open_order_policy.value}

    def _do_trip(self, ctx, defn: CircuitBreakerDefinition, state: CircuitBreakerState, finding: SafetyFinding,
                 *, manual: bool, tripped_by: str, recon_run_id: str = "", now: float,
                 idem_scope: str = "", idem_key: str = "", idem_payload_hash: str = "") -> dict:
        # idempotency: same key → return prior trip result
        if idem_key:
            try:
                prior = self.store.idem_lookup(ctx.org_id, idem_scope, idem_key, idem_payload_hash)
            except IdempotencyConflict as e:
                raise PlatformContextError("CONFLICT", str(e)) from e
            if prior:
                return {**prior, "idempotent_replay": True}

        trip_id = new_id("trip_")
        correlation_id = ctx.run_id or f"safety:{ctx.org_id}"
        alert_level = default_alert_level(defn.breaker_type)
        policy = defn.open_order_policy

        # plan open-order handling (freeze = enforced by halt; cancel = post-commit)
        actions: list[dict] = []
        cancel_targets: list[str] = []
        if defn.scope == BreakerScope.PAPER_ACCOUNT and defn.scope_ref:
            open_orders = [o for o in self.paper.list_orders(ctx.org_id, account_id=defn.scope_ref, limit=500)
                           if not o.is_terminal]
            for o in open_orders:
                if policy == OpenOrderPolicy.CANCEL_REMAINING_QUANTITY:
                    actions.append({"order_id": o.id, "action": "CANCEL_PLANNED"})
                    cancel_targets.append(o.id)
                else:
                    actions.append({"order_id": o.id, "action": "FREEZE"})

        snap = finding.snapshot.to_public()
        trip = CircuitBreakerTrip(
            trip_id=trip_id, org_id=ctx.org_id, definition_id=defn.id, breaker_type=defn.breaker_type,
            scope=defn.scope, scope_ref=defn.scope_ref, severity=finding.severity, alert_level=alert_level,
            ts=now, reason_codes=list(finding.reason_codes), message=finding.message, metric_snapshot=snap,
            threshold=str(defn.threshold), open_order_policy=policy, open_order_actions=actions,
            reconciliation_run_id=recon_run_id, correlation_id=correlation_id, manual=manual,
            tripped_by=tripped_by, trip_hash="")
        trip.trip_hash = shash({"engine": SAFETY_ENGINE_VERSION, "def": defn.def_hash(),
                                "snapshot": snap.get("snapshot_hash", ""), "recon": recon_run_id,
                                "scope": defn.scope.value, "ref": defn.scope_ref})

        # state transition NORMAL/WARNING → TRIPPED → HALTED
        state.state = BreakerState.HALTED
        state.last_evaluated_at = now
        state.last_metric_json = snap
        state.last_trip_id = trip_id
        state.trip_count += 1
        state.acknowledged_at = 0.0
        state.reset_requested_at = 0.0
        state.reset_at = 0.0
        state.version += 1
        if defn.breaker_type == BreakerType.MAX_DRAWDOWN:
            state.peak_equity = D(snap.get("detail", {}).get("new_peak", state.peak_equity))

        halt_account_id = defn.scope_ref if defn.scope == BreakerScope.PAPER_ACCOUNT else ""
        alert = {"alert_id": new_id("alrt_"), "level": alert_level.value, "blocking": True,
                 "message": f"{defn.breaker_type.value} tripped ({defn.scope.value})",
                 "payload": self._alert_payload(defn, finding, trip_id)}
        metric = {**snap}
        finding_row = {"severity": finding.severity.value, "breached": True,
                       "reason_codes": finding.reason_codes, "message": finding.message,
                       "breaker_type": defn.breaker_type.value}
        idem_result = {"trip": trip.to_public()}
        result = self.store.persist_trip(
            trip=trip, state=state, metric=metric, finding=finding_row, alert=alert,
            halt_account_id=halt_account_id, idem_scope=idem_scope, idem_key=idem_key,
            idem_payload_hash=idem_payload_hash, idem_result=idem_result)

        # post-commit CANCEL policy (freeze needs nothing — halt stops fills)
        if cancel_targets:
            self._cancel_open_orders(ctx, cancel_targets, trip_id)
        self._audit(ctx, "safety.breaker.tripped", trip_id=trip_id, definition_id=defn.id,
                    breaker_type=defn.breaker_type.value, scope=defn.scope.value, manual=manual,
                    outcome="halted")
        return {"trip": result}

    def _cancel_open_orders(self, ctx, order_ids: list[str], trip_id: str) -> None:
        """Cancel remaining quantity through the canonical gateway path. Any failure
        escalates (records a processing failure) but never silently drops an order."""
        from saathi.platform.paper_trading import orchestration
        for oid in order_ids:
            try:
                if self._paper_service is not None:
                    self._paper_service.cancel_order(ctx, order_id=oid,
                                                     idempotency_key=f"safety-cancel:{trip_id}:{oid}")
                else:
                    orchestration.cancel_via_gateway(ctx, order_id=oid,
                                                     idempotency_key=f"safety-cancel:{trip_id}:{oid}")
            except Exception as exc:
                self.store.record_failure_event(ctx.org_id, BreakerScope.PAPER_BROKER_PROCESSOR, "",
                                                f"cancel_failed:{oid}", _time.time())
                self._audit(ctx, "safety.open_order.cancel_failed", order_id=oid, trip_id=trip_id,
                            error=str(exc)[:200], outcome="escalated")

    def _warn(self, ctx, defn, state, finding: SafetyFinding, *, now: float) -> None:
        snap = finding.snapshot.to_public()
        state.state = BreakerState.WARNING
        state.last_evaluated_at = now
        state.last_metric_json = snap
        state.version += 1
        alert = {"alert_id": new_id("alrt_"), "level": AlertLevel.WARNING.value, "blocking": False,
                 "message": f"{defn.breaker_type.value} WARNING ({defn.scope.value})",
                 "payload": self._alert_payload(defn, finding, "")}
        self.store.persist_warning(state=state, metric=snap,
                                   finding={"severity": finding.severity.value, "breaker_type": defn.breaker_type.value,
                                            "reason_codes": finding.reason_codes, "message": finding.message,
                                            "ts": now}, alert=alert)

    def _clear_to_normal(self, state, *, now: float) -> None:
        if state.state == BreakerState.WARNING:
            state.state = BreakerState.NORMAL
            state.last_evaluated_at = now
            state.version += 1
            self.store.save_state(state)
        elif state.state == BreakerState.NORMAL:
            state.last_evaluated_at = now
            self.store.save_state(state)

    # ── on-demand / scheduled sweep ─────────────────────────────────────────────────
    def run_sweep(self, ctx, *, account_ids: list[str] | None = None, now: float | None = None,
                  marks: dict[str, dict] | None = None, batch: int = 100) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_SWEEP)
        return self._sweep(ctx, account_ids=account_ids, now=now, marks=marks, batch=batch,
                           tripped_by=f"sweep:{ctx.user_id}")

    def _sweep(self, ctx, *, account_ids, now, marks, batch, tripped_by) -> dict:
        now = float(now if now is not None else _time.time())
        marks = marks or {}
        sweep_id = new_id("swp_")
        self.store.save_sweep(ctx.org_id, sweep_id, engine_version=SAFETY_ENGINE_VERSION,
                              status="RUNNING", started_at=now)
        accts = self.paper.list_accounts(ctx.org_id)
        if account_ids is not None:
            accts = [a for a in accts if a.id in set(account_ids)]
        accts = accts[:max(0, int(batch))]
        skipped = [a.id for a in self.paper.list_accounts(ctx.org_id)
                   if account_ids is not None and a.id not in set(account_ids)]

        defs = self.store.list_definitions(ctx.org_id)
        by_account: dict[str, list[CircuitBreakerDefinition]] = {}
        for d in defs:
            if d.scope == BreakerScope.PAPER_ACCOUNT and d.enabled:
                by_account.setdefault(d.scope_ref, []).append(d)

        counts = {s.value: 0 for s in Severity}
        trips_created = 0; alerts_created = 0; findings_hashes: list[str] = []; errors: list[dict] = []
        evaluated_accounts = 0

        for a in accts:
            # auto-provision defaults so no active account is silently unmonitored
            if a.id not in by_account:
                self._provision_defaults(ctx.org_id, a.id, a.workspace_id)
                by_account[a.id] = [d for d in self.store.list_definitions(ctx.org_id)
                                    if d.scope == BreakerScope.PAPER_ACCOUNT and d.scope_ref == a.id and d.enabled]
            evaluated_accounts += 1
            m = self.metrics.account_metrics(ctx.org_id, a.id, now=now,
                                             tz_name=(by_account[a.id][0].timezone if by_account[a.id] else "UTC"),
                                             marks=marks.get(a.id))
            for d in by_account[a.id]:
                try:
                    res = self._evaluate_and_enforce(ctx, d, m, now=now, tripped_by=tripped_by, sweep_id=sweep_id)
                except Exception as exc:  # never let one breaker abort the sweep
                    errors.append({"definition_id": d.id, "error": str(exc)[:200]})
                    continue
                counts[res["severity"]] = counts.get(res["severity"], 0) + 1
                findings_hashes.append(res["hash"])
                if res["tripped"]:
                    trips_created += 1
                if res["alert"]:
                    alerts_created += 1

        completed = float(now)
        result_hash = shash({"engine": SAFETY_ENGINE_VERSION, "accounts": sorted(a.id for a in accts),
                             "findings": sorted(findings_hashes), "counts": counts})
        manifest = {"sweep_id": sweep_id, "engine_version": SAFETY_ENGINE_VERSION, "started_at": now,
                    "completed_at": completed, "scope_count": len(accts), "accounts_evaluated": evaluated_accounts,
                    "definitions_evaluated": sum(len(v) for v in by_account.values()),
                    "findings_by_severity": counts, "trips_created": trips_created,
                    "alerts_created": alerts_created, "errors": errors, "skipped_scopes": skipped,
                    "result_hash": result_hash}
        self.store.save_sweep(ctx.org_id, sweep_id, engine_version=SAFETY_ENGINE_VERSION, status="COMPLETED",
                              started_at=now, completed_at=completed, manifest=manifest, result_hash=result_hash)
        self._audit(ctx, "safety.sweep.completed", sweep_id=sweep_id, trips=trips_created,
                    accounts=evaluated_accounts)
        return manifest

    def _evaluate_and_enforce(self, ctx, defn: CircuitBreakerDefinition, m: dict, *, now: float,
                              tripped_by: str, sweep_id: str = "") -> dict:
        state = self.store.get_state(ctx.org_id, defn.id) or CircuitBreakerState(
            definition_id=defn.id, org_id=ctx.org_id, scope=defn.scope, scope_ref=defn.scope_ref)
        # already-blocking breakers are not re-tripped by a sweep (idempotent); a retrip
        # only happens after reset returns them to NORMAL.
        if state.state in BLOCKING_STATES:
            state.last_evaluated_at = now
            self.store.save_state(state)
            return {"tripped": False, "alert": False, "severity": Severity.INFO.value, "hash": "blocking"}

        rejection = None
        if defn.breaker_type == BreakerType.ORDER_REJECTION_RATE:
            rejection = self.metrics.rejection_rate(ctx.org_id, defn.scope_ref, now=now,
                                                    window_seconds=defn.window_seconds)
        failure_count = 0
        if defn.breaker_type == BreakerType.PROCESSING_FAILURE:
            failure_count = self.store.count_failures(ctx.org_id, defn.scope, defn.scope_ref,
                                                      since=now - defn.window_seconds)
        finding = self.evaluator.evaluate(defn, metrics=m, rejection=rejection, failure_count=failure_count,
                                          peak_equity=state.peak_equity, now=now)
        # keep drawdown peak fresh even when not breached
        if defn.breaker_type == BreakerType.MAX_DRAWDOWN:
            state.peak_equity = D(finding.snapshot.detail.get("new_peak", state.peak_equity))

        fh = finding.snapshot.snapshot_hash()
        if finding.breached and finding.severity == Severity.WARNING:
            self._warn(ctx, defn, state, finding, now=now)
            return {"tripped": False, "alert": True, "severity": Severity.WARNING.value, "hash": fh}
        if finding.breached and defn.auto_trip:
            self._do_trip(ctx, defn, state, finding, manual=False, tripped_by=tripped_by, now=now)
            return {"tripped": True, "alert": True, "severity": finding.severity.value, "hash": fh}
        self._clear_to_normal(state, now=now)
        return {"tripped": False, "alert": False, "severity": finding.severity.value, "hash": fh}

    # ── reconciliation integration (CRITICAL drift → auto trip) ───────────────────────
    def reconcile_and_guard(self, ctx, account_id: str) -> dict:
        """Run the M62.6 reconciliation engine; on CRITICAL drift auto-trip the
        RECONCILIATION_CRITICAL breaker. Reconciliation stays authoritative and may
        halt; this service never repairs. Returns the recon report + any trip."""
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_SWEEP)
        report = self._recon_engine().reconcile_account(ctx, account_id)
        pub = report.to_public()
        trip = None
        if pub["severity_max"] == "CRITICAL":
            defn = self.store.find_definition(ctx.org_id, BreakerType.RECONCILIATION_CRITICAL,
                                              BreakerScope.PAPER_ACCOUNT, account_id)
            if not defn:
                acct = self.paper.get_account(ctx.org_id, account_id)
                self._provision_defaults(ctx.org_id, account_id, acct.workspace_id if acct else "")
                defn = self.store.find_definition(ctx.org_id, BreakerType.RECONCILIATION_CRITICAL,
                                                  BreakerScope.PAPER_ACCOUNT, account_id)
            state = self.store.get_state(ctx.org_id, defn.id)
            if state.state not in BLOCKING_STATES:
                now = _time.time()
                snap = self.evaluator.evaluate(defn, metrics={}, now=now)  # placeholder value
                finding = SafetyFinding(
                    definition_id=defn.id, breaker_type=defn.breaker_type, scope=defn.scope,
                    scope_ref=defn.scope_ref, severity=Severity.CRITICAL, breached=True,
                    reason_codes=["reconciliation_critical_drift"] + sorted(
                        {f["code"] for f in pub["findings"] if f["severity"] == "CRITICAL"}),
                    message="reconciliation CRITICAL drift; account halted, no repair executed",
                    snapshot=snap.snapshot)
                finding.snapshot.value = Decimal(pub["counts"].get("CRITICAL", 0))
                finding.snapshot.detail = {"reconciliation_run_id": pub["run_id"], "counts": pub["counts"]}
                trip = self._do_trip(ctx, defn, state, finding, manual=False, tripped_by="reconciliation",
                                     recon_run_id=pub["run_id"], now=now,
                                     idem_scope="recon_trip", idem_key=f"recon:{pub['run_id']}",
                                     idem_payload_hash=pub["report_hash"])
        return {"reconciliation": pub, "trip": (trip or {}).get("trip") if trip else None}

    # ── market-data breakers (event-driven, fail-closed) ─────────────────────────────
    def observe_market_event(self, ctx, *, source: str, quality: str, event_ts: float, now: float | None = None,
                             seq: int | None = None, prev_seq: int | None = None, payload_hash: str = "",
                             expected_hash: str = "", max_age_seconds: int = 60,
                             scope: str = "MARKET_DATA_SOURCE") -> dict:
        """Fail-closed market-data check. Trips an INVALID/STALE breaker on the source
        or processor and blocks event processing. Does not trust later events until reset."""
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_SWEEP)
        now = float(now if now is not None else _time.time())
        sc = BreakerScope(scope)
        reasons: list[str] = []
        if str(quality).upper() != "VALID":
            reasons.append(f"quality_{str(quality).lower()}")
        if seq is not None and prev_seq is not None and seq <= prev_seq:
            reasons.append("sequence_regression")
        if expected_hash and payload_hash and payload_hash != expected_hash:
            reasons.append("hash_mismatch")
        age = now - event_ts
        stale = age > max_age_seconds
        invalid = bool([r for r in reasons if not r.startswith("stale")])

        if not reasons and not stale:
            return {"blocked": False, "reasons": []}

        btype = BreakerType.INVALID_MARKET_DATA if invalid else BreakerType.STALE_MARKET_DATA
        if stale and not invalid:
            reasons.append(f"stale_age_{int(age)}s")
        defn = self.store.find_definition(ctx.org_id, btype, sc, source)
        if not defn:
            defn = CircuitBreakerDefinition(
                id=new_id("brk_"), org_id=ctx.org_id, breaker_type=btype, scope=sc, scope_ref=source,
                threshold=Decimal(str(max_age_seconds)) if not invalid else Decimal("0"),
                severity=Severity.CRITICAL if invalid else Severity.ERROR,
                open_order_policy=default_open_order_policy(btype), created_by="system")
            self.store.upsert_definition(defn)
        state = self.store.get_state(ctx.org_id, defn.id)
        blocked_trip = None
        if state.state not in BLOCKING_STATES:
            from saathi.platform.safety.evaluator import _snap
            snap = _snap(defn, ts=now, value=Decimal(str(int(age))),
                         detail={"source": source, "quality": quality, "reasons": reasons, "age": int(age)})
            finding = SafetyFinding(definition_id=defn.id, breaker_type=btype, scope=sc, scope_ref=source,
                                    severity=defn.severity, breached=True, reason_codes=reasons,
                                    message=f"market-data {btype.value} on {source}: {','.join(reasons)}",
                                    snapshot=snap)
            blocked_trip = self._do_trip(ctx, defn, state, finding, manual=False, tripped_by="market_data",
                                         now=now, idem_scope="md_trip",
                                         idem_key=f"md:{source}:{payload_hash or event_ts}",
                                         idem_payload_hash=shash(reasons))
        return {"blocked": True, "reasons": reasons, "breaker_type": btype.value,
                "trip": (blocked_trip or {}).get("trip") if blocked_trip else None}

    def record_processing_failure(self, ctx, *, scope: str = "PAPER_BROKER_PROCESSOR", scope_ref: str = "",
                                  kind: str = "processing_error", now: float | None = None) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_SWEEP)
        now = float(now if now is not None else _time.time())
        sc = BreakerScope(scope)
        self.store.record_failure_event(ctx.org_id, sc, scope_ref, kind, now)
        defn = self.store.find_definition(ctx.org_id, BreakerType.PROCESSING_FAILURE, sc, scope_ref)
        if not defn:
            defn = CircuitBreakerDefinition(
                id=new_id("brk_"), org_id=ctx.org_id, breaker_type=BreakerType.PROCESSING_FAILURE, scope=sc,
                scope_ref=scope_ref, threshold=Decimal("5"), window_seconds=600, severity=Severity.CRITICAL,
                open_order_policy=OpenOrderPolicy.FREEZE_OPEN_ORDERS, created_by="system")
            self.store.upsert_definition(defn)
        state = self.store.get_state(ctx.org_id, defn.id)
        if state.state in BLOCKING_STATES:
            return {"tripped": False, "state": state.state.value}
        count = self.store.count_failures(ctx.org_id, sc, scope_ref, since=now - defn.window_seconds)
        finding = self.evaluator.evaluate(defn, failure_count=count, now=now)
        if finding.breached:
            self._do_trip(ctx, defn, state, finding, manual=False, tripped_by="processor", now=now)
            return {"tripped": True, "failures": count}
        return {"tripped": False, "failures": count}

    # ── manual kill switch ───────────────────────────────────────────────────────────
    def manual_trip(self, ctx, *, scope: str, scope_ref: str = "", reason: str = "manual kill switch",
                    definition_id: str = "", now: float | None = None) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_TRIP)
        self._require_human(ctx, "trip breakers")
        now = float(now if now is not None else _time.time())
        sc = BreakerScope(scope)
        if sc in BROAD_SCOPES and not ctx.role in ("owner", "admin"):
            raise PlatformContextError("PERMISSION_DENIED",
                                       f"{sc.value} kill switch requires owner/admin")
        if definition_id:
            defn = self.store.get_definition(ctx.org_id, definition_id)
            if not defn:
                raise PlatformContextError("NOT_FOUND", "breaker not found for tenant")
        else:
            defn = self.store.find_definition(ctx.org_id, BreakerType.MANUAL_KILL_SWITCH, sc, scope_ref)
            if not defn:
                defn = CircuitBreakerDefinition(
                    id=new_id("brk_"), org_id=ctx.org_id, breaker_type=BreakerType.MANUAL_KILL_SWITCH, scope=sc,
                    scope_ref=scope_ref, threshold=Decimal("0"), severity=Severity.CRITICAL,
                    open_order_policy=OpenOrderPolicy.FREEZE_OPEN_ORDERS, created_by=ctx.user_id)
                self.store.upsert_definition(defn)
        state = self.store.get_state(ctx.org_id, defn.id)
        if state.state in BLOCKING_STATES:
            return {"tripped": False, "reason": "already blocking", "state": state.state.value}
        from saathi.platform.safety.evaluator import _snap
        snap = _snap(defn, ts=now, value=Decimal("0"), detail={"reason": reason, "manual": True})
        finding = SafetyFinding(definition_id=defn.id, breaker_type=defn.breaker_type, scope=sc, scope_ref=scope_ref,
                                severity=Severity.CRITICAL, breached=True, reason_codes=["manual_kill_switch"],
                                message=reason[:200], snapshot=snap)
        return self._do_trip(ctx, defn, state, finding, manual=True, tripped_by=ctx.user_id, now=now)

    # ── acknowledgement (human, does NOT remove halt) ─────────────────────────────────
    def acknowledge(self, ctx, trip_id: str, *, note: str = "", evidence_reviewed: bool = False) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_ACKNOWLEDGE)
        self._require_human(ctx, "acknowledge breakers")
        trip = self.store.get_trip(ctx.org_id, trip_id)
        if not trip:
            raise PlatformContextError("NOT_FOUND", "trip not found for tenant")
        state = self.store.get_state(ctx.org_id, trip["definition_id"])
        if not state:
            raise PlatformContextError("NOT_FOUND", "breaker state not found")
        existing = self.store.get_ack_for_trip(ctx.org_id, trip_id)
        if existing:
            return {**existing, "idempotent_replay": True, "state": state.state.value}
        if not can_breaker_transition(state.state, BreakerState.ACKNOWLEDGED):
            raise PlatformContextError("VALIDATION_FAILED", f"cannot acknowledge from {state.state.value}")
        now = _time.time()
        ack = BreakerAcknowledgement(ack_id=new_id("ack_"), org_id=ctx.org_id, trip_id=trip_id,
                                     definition_id=trip["definition_id"], acknowledged_by=ctx.user_id,
                                     acknowledged_at=now, note=note[:500], evidence_reviewed=bool(evidence_reviewed))
        state.state = BreakerState.ACKNOWLEDGED
        state.acknowledged_at = now
        state.version += 1
        res = self.store.persist_ack(ack=ack, state=state)
        self._audit(ctx, "safety.breaker.acknowledged", trip_id=trip_id, definition_id=trip["definition_id"])
        return {**res, "state": state.state.value, "halt_retained": True}

    # ── reset request (human) ─────────────────────────────────────────────────────────
    def request_reset(self, ctx, trip_id: str, *, reason: str, idempotency_key: str = "",
                      approval_id: str = "") -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_RESET_REQUEST)
        self._require_human(ctx, "request breaker reset")
        if not reason:
            raise PlatformContextError("VALIDATION_FAILED", "reset reason required")
        trip = self.store.get_trip(ctx.org_id, trip_id)
        if not trip:
            raise PlatformContextError("NOT_FOUND", "trip not found for tenant")
        defn = self.store.get_definition(ctx.org_id, trip["definition_id"])
        state = self.store.get_state(ctx.org_id, trip["definition_id"])
        if state.state != BreakerState.ACKNOWLEDGED:
            raise PlatformContextError("VALIDATION_FAILED",
                                       f"breaker must be ACKNOWLEDGED before reset request (is {state.state.value})")
        payload_hash = shash({"definition_id": defn.id, "trip_id": trip_id, "scope": defn.scope.value,
                              "scope_ref": defn.scope_ref})
        if not can_breaker_transition(state.state, BreakerState.RESET_PENDING):
            raise PlatformContextError("VALIDATION_FAILED", "invalid transition to RESET_PENDING")
        now = _time.time()
        state.state = BreakerState.RESET_PENDING
        state.reset_requested_at = now
        state.version += 1
        # bind the request to the POST-transition breaker version so any later material
        # change to the breaker invalidates the reset (breaker_version_match check).
        req = BreakerResetRequest(
            request_id=new_id("rreq_"), org_id=ctx.org_id, trip_id=trip_id, definition_id=defn.id,
            scope=defn.scope, scope_ref=defn.scope_ref, requested_by=ctx.requested_by(),
            requested_at=now, reason=reason[:500], idempotency_key=idempotency_key,
            breaker_version=state.version, approval_id=approval_id, payload_hash=payload_hash, status="REQUESTED")
        self.store.persist_reset_request(req, state)
        self._audit(ctx, "safety.reset.requested", request_id=req.request_id, trip_id=trip_id)
        return req.to_public()

    # ── reset execution (fail-closed, server-authoritative) ───────────────────────────
    def execute_reset(self, ctx, request_id: str, *, _via_gateway: bool = False) -> dict:
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_RESET)
        self._require_human(ctx, "reset breakers")
        req = self.store.get_reset_request(ctx.org_id, request_id)
        if not req:
            raise PlatformContextError("NOT_FOUND", "reset request not found for tenant")
        if req.status == "EXECUTED":
            return {"allowed": True, "idempotent_replay": True, "request_id": request_id}
        defn = self.store.get_definition(ctx.org_id, req.definition_id)
        state = self.store.get_state(ctx.org_id, req.definition_id)
        trip = self.store.get_trip(ctx.org_id, req.trip_id)

        checks: list[dict] = []
        codes: list[str] = []

        def check(name: str, ok: bool, detail: str = ""):
            checks.append({"check": name, "ok": bool(ok), "detail": detail})
            if not ok:
                codes.append(name)

        now = _time.time()
        # 1. breaker in a resettable state
        check("state_resettable", state.state in (BreakerState.RESET_PENDING, BreakerState.ACKNOWLEDGED),
              f"state={state.state.value}")
        # 2. acknowledgement exists
        ack = self.store.get_ack_for_trip(ctx.org_id, req.trip_id)
        check("acknowledged", bool(ack), "operator acknowledgement required")
        # 3. breaker version unchanged since request
        check("breaker_version_match", state.version == req.breaker_version,
              f"request v{req.breaker_version} != current v{state.version}")
        # 4. no broader breaker still blocking this scope
        broader = self._broader_blocking(ctx.org_id, defn)
        check("no_broader_breaker", not broader, f"broader breaker active: {broader}")

        recon_run_id = ""
        # 5-6. fresh reconciliation + account invariants (account-scoped)
        if defn.scope == BreakerScope.PAPER_ACCOUNT and defn.scope_ref:
            try:
                report = self._recon_engine().reconcile_account(ctx, defn.scope_ref)
                recon_run_id = report.run_id
                check("reconciliation_clean", report.severity_max.value != "CRITICAL",
                      f"recon severity={report.severity_max.value}")
                m = self.metrics.account_metrics(ctx.org_id, defn.scope_ref, now=now, tz_name=defn.timezone)
                check("accounting_invariants", D(m["available_cash"]) >= 0 and D(m["reserved_cash"]) >= 0,
                      "available/reserved cash must be >= 0")
                # 8. triggering threshold no longer breached
                rejection = (self.metrics.rejection_rate(ctx.org_id, defn.scope_ref, now=now,
                             window_seconds=defn.window_seconds)
                             if defn.breaker_type == BreakerType.ORDER_REJECTION_RATE else None)
                fc = (self.store.count_failures(ctx.org_id, defn.scope, defn.scope_ref, since=now - defn.window_seconds)
                      if defn.breaker_type == BreakerType.PROCESSING_FAILURE else 0)
                f = self.evaluator.evaluate(defn, metrics=m, rejection=rejection, failure_count=fc,
                                            peak_equity=state.peak_equity, now=now)
                check("threshold_cleared", not f.breached, f"{defn.breaker_type.value} still breached")
            except PlatformContextError as e:
                check("reconciliation_clean", False, f"recon error: {e.message}")
        else:
            check("threshold_cleared", True, "non-account scope; no metric re-eval")

        # 10. approval (server-owned, single-use, tenant-scoped, payload-matched)
        approval_ok, approval_reason, consume_cb = self._verify_reset_approval(ctx, req)
        check("approval_valid", approval_ok, approval_reason)

        allowed = all(c["ok"] for c in checks)
        decision = BreakerResetDecision(
            decision_id=new_id("rdec_"), org_id=ctx.org_id, request_id=request_id, trip_id=req.trip_id,
            definition_id=defn.id, allowed=allowed, ts=now, checks=checks, reason_codes=codes,
            decided_by=ctx.user_id, reconciliation_run_id=recon_run_id, approval_id=req.approval_id)

        if not allowed:
            # record denial only (no state change, no approval consumption, halt retained)
            req.status = "REJECTED" if state.state == BreakerState.RESET_PENDING else req.status
            # keep breaker blocking; move RESET_PENDING back to ACKNOWLEDGED for retry
            if state.state == BreakerState.RESET_PENDING:
                state.state = BreakerState.ACKNOWLEDGED
                state.reset_requested_at = 0.0
                state.version += 1
            self.store.persist_reset(decision=decision, request=req, state=state)
            self._audit(ctx, "safety.reset.denied", request_id=request_id, reasons=codes, outcome="denied")
            return {"allowed": False, "decision": decision.to_public(), "halt_retained": True}

        # success: RESET_PENDING → RESET → NORMAL (both legal); unhalt account if safe
        if not (can_breaker_transition(state.state, BreakerState.RESET)
                and can_breaker_transition(BreakerState.RESET, BreakerState.NORMAL)):
            raise PlatformContextError("VALIDATION_FAILED", "reset transition path invalid")
        state.state = BreakerState.NORMAL
        state.reset_at = now
        state.last_trip_id = ""
        state.version += 1
        req.status = "EXECUTED"
        unhalt = ""
        if defn.scope == BreakerScope.PAPER_ACCOUNT and defn.scope_ref:
            acct = self.paper.get_account(ctx.org_id, defn.scope_ref)
            if acct and acct.status == AccountStatus.HALTED and not self._other_account_blockers(ctx.org_id, defn):
                unhalt = defn.scope_ref
        self.store.persist_reset(decision=decision, request=req, state=state,
                                 unhalt_account_id=unhalt, consume_approval=consume_cb)
        self._audit(ctx, "safety.reset.executed", request_id=request_id, trip_id=req.trip_id,
                    account_unhalted=bool(unhalt), reconciliation_run_id=recon_run_id, outcome="reset")
        return {"allowed": True, "decision": decision.to_public(), "account_unhalted": bool(unhalt),
                "financial_state_modified": False}

    # ── reset helpers ────────────────────────────────────────────────────────────────
    def _broader_blocking(self, org_id: str, defn: CircuitBreakerDefinition) -> str:
        """A breaker at a broader scope still blocking this scope prevents reset."""
        hierarchy = {BreakerScope.PAPER_ACCOUNT: [BreakerScope.WORKSPACE, BreakerScope.TENANT,
                                                  BreakerScope.GLOBAL_PAPER],
                     BreakerScope.INSTRUMENT: [BreakerScope.TENANT, BreakerScope.GLOBAL_PAPER],
                     BreakerScope.STRATEGY_VERSION: [BreakerScope.TENANT, BreakerScope.GLOBAL_PAPER],
                     BreakerScope.WORKSPACE: [BreakerScope.TENANT, BreakerScope.GLOBAL_PAPER],
                     BreakerScope.MARKET_DATA_SOURCE: [BreakerScope.GLOBAL_PAPER],
                     BreakerScope.PAPER_BROKER_PROCESSOR: [BreakerScope.GLOBAL_PAPER]}
        for s in self.store.list_states(org_id):
            if not s.is_blocking():
                continue
            if s.scope in hierarchy.get(defn.scope, []):
                return f"{s.scope.value}:{s.scope_ref}"
        return ""

    def _other_account_blockers(self, org_id: str, defn: CircuitBreakerDefinition) -> bool:
        """Another account-scoped breaker still blocking the same account keeps it halted."""
        for s in self.store.list_states(org_id):
            if s.definition_id == defn.id:
                continue
            if s.scope == BreakerScope.PAPER_ACCOUNT and s.scope_ref == defn.scope_ref and s.is_blocking():
                return True
        return False

    def _verify_reset_approval(self, ctx, req: BreakerResetRequest):
        """Server-owned reset approval: existing, APPROVED, unexpired, single-use,
        same tenant, payload/scope-matched, not self-approved by an agent."""
        if not self._platform_store:
            return (False, "approval store unavailable (fail closed)", None)
        if not req.approval_id:
            return (False, "reset approval required", None)
        ap = self._platform_store.get_approval(req.approval_id)
        if not ap:
            return (False, "approval not found", None)
        if ap.org_id != ctx.org_id:
            return (False, "cross-tenant approval rejected", None)
        if ap.status != ApprovalStatus.APPROVED.value:
            return (False, f"approval not usable ({ap.status})", None)
        if ap.expires_at and ap.expires_at < _time.time():
            return (False, "approval expired", None)
        if ap.tool_id and ap.tool_id != "paper_safety.reset":
            return (False, "approval tool mismatch", None)
        # payload / scope match: approved target must equal the request payload hash
        if ap.target_resource and ap.target_resource != req.payload_hash:
            return (False, "approved payload/scope differs from request", None)
        if ap.decided_by and ap.decided_by == ctx.user_id and ap.requested_by == ctx.requested_by():
            return (False, "self-approval prohibited", None)
        org_id = ctx.org_id; approval_id = req.approval_id

        def _consume(cur: sqlite3.Cursor) -> bool:
            try:
                r = cur.execute("UPDATE approvals SET status=?, consumed_at=? WHERE approval_id=? AND status=? "
                                "AND org_id=?", (ApprovalStatus.CONSUMED.value, _time.time(), approval_id,
                                                 ApprovalStatus.APPROVED.value, org_id))
                return r.rowcount == 1
            except sqlite3.OperationalError:
                return False
        return (True, "ok", _consume)

    # ── Guardian posture ───────────────────────────────────────────────────────────────
    def breaker_posture(self, ctx, *, account_id: str = "", symbol: str = "", source: str = "",
                        strategy_version: str = "", workspace_id: str = "") -> dict:
        """All active blocking breakers relevant to a prospective order. Consumed by
        the Trading Guardian: any blocking breaker vetoes submission."""
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        blocking: list[dict] = []
        for s in self.store.list_states(ctx.org_id):
            if not s.is_blocking():
                continue
            relevant = (
                s.scope == BreakerScope.GLOBAL_PAPER
                or (s.scope == BreakerScope.TENANT)
                or (s.scope == BreakerScope.WORKSPACE and s.scope_ref in ("", workspace_id, ctx.workspace_id))
                or (s.scope == BreakerScope.PAPER_ACCOUNT and s.scope_ref == account_id)
                or (s.scope == BreakerScope.INSTRUMENT and s.scope_ref == symbol)
                or (s.scope == BreakerScope.MARKET_DATA_SOURCE and s.scope_ref == source)
                or (s.scope == BreakerScope.STRATEGY_VERSION and s.scope_ref == strategy_version)
                or (s.scope == BreakerScope.PAPER_BROKER_PROCESSOR)
            )
            if relevant:
                d = self.store.get_definition(ctx.org_id, s.definition_id)
                blocking.append({"definition_id": s.definition_id,
                                 "breaker_type": d.breaker_type.value if d else "",
                                 "scope": s.scope.value, "scope_ref": s.scope_ref, "state": s.state.value,
                                 "trip_id": s.last_trip_id})
        return {"blocked": bool(blocking), "breakers": blocking}
