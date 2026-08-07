"""M222 — Security Validation.

Verify broker isolation, credential isolation, approval isolation,
audit integrity, LLM authority boundaries, environment separation,
sandbox separation. No component may bypass approval.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_sandbox.credentials import CredentialTrustError, CredentialTrustFramework
from saathi.platform.tg.broker_sandbox.emulator import SandboxEmulator
from saathi.platform.tg.broker_sandbox.models import (
    BROKER_CREDENTIAL_SUPPORT,
    EXCHANGE_AUTH_CAPABLE,
    LIVE_ORDER_CAPABLE,
    LIVE_TRADING_AUTHORIZED,
    LLM_BOUNDARY,
    OAUTH_CAPABLE,
    PAPER_POSTURE,
    PRODUCTION_DEPLOY_CAPABLE,
    REAL_BROKER_CONNECTION_CAPABLE,
    SecurityCheckResult,
)
from saathi.platform.tg.broker_sandbox.registry import CapabilityRegistry
from saathi.platform.tg.broker_sandbox.store import SandboxStore, _uid
from saathi.platform.tg.broker_sandbox.trust_pipeline import TrustApprovalPipeline, TrustPipelineError


class SecurityValidator:
    def __init__(
        self,
        store: SandboxStore,
        registry: CapabilityRegistry,
        credentials: CredentialTrustFramework,
        trust: TrustApprovalPipeline,
        emulator: SandboxEmulator,
    ):
        self.store = store
        self.registry = registry
        self.credentials = credentials
        self.trust = trust
        self.emulator = emulator

    def _record(self, name: str, result: SecurityCheckResult, detail: dict) -> dict[str, Any]:
        cid = _uid("sec")
        self.store.execute(
            """INSERT INTO bs_security_checks(id, check_name, result, detail_json, created_at)
               VALUES(?,?,?,?,?)""",
            (cid, name, result.value, json.dumps(detail), time.time()),
        )
        return {
            "id": cid,
            "check_name": name,
            "result": result.value,
            "detail": detail,
            "passed": result == SecurityCheckResult.PASS,
        }

    def check_broker_isolation(self) -> dict[str, Any]:
        inv = self.registry.assert_all_not_connected()
        # Attempt connect on catalog broker
        refused = self.registry.refuse_connect("catalog.binance")
        ok = inv["ok"] and refused["ok"] is False
        return self._record(
            "broker_isolation",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {"invariant": inv, "connect_refused": refused},
        )

    def check_credential_isolation(self) -> dict[str, Any]:
        # Reject secret material
        rejected = False
        try:
            self.credentials.create_reference(
                "catalog.alpaca",
                provider_metadata={"api_key": "sk-live-secret-value"},
                actor="security-test",
            )
        except CredentialTrustError as e:
            rejected = e.code == "SECRET_MATERIAL_REJECTED"

        ref = self.credentials.create_reference(
            "catalog.alpaca",
            label="meta-only",
            provider_metadata={"provider": "ALPACA", "env": "SANDBOX"},
            actor="security-test",
        )
        use = self.credentials.attempt_use(ref["id"])
        ok = (
            rejected
            and ref["usable"] is False
            and ref["secret_material_present"] is False
            and use["ok"] is False
            and BROKER_CREDENTIAL_SUPPORT is False
        )
        return self._record(
            "credential_isolation",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {
                "secret_rejected": rejected,
                "usable": ref["usable"],
                "use_refused": not use["ok"],
                "broker_credential_support": BROKER_CREDENTIAL_SUPPORT,
            },
        )

    def check_approval_isolation(self) -> dict[str, Any]:
        # Auto-activate refused
        auto = self.trust.attempt_activate_without_approval("catalog.kraken")
        # Partial pipeline cannot activate
        pipe = self.trust.create_pipeline("catalog.kraken", created_by="security-test")
        self.trust.decide(
            pipe["id"], stage="OWNER", decision="approve",
            actor="owner:sec", actor_role="OWNER",
        )
        gate = self.trust.require_all_stages(pipe["id"])
        # LLM cannot approve
        llm_blocked = False
        try:
            self.trust.decide(
                pipe["id"], stage="SECURITY", decision="approve",
                actor="llm:assistant", actor_role="LLM",
            )
        except TrustPipelineError as e:
            llm_blocked = e.code == "LLM_APPROVAL_FORBIDDEN"

        ok = (
            auto["ok"] is False
            and gate["allowed_sandbox"] is False
            and gate["allowed_live"] is False
            and llm_blocked
        )
        return self._record(
            "approval_isolation",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {
                "auto_activate_refused": not auto["ok"],
                "partial_blocked": not gate["allowed_sandbox"],
                "live_blocked": not gate["allowed_live"],
                "llm_blocked": llm_blocked,
            },
        )

    def check_audit_integrity(self) -> dict[str, Any]:
        before = len(self.store.list_audit(limit=1000))
        self.store.audit("security.audit_probe", actor="security-test", detail={"probe": True})
        after = self.store.list_audit(limit=1000)
        found = any(a["kind"] == "security.audit_probe" for a in after)
        ok = found and len(after) >= before
        return self._record(
            "audit_integrity",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {"events": len(after), "probe_found": found},
        )

    def check_llm_authority_boundaries(self) -> dict[str, Any]:
        forbidden = [
            "llm_may_connect_brokers",
            "llm_may_store_credentials",
            "llm_may_approve_credentials",
            "llm_may_approve_brokers",
            "llm_may_execute_orders",
            "llm_may_enable_live_mode",
            "llm_may_authorize_trading",
            "llm_may_bypass_approval",
        ]
        violations = [k for k in forbidden if LLM_BOUNDARY.get(k) is not False]
        allowed = [
            "llm_may_explain",
            "llm_may_recommend",
            "llm_may_analyse",
            "llm_may_compare",
            "llm_may_generate_reports",
            "llm_may_simulate",
        ]
        missing_allow = [k for k in allowed if not LLM_BOUNDARY.get(k)]
        ok = len(violations) == 0 and len(missing_allow) == 0
        return self._record(
            "llm_authority_boundaries",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {"violations": violations, "missing_allow": missing_allow, "boundary": LLM_BOUNDARY},
        )

    def check_environment_separation(self) -> dict[str, Any]:
        flags = {
            "live_trading_authorized": LIVE_TRADING_AUTHORIZED,
            "live_order_capable": LIVE_ORDER_CAPABLE,
            "real_broker_connection_capable": REAL_BROKER_CONNECTION_CAPABLE,
            "exchange_auth_capable": EXCHANGE_AUTH_CAPABLE,
            "oauth_capable": OAUTH_CAPABLE,
            "production_deploy_capable": PRODUCTION_DEPLOY_CAPABLE,
            "paper_only": PAPER_POSTURE["paper_only"],
            "sandbox_only": PAPER_POSTURE["sandbox_only"],
        }
        ok = (
            flags["live_trading_authorized"] is False
            and flags["live_order_capable"] is False
            and flags["real_broker_connection_capable"] is False
            and flags["exchange_auth_capable"] is False
            and flags["oauth_capable"] is False
            and flags["production_deploy_capable"] is False
            and flags["paper_only"] is True
            and flags["sandbox_only"] is True
        )
        return self._record(
            "environment_separation",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            flags,
        )

    def check_sandbox_separation(self) -> dict[str, Any]:
        # Emulator is only executable surface
        sess = self.emulator.create_session()
        order = self.emulator.place_order(
            sess["id"], symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        # Catalog adapters refuse connect
        refused = self.registry.refuse_connect("catalog.coinbase")
        ok = (
            order["simulated"] is True
            and order["live_order"] is False
            and refused["ok"] is False
            and sess["real_network"] is False
        )
        return self._record(
            "sandbox_separation",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {
                "emulator_simulated": order["simulated"],
                "live_order": order["live_order"],
                "catalog_connect_refused": not refused["ok"],
                "real_network": sess["real_network"],
            },
        )

    def check_no_approval_bypass(self) -> dict[str, Any]:
        pipe = self.trust.create_pipeline("catalog.bybit", created_by="security-test")
        # Try to claim full approval without stages
        gate = self.trust.require_all_stages(pipe["id"])
        ok = gate["allowed_sandbox"] is False and gate["allowed_live"] is False
        return self._record(
            "no_approval_bypass",
            SecurityCheckResult.PASS if ok else SecurityCheckResult.FAIL,
            {"gate": gate},
        )

    def run_all(self) -> dict[str, Any]:
        checks = [
            self.check_broker_isolation(),
            self.check_credential_isolation(),
            self.check_approval_isolation(),
            self.check_audit_integrity(),
            self.check_llm_authority_boundaries(),
            self.check_environment_separation(),
            self.check_sandbox_separation(),
            self.check_no_approval_bypass(),
        ]
        passed = all(c["passed"] for c in checks)
        return {
            "milestone": "M222",
            "checks": checks,
            "total": len(checks),
            "passed_count": sum(1 for c in checks if c["passed"]),
            "all_passed": passed,
            "paper_only": True,
            "live_trading_authorized": False,
        }

    def list_checks(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.store.fetchall(
            "SELECT * FROM bs_security_checks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "check_name": r["check_name"],
                "result": r["result"],
                "detail": json.loads(r["detail_json"] or "{}"),
                "created_at": r["created_at"],
            })
        return out


__all__ = ["SecurityValidator"]
