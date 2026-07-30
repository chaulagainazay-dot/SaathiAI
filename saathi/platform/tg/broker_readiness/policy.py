"""M225 — Read-Only Capability Policy Engine.

Determines whether a requested provider operation is theoretically acceptable
for a future read-only connection. Simulation only. Fail closed.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    ADAPTER_OPERATIONS,
    ALLOWED_ADAPTER_AUTHORITIES,
    AuthorityClass,
    FORBIDDEN_PERMISSION_KEYWORDS,
    FORBIDDEN_SCOPES,
    PolicyDecision,
)
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid


class PolicyEngine:
    def __init__(self, store: ReadinessStore):
        self.store = store

    def evaluate(
        self,
        operation: str,
        *,
        scopes: list[str] | None = None,
        permissions: list[str] | None = None,
        environment: str = "SIMULATION",
        account_type: str = "SIMULATED_READ_ONLY",
        approval_state: str = "UNAPPROVED",
        owner_signoff: bool = False,
        session_state: str = "NOT_CONFIGURED",
        expired: bool = False,
        revoked: bool = False,
        ip_restriction_ok: bool = True,
        withdrawal_permission: bool = False,
        trading_permission: bool = False,
        administrative_permission: bool = False,
        production_authority: bool = False,
        live_trading_authority: bool = False,
        real_connection_requested: bool = False,
        provider_capability: str | None = None,
    ) -> dict[str, Any]:
        scopes = list(scopes or [])
        permissions = list(permissions or [])
        reasons: list[str] = []
        decision = PolicyDecision.ALLOW_SIMULATION_ONLY

        def deny(d: PolicyDecision, reason: str) -> dict[str, Any]:
            return self._record(operation, d, {
                "reasons": reasons + [reason],
                "scopes": scopes,
                "permissions": permissions,
                "environment": environment,
            })

        # Real connection always denied
        if real_connection_requested:
            return deny(PolicyDecision.DENY_REAL_CONNECTION, "real connection requested")

        if production_authority or live_trading_authority:
            return deny(PolicyDecision.DENY_REAL_CONNECTION, "production/live authority claimed")

        if environment.upper() not in ("SIMULATION", "SANDBOX", "PAPER", "LOCAL"):
            return deny(PolicyDecision.DENY_WRONG_ENVIRONMENT, f"environment={environment}")

        if expired:
            return deny(PolicyDecision.DENY_EXPIRED, "credential expired")

        if revoked:
            return deny(PolicyDecision.DENY_REVOKED, "credential revoked")

        if withdrawal_permission or trading_permission or administrative_permission:
            return deny(
                PolicyDecision.DENY_EXCESS_PERMISSION,
                "write/admin/trading/withdrawal permission present",
            )

        # Forbidden scopes
        for s in scopes:
            su = s.upper().replace(":", "_").replace(".", "_").replace("-", "_")
            if su in FORBIDDEN_SCOPES or any(
                k in s.lower() for k in ("order_create", "withdraw", "trading", "transfer", "admin")
            ):
                return deny(PolicyDecision.DENY_WRITE_SCOPE, f"forbidden scope {s}")

        # Mixed read/write: any write keyword in permissions rejects entirely
        for p in permissions:
            pl = p.lower().replace("_", " ").replace("-", " ")
            for kw in FORBIDDEN_PERMISSION_KEYWORDS:
                if kw in pl or kw.replace(" ", "_") in p.lower():
                    return deny(
                        PolicyDecision.DENY_EXCESS_PERMISSION,
                        f"permission set contains forbidden '{kw}' — no silent downgrade",
                    )

        # Operation authority
        auth = ADAPTER_OPERATIONS.get(operation)
        if auth is None and provider_capability is None:
            return deny(PolicyDecision.DENY_UNKNOWN_CAPABILITY, f"unknown operation {operation}")
        if auth is not None and auth not in ALLOWED_ADAPTER_AUTHORITIES:
            return deny(PolicyDecision.DENY_WRITE_SCOPE, f"operation authority {auth.value}")

        if auth is not None and auth in (
            AuthorityClass.TRADING_WRITE,
            AuthorityClass.TRANSFER_WRITE,
            AuthorityClass.ADMINISTRATIVE_WRITE,
            AuthorityClass.FORBIDDEN,
        ):
            return deny(PolicyDecision.DENY_WRITE_SCOPE, "write/forbidden authority class")

        # Approval
        if approval_state.upper() not in (
            "APPROVED", "APPROVED_FOR_SIMULATION", "READINESS_APPROVED", "SIMULATION_APPROVED",
        ):
            # Still allow pure simulation evaluation with unapproved flag
            if approval_state.upper() in ("UNAPPROVED", "", "PENDING"):
                if operation in ADAPTER_OPERATIONS and ADAPTER_OPERATIONS[operation] in ALLOWED_ADAPTER_AUTHORITIES:
                    # Simulation-only without connection readiness
                    decision = PolicyDecision.ALLOW_SIMULATION_ONLY
                    reasons.append("unapproved: simulation evaluation only")
                else:
                    return deny(PolicyDecision.DENY_UNAPPROVED, "not approved")
            else:
                return deny(PolicyDecision.DENY_UNAPPROVED, f"approval_state={approval_state}")
        else:
            if owner_signoff:
                decision = PolicyDecision.READINESS_APPROVED_NOT_CONNECTED
                reasons.append("approved for readiness simulation; not connected")
            else:
                decision = PolicyDecision.ALLOW_SIMULATION_ONLY
                reasons.append("approved metadata without owner sign-off claim")

        if not ip_restriction_ok:
            return deny(PolicyDecision.FAIL_CLOSED, "IP restriction mismatch")

        if session_state in ("SIMULATED_REVOKED", "SIMULATED_FAILED_SAFE", "REAL_CONNECTION_FORBIDDEN"):
            return deny(PolicyDecision.FAIL_CLOSED, f"session_state={session_state}")

        return self._record(operation, decision, {
            "reasons": reasons or ["ok for simulation"],
            "scopes": scopes,
            "permissions": permissions,
            "environment": environment,
            "account_type": account_type,
            "approval_state": approval_state,
            "owner_signoff": owner_signoff,
            "connected": False,
            "simulation_only": True,
        })

    def _record(self, operation: str, decision: PolicyDecision, detail: dict[str, Any]) -> dict[str, Any]:
        eid = _uid("pol")
        self.store.execute(
            """INSERT INTO br_policy_evals(id, operation, decision, input_json, detail_json, created_at)
               VALUES(?,?,?,?,?,?)""",
            (eid, operation, decision.value, json.dumps(detail), json.dumps(detail), time.time()),
        )
        self.store.audit("policy.evaluate", subject=operation, detail={
            "decision": decision.value, "eval_id": eid,
        })
        return {
            "eval_id": eid,
            "operation": operation,
            "decision": decision.value,
            "allowed": decision in (
                PolicyDecision.ALLOW_SIMULATION_ONLY,
                PolicyDecision.READINESS_APPROVED_NOT_CONNECTED,
            ),
            "connected": False,
            "detail": detail,
            "simulation_only": True,
            "paper_only": True,
        }

    def reject_write_permission_set(self, permissions: list[str]) -> dict[str, Any]:
        return self.evaluate(
            "place_order",
            permissions=permissions,
            scopes=["ORDER_CREATE"],
            approval_state="APPROVED",
            owner_signoff=True,
        )


__all__ = ["PolicyEngine"]
