"""Governed migration plan / preflight / approval / execute (M18.4).

Write execution always goes through ExecutionGateway (UniversalBoundary).
Provider client write is only invoked from the gateway handler.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Optional

from saathi.providers.insforge.config import InsForgeConfig, load_config
from saathi.providers.insforge.errors import InsForgeError, InsForgeErrorCategory
from saathi.providers.insforge.migration_policy import (
    build_request_from_dict,
    ops_to_sql,
    plan_migration,
)
from saathi.providers.insforge.migration_store import MigrationLedger
from saathi.providers.insforge.migration_types import (
    ExecutionOutcome,
    MigrationExecutionResult,
    MigrationPlan,
    MigrationRequest,
    MigrationRisk,
    PreflightResult,
    PreflightStrength,
    RISK_TO_GATEWAY,
    new_request_id,
)
from saathi.providers.insforge.provider import InsForgeProvider, PROVIDER_ID
from saathi.providers.insforge.sanitization import sanitize_value

TOOL_ID = "insforge.migration.apply"
CONNECTOR_ID = "insforge"
CAPABILITY_ID = "insforge_migration_apply"

# Risk integer for connector store (matches MANUAL_ONLY style high)
_RISK_INT = {
    MigrationRisk.LOW: 3,
    MigrationRisk.ELEVATED: 4,
    MigrationRisk.PROHIBITED: 4,
}


class MigrationService:
    """Plan → preflight → approve → execute (once) → verify."""

    def __init__(
        self,
        config: InsForgeConfig | None = None,
        *,
        provider: InsForgeProvider | None = None,
        ledger: MigrationLedger | None = None,
        approval_store: Any = None,
        write_executor: Callable[[MigrationRequest, MigrationPlan], dict] | None = None,
    ):
        self.config = config or load_config()
        self.provider = provider or InsForgeProvider(config=self.config, audit=True)
        self.ledger = ledger or MigrationLedger()
        self._approval_store = approval_store
        self._write_executor = write_executor  # injectable for tests
        self._last_preflight: dict[str, PreflightResult] = {}
        self._events: list[dict] = []

    # ── planning ────────────────────────────────────────────────────────────

    def plan(self, raw: dict | MigrationRequest) -> MigrationPlan:
        if isinstance(raw, MigrationRequest):
            req = raw
            err = ""
        else:
            req, err = build_request_from_dict(raw)
            if err or req is None:
                plan = MigrationPlan(
                    ok=False, fingerprint="", risk=MigrationRisk.PROHIBITED,
                    approval_level="L4", operations=[], affected_objects=[],
                    reversible=False, rollback_ops=[],
                    denied_reason=err or "invalid_request",
                )
                self._emit("migration_validation_denied", plan.to_dict())
                return plan
        plan = plan_migration(req)
        self._emit(
            "migration_plan_created" if plan.ok else "migration_validation_denied",
            plan.to_dict(),
        )
        return plan

    def validate(self, raw: dict | MigrationRequest) -> MigrationPlan:
        return self.plan(raw)

    # ── preflight ───────────────────────────────────────────────────────────

    def preflight(self, raw: dict | MigrationRequest) -> PreflightResult:
        plan = self.plan(raw)
        if not plan.ok:
            return PreflightResult(
                ok=False,
                strength=PreflightStrength.LOCAL_POLICY_ONLY,
                fingerprint="",
                risk=plan.risk,
                approval_level=plan.approval_level,
                provider_contacted=False,
                denied_reason=plan.denied_reason,
                plan=plan.to_dict(),
            )

        warnings = list(plan.warnings)
        strength = PreflightStrength.LOCAL_POLICY_ONLY
        provider_contacted = False

        # Optional provider schema read for stronger preflight (still not dry-run SQL)
        if self.config.enabled and self.config.base_url:
            try:
                r = self.provider.list_schema_objects()
                provider_contacted = True
                if r.ok:
                    strength = PreflightStrength.PROVIDER_VALIDATED
                    existing = set(r.data.get("tables") or [])
                    for t in plan.affected_objects:
                        # create_table on existing → warning only
                        ops = [o for o in plan.operations if o.get("table") == t]
                        if any(o.get("op") == "create_table" for o in ops) and t in existing:
                            warnings.append(f"table_may_already_exist:{t}")
                else:
                    warnings.append(f"provider_schema_read_failed:{r.error_category}")
            except Exception as e:
                warnings.append(f"provider_contact_error:{type(e).__name__}")

        # Honest labeling: we do not have TRANSACTION_ROLLBACK_VERIFIED in pilot
        pf = PreflightResult(
            ok=True,
            strength=strength,
            fingerprint=plan.fingerprint,
            risk=plan.risk,
            approval_level=plan.approval_level,
            provider_contacted=provider_contacted,
            warnings=warnings,
            plan=plan.to_dict(),
        )
        self._last_preflight[plan.fingerprint] = pf
        self._emit("migration_preflight_completed", pf.to_dict())
        return pf

    # ── approval ────────────────────────────────────────────────────────────

    def request_approval(
        self,
        raw: dict | MigrationRequest,
        *,
        owner: str,
        ttl_sec: int = 3600,
    ) -> dict:
        """Create pending approval bound to migration fingerprint (connector store)."""
        plan = self.plan(raw)
        if not plan.ok:
            return {"ok": False, "error": plan.denied_reason, "approval_id": ""}

        pf = self._last_preflight.get(plan.fingerprint)
        if pf is None:
            pf = self.preflight(raw)
        if not pf.ok:
            return {"ok": False, "error": pf.denied_reason, "approval_id": ""}

        store = self._get_approval_store()
        risk_i = _RISK_INT[plan.risk]
        aid = store.add_approval(
            owner=owner,
            connector_id=CONNECTOR_ID,
            account_id=plan.project_id,
            tool_id=TOOL_ID,
            capability_id=CAPABILITY_ID,
            input_hash=plan.fingerprint,
            risk=risk_i,
            environment=plan.environment,
            target=f"insforge:{plan.project_id}",
            ttl_sec=ttl_sec,
            max_uses=1,
        )
        self._emit("migration_approval_requested", {
            "approval_id": aid,
            "fingerprint": plan.fingerprint,
            "risk": plan.risk.value,
            "owner": owner,
        })
        return {
            "ok": True,
            "approval_id": aid,
            "fingerprint": plan.fingerprint,
            "risk": plan.risk.value,
            "approval_level": plan.approval_level,
            "status": "pending",
            "input_hash": plan.fingerprint,
        }

    def approve(
        self,
        approval_id: str,
        *,
        actor: str,
        approved: bool = True,
    ) -> dict:
        """Resolve approval. Actor must not equal requestor self-approval for agents —
        enforced by caller policy; we record actor."""
        store = self._get_approval_store()
        a = store.resolve_approval(approval_id, approved=approved, actor=actor)
        if not a:
            return {"ok": False, "error": "approval_not_found"}
        return {
            "ok": a.get("status") in ("approved", "denied", "expired"),
            "approval": {
                "id": a.get("id"),
                "status": a.get("status"),
                "input_hash": a.get("input_hash"),
                "environment": a.get("environment"),
                "risk": a.get("risk"),
            },
        }

    # ── execute via gateway ─────────────────────────────────────────────────

    def execute(
        self,
        raw: dict | MigrationRequest,
        *,
        approval_id: str,
        owner: str,
        actor_id: str = "",
    ) -> MigrationExecutionResult:
        t0 = time.time()
        actor_id = actor_id or owner

        if not self.config.enabled:
            return self._fail_exec(
                "", approval_id, ExecutionOutcome.NOT_APPLIED,
                "provider_disabled", "provider_disabled", t0,
            )
        if not self.config.writes_enabled:
            return self._fail_exec(
                "", approval_id, ExecutionOutcome.NOT_APPLIED,
                "writes_disabled", "writes_disabled_set_SAATHI_INSFORGE_WRITES_ENABLED", t0,
            )

        if isinstance(raw, MigrationRequest):
            req = raw
        else:
            req, err = build_request_from_dict(raw)
            if err or req is None:
                return self._fail_exec(
                    "", approval_id, ExecutionOutcome.NOT_APPLIED,
                    "invalid_request", err or "invalid", t0,
                )

        plan = plan_migration(req)
        if not plan.ok:
            return self._fail_exec(
                plan.fingerprint, approval_id, ExecutionOutcome.NOT_APPLIED,
                "plan_denied", plan.denied_reason, t0,
            )

        # Preflight evidence required
        pf = self._last_preflight.get(plan.fingerprint)
        if pf is None or not pf.ok or pf.fingerprint != plan.fingerprint:
            return self._fail_exec(
                plan.fingerprint, approval_id, ExecutionOutcome.NOT_APPLIED,
                "preflight_required", "run_preflight_before_execute", t0,
            )

        # Approval binding
        bind_err = self._validate_approval(
            approval_id, plan=plan, owner=owner, requestor=req.requestor, actor=actor_id,
        )
        if bind_err:
            self._emit("migration_execution_denied", {
                "reason": bind_err, "fingerprint": plan.fingerprint,
            })
            return self._fail_exec(
                plan.fingerprint, approval_id, ExecutionOutcome.NOT_APPLIED,
                "approval_invalid", bind_err, t0,
            )

        # Idempotency claim
        claimed, existing = self.ledger.claim(
            fingerprint=plan.fingerprint,
            idempotency_key=req.ensure_idempotency_key(),
            approval_id=approval_id,
            environment=plan.environment,
            project_id=plan.project_id,
        )
        if not claimed and existing:
            if existing.get("status") in ("completed", "verified", "duplicate"):
                prev = {}
                try:
                    import json
                    prev = json.loads(existing.get("result_json") or "{}")
                except Exception:
                    prev = {}
                return MigrationExecutionResult(
                    ok=True,
                    outcome=ExecutionOutcome.DUPLICATE_ALREADY_APPLIED,
                    fingerprint=plan.fingerprint,
                    approval_id=approval_id,
                    verified=bool(prev.get("verified")),
                    verification_detail=prev.get("verification_detail", "prior_result"),
                    rollback_guidance=self._rollback_guidance(plan),
                    duplicate=True,
                    duration_ms=(time.time() - t0) * 1000,
                    detail="duplicate_suppressed",
                )
            if existing.get("status") == "in_progress":
                return self._fail_exec(
                    plan.fingerprint, approval_id, ExecutionOutcome.OUTCOME_UNKNOWN,
                    "in_progress", "concurrent_or_stale_claim", t0,
                )

        # Build ToolIntent and submit through UniversalBoundary
        try:
            result = self._gateway_execute(req, plan, approval_id=approval_id, actor_id=actor_id)
        except Exception as e:
            self.ledger.complete(plan.fingerprint, "failed", {"error": type(e).__name__})
            return self._fail_exec(
                plan.fingerprint, approval_id, ExecutionOutcome.OUTCOME_UNKNOWN,
                "execution_error", type(e).__name__, t0,
            )

        # Consume approval after attempt (single-use)
        try:
            self._get_approval_store().consume_approval(approval_id)
        except Exception:
            pass

        # Verify via read-only provider
        verified, vdetail = self._verify(plan, apply_result=result)
        if result.get("applied") and verified:
            outcome = ExecutionOutcome.APPLIED_AND_VERIFIED
            ok = True
            status = "verified"
        elif result.get("applied") and not verified:
            outcome = ExecutionOutcome.APPLIED_VERIFICATION_FAILED
            ok = False
            status = "verify_failed"
        elif result.get("applied") is None:
            outcome = ExecutionOutcome.OUTCOME_UNKNOWN
            ok = False
            status = "unknown"
        else:
            outcome = ExecutionOutcome.NOT_APPLIED
            ok = False
            status = "not_applied"

        exec_res = MigrationExecutionResult(
            ok=ok,
            outcome=outcome,
            fingerprint=plan.fingerprint,
            approval_id=approval_id,
            execution_id=str(result.get("execution_id") or ""),
            verified=verified,
            verification_detail=vdetail,
            rollback_guidance=self._rollback_guidance(plan),
            detail=str(result.get("detail") or "")[:300],
            duration_ms=(time.time() - t0) * 1000,
            error_category="" if ok else outcome.value.lower(),
        )
        self.ledger.complete(plan.fingerprint, status, exec_res.to_dict())
        self._emit("migration_execution_completed", exec_res.to_dict())
        self._record_evidence(exec_res)
        return exec_res

    def status(self, fingerprint: str) -> dict:
        row = self.ledger.get(fingerprint)
        if not row:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "record": {
            "fingerprint": row.get("fingerprint"),
            "status": row.get("status"),
            "approval_id": row.get("approval_id"),
            "environment": row.get("environment"),
            "project_id": row.get("project_id"),
            "updated_at": row.get("updated_at"),
        }}

    def rollback_guidance(self, raw: dict | MigrationRequest) -> dict:
        plan = self.plan(raw)
        g = self._rollback_guidance(plan)
        self._emit("migration_rollback_guidance", g)
        return g

    # ── internals ───────────────────────────────────────────────────────────

    def _validate_approval(
        self,
        approval_id: str,
        *,
        plan: MigrationPlan,
        owner: str,
        requestor: str,
        actor: str,
    ) -> str:
        if not approval_id:
            return "approval_missing"
        store = self._get_approval_store()
        a = store.get_approval(approval_id)
        if not a:
            return "approval_not_found"
        if a.get("status") == "denied":
            return "approval_denied"
        if a.get("status") == "expired" or (
            a.get("expires_at") and a["expires_at"] < time.time()
        ):
            return "approval_expired"
        if a.get("status") != "approved":
            # auto-resolve path: tests may pre-approve; still require approved
            return f"approval_status:{a.get('status')}"
        if a.get("input_hash") != plan.fingerprint:
            return "fingerprint_mismatch"
        if a.get("environment") != plan.environment:
            return "environment_mismatch"
        if a.get("connector_id") != CONNECTOR_ID:
            return "provider_mismatch"
        if a.get("tool_id") != TOOL_ID:
            return "tool_mismatch"
        if a.get("account_id") != plan.project_id:
            return "project_mismatch"
        if int(a.get("risk", -1)) != _RISK_INT[plan.risk]:
            return "risk_mismatch"
        if a.get("used", 0) >= a.get("max_uses", 1):
            return "approval_already_consumed"
        # No self-approval for agent actors
        if actor.startswith("agent:") and actor == f"agent:{requestor}":
            return "self_approval_denied"
        if actor == requestor and str(requestor).startswith("agent"):
            return "self_approval_denied"
        return ""

    def _gateway_execute(
        self,
        req: MigrationRequest,
        plan: MigrationPlan,
        *,
        approval_id: str,
        actor_id: str,
    ) -> dict:
        """Submit through UniversalBoundary; handler performs provider write."""
        handler_result: dict = {}

        def handler(intent, record) -> dict:
            # Direct write only inside gateway handler
            if self._write_executor:
                out = self._write_executor(req, plan)
            else:
                out = self._default_provider_write(req, plan)
            handler_result.update(out if isinstance(out, dict) else {"applied": bool(out)})
            return handler_result

        try:
            from saathi.execution.toolintent import (
                ApprovalLevel,
                ActorType,
                RiskLevel,
                builder,
            )
            from saathi.execution.universal import UniversalBoundary

            boundary = UniversalBoundary(auto_integrations=False)
            boundary.register_handler("connector", handler)

            risk = RiskLevel.HIGH if plan.risk == MigrationRisk.LOW else RiskLevel.CRITICAL
            approval = ApprovalLevel.L3 if plan.approval_level == "L3" else ApprovalLevel.L4
            atype = ActorType.AGENT if str(actor_id).startswith("agent") else ActorType.USER

            b = builder()
            b.actor(actor_id, atype)
            b.capability(CAPABILITY_ID, CONNECTOR_ID, "migration_apply")
            b.risk(risk, approval)
            b.parameters({
                "fingerprint": plan.fingerprint,
                "migration_name": plan.migration_name,
                "project_id": plan.project_id,
                "environment": plan.environment,
                "operations": plan.operations,
            })
            b.metadata({
                "family": "connector",
                "provider": PROVIDER_ID,
                "approval_pre_resolved": True,
                "require_approval": False,
                "insforge_migration": True,
                "approval_id": approval_id,
                "environment": plan.environment,
                "account_id": plan.project_id,
            })
            b.data["idempotency_key"] = plan.fingerprint
            intent = b.build()

            rec = boundary.submit(
                intent, approval_id=approval_id, handler=handler, execute=True,
            )
            st = str(getattr(rec.status, "value", rec.status)).lower()
            result_payload = dict(handler_result)
            if result_payload.get("applied") is None:
                if st in ("succeeded", "completed", "success"):
                    result_payload["applied"] = True
                elif st in ("failed", "denied", "cancelled"):
                    result_payload["applied"] = False
                else:
                    result_payload["applied"] = None
            result_payload["execution_id"] = getattr(rec, "execution_id", "") or ""
            result_payload["gateway_status"] = st
            return result_payload
        except Exception:
            if self._write_executor:
                # Still only allow controlled executor, but surface gateway failure
                out = self._write_executor(req, plan)
                if isinstance(out, dict):
                    out.setdefault("execution_id", new_request_id())
                    out.setdefault("gateway_error", True)
                    return out
            raise

    def _default_provider_write(self, req: MigrationRequest, plan: MigrationPlan) -> dict:
        """POST migration payload to allowlisted path only."""
        from saathi.providers.insforge.client import InsForgeClient
        stmts = ops_to_sql(req.operations)
        client = self.provider._client  # governed client
        # Use migration-only POST
        payload = {
            "name": plan.migration_name,
            "version": req.version,
            "fingerprint": plan.fingerprint,
            "statements": stmts,
            "operations": plan.operations,
            "project_id": plan.project_id,
            "environment": plan.environment,
        }
        try:
            raw = client.post_json("/api/database/migrations", json_body=payload)
            return {"applied": True, "provider_response": sanitize_value(raw, max_str=200)}
        except InsForgeError as e:
            return {
                "applied": False,
                "error_category": e.category.value,
                "detail": e.detail,
            }

    def _verify(self, plan: MigrationPlan, *, apply_result: dict) -> tuple[bool, str]:
        if apply_result.get("applied") is not True:
            return False, "not_applied"
        # Prefer mock/test hook
        if apply_result.get("verify_override") is not None:
            return bool(apply_result["verify_override"]), str(
                apply_result.get("verify_detail") or "override"
            )
        if not self.config.enabled:
            # Without live provider, verification can only check apply_result claims
            if apply_result.get("simulated"):
                return True, "simulated_verification"
            return False, "provider_disabled_cannot_verify"

        try:
            r = self.provider.list_schema_objects()
            if not r.ok:
                return False, f"schema_read_failed:{r.error_category}"
            tables = set(r.data.get("tables") or [])
            missing = [t for t in plan.affected_objects if t not in tables
                       and any(o.get("op") == "create_table" and o.get("table") == t
                               for o in plan.operations)]
            if missing:
                return False, f"tables_missing:{','.join(missing)}"
            return True, "schema_objects_present"
        except Exception as e:
            return False, f"verify_error:{type(e).__name__}"

    def _rollback_guidance(self, plan: MigrationPlan) -> dict:
        return {
            "fingerprint": plan.fingerprint,
            "rollback_ops": plan.rollback_ops,
            "rollback_risk": "elevated",
            "approval_required": True,
            "auto_execute": False,
            "data_loss_warning": any(
                o.get("op") in ("drop_table", "drop_column") for o in plan.rollback_ops
            ),
            "verification_steps": [
                "re-read schema via list_schema_objects",
                "confirm objects removed or restored",
            ],
            "note": "rollback is guidance only in M18.4; not auto-executed",
        }

    def _get_approval_store(self):
        if self._approval_store is not None:
            return self._approval_store
        from saathi.connectors.platform.store import ConnectorStore
        return ConnectorStore()

    def _fail_exec(
        self, fp, approval_id, outcome, cat, detail, t0,
    ) -> MigrationExecutionResult:
        res = MigrationExecutionResult(
            ok=False, outcome=outcome, fingerprint=fp or "",
            approval_id=approval_id, error_category=cat, detail=detail,
            duration_ms=(time.time() - t0) * 1000,
            rollback_guidance={},
        )
        self._emit("migration_execution_denied", res.to_dict())
        return res

    def _emit(self, event: str, payload: dict) -> None:
        rec = {"type": event, "provider": PROVIDER_ID, "payload": sanitize_value(payload)}
        self._events.append(rec)
        if len(self._events) > 200:
            del self._events[: len(self._events) - 200]
        try:
            from saathi.events import bus as bus_mod
            b = getattr(bus_mod, "default_bus", None)
            if callable(b):
                b().emit(event, "insforge_migration", rec["payload"])
        except Exception:
            pass
        try:
            from saathi.security.store import get_store
            get_store().audit(
                event, ok=payload.get("ok", True) is not False,
                user_id="system", detail=event[:200],
            )
        except Exception:
            pass

    def _record_evidence(self, res: MigrationExecutionResult) -> None:
        try:
            from saathi.evidence.schema import Evidence
            from saathi.evidence import store as ev_mod
            e = Evidence(
                department="engineering",
                project="insforge_migration",
                episode=res.fingerprint[:16],
                director="insforge_migration",
                workflow="m18.4",
                provider=PROVIDER_ID,
                status=res.outcome.value,
                confidence=1.0 if res.ok else 0.3,
                metrics={
                    "outcome": res.outcome.value,
                    "verified": res.verified,
                    "duplicate": res.duplicate,
                    "duration_ms": res.duration_ms,
                },
            )
            res.evidence_id = ev_mod.EvidenceStore().record(e)
        except Exception:
            pass

    def recent_events(self, limit: int = 30) -> list[dict]:
        return list(self._events[-limit:])
