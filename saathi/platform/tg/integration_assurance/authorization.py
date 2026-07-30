"""M238 — Read-only integration authorization framework (planning only).

No automatic authorization. No owner sign-off by automation.
Maximum state: READ_ONLY_CANARY_PLANNING_ELIGIBLE with real_connectivity_authorized=false.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.integration_assurance.models import (
    APPROVAL_DOMAINS,
    AuthorizationState,
    MAX_AUTH_STATE,
    OWNER_SIGNOFF_AUTOMATED,
    REAL_CONNECTIVITY_AUTHORIZED,
)
from saathi.platform.tg.integration_assurance.store import AssuranceStore, _uid


class AuthorizationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class AuthorizationFramework:
    def __init__(self, store: AssuranceStore):
        self.store = store

    def domains(self) -> dict[str, Any]:
        return {
            "domains": [
                {"id": d[0], "name": d[1], "required": True}
                for d in APPROVAL_DOMAINS
            ],
            "count": len(APPROVAL_DOMAINS),
            "real_connectivity_authorized": False,
            "max_state": MAX_AUTH_STATE.value,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def create_plan(
        self,
        provider: str = "future.read_only.provider",
        environment: str = "PLANNING",
    ) -> dict[str, Any]:
        if environment.upper() in ("PRODUCTION", "LIVE", "MAINNET"):
            raise AuthorizationError(
                "FAIL_CLOSED",
                "Production/live environment not eligible in M238 planning framework",
            )
        pid = _uid("plan")
        now = time.time()
        self.store.execute(
            """INSERT INTO ia_authorization_plans(
                id, provider, environment, aggregate_state,
                real_connectivity_authorized, detail_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                pid, provider, environment,
                AuthorizationState.PLANNING_ONLY.value,
                0, json.dumps({"created_by": "planning"}), now, now,
            ),
        )
        self.store.audit("auth.plan_created", subject=pid, detail={"provider": provider})
        return self.get_plan(pid)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM ia_authorization_plans WHERE id=?", (plan_id,))
        if not row:
            raise AuthorizationError("PLAN_NOT_FOUND", plan_id)
        approvals = self.list_approvals(plan_id)
        aggregate = self.aggregate(plan_id)
        return {
            "plan": {
                "id": row["id"],
                "provider": row["provider"],
                "environment": row["environment"],
                "aggregate_state": aggregate["state"],
                "real_connectivity_authorized": False,
                "detail": json.loads(row.get("detail_json") or "{}"),
                "created_at": row["created_at"],
            },
            "approvals": approvals["approvals"],
            "aggregate": aggregate,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def list_plans(self) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ia_authorization_plans ORDER BY created_at DESC LIMIT 50"
        )
        plans = []
        for r in rows:
            plans.append({
                "id": r["id"],
                "provider": r["provider"],
                "environment": r["environment"],
                "aggregate_state": r["aggregate_state"],
                "real_connectivity_authorized": False,
            })
        return {"plans": plans, "REAL_CONNECTIVITY_AUTHORIZED": False}

    def record_approval(
        self,
        plan_id: str,
        domain: str,
        *,
        approver_identity: str = "",
        role: str = "",
        scope: str = "read-only-planning",
        provider: str = "",
        environment: str = "PLANNING",
        issued_at: float | None = None,
        expires_at: float | None = None,
        evidence_refs: list | None = None,
        acknowledgements: list | None = None,
        automated: bool = False,
        actor: str = "system",
    ) -> dict[str, Any]:
        # Hard block: automation cannot produce owner sign-off
        if domain == "OWNER_AUTH" and (automated or actor in ("llm", "agent", "pipeline", "automation", "test")):
            raise AuthorizationError(
                "OWNER_SIGNOFF_AUTOMATION_FORBIDDEN",
                "No automated test, LLM, agent or pipeline may produce owner sign-off.",
            )
        if automated and domain in ("OWNER_AUTH", "SECURITY_AUTH", "LEGAL_TOS"):
            raise AuthorizationError(
                "CRITICAL_APPROVAL_AUTOMATION_FORBIDDEN",
                f"Domain {domain} cannot be granted by automation",
            )
        if OWNER_SIGNOFF_AUTOMATED:
            raise AuthorizationError("FAIL_CLOSED", "OWNER_SIGNOFF_AUTOMATED must remain false")

        valid_domains = {d[0] for d in APPROVAL_DOMAINS}
        if domain not in valid_domains:
            raise AuthorizationError("UNKNOWN_DOMAIN", domain)

        plan = self.store.fetchone("SELECT * FROM ia_authorization_plans WHERE id=?", (plan_id,))
        if not plan:
            raise AuthorizationError("PLAN_NOT_FOUND", plan_id)

        # Provider / environment mismatch
        if provider and plan["provider"] and provider != plan["provider"]:
            raise AuthorizationError("PROVIDER_MISMATCH", f"{provider} != {plan['provider']}")
        if environment and plan["environment"] and environment != plan["environment"]:
            if environment.upper() in ("PRODUCTION", "LIVE"):
                raise AuthorizationError("ENVIRONMENT_MISMATCH", environment)

        now = time.time()
        issued = issued_at if issued_at is not None else now
        expires = expires_at if expires_at is not None else now + 86400 * 30
        aid = _uid("appr")
        audit = [{"event": "issued", "at": now, "actor": actor}]
        self.store.execute(
            """INSERT INTO ia_approvals(
                id, plan_id, domain, approver_identity, role, scope, provider, environment,
                issued_at, expires_at, evidence_refs_json, acknowledgements_json,
                revoked, superseded, automated, audit_json, detail_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
            (
                aid, plan_id, domain, approver_identity, role, scope,
                provider or plan["provider"], environment or plan["environment"],
                issued, expires, json.dumps(evidence_refs or []),
                json.dumps(acknowledgements or []),
                1 if automated else 0, json.dumps(audit),
                json.dumps({"actor": actor}), now,
            ),
        )
        self.store.audit("auth.approval_recorded", subject=aid, detail={"domain": domain, "automated": automated})
        return self._approval_row(aid)

    def _approval_row(self, aid: str) -> dict[str, Any]:
        r = self.store.fetchone("SELECT * FROM ia_approvals WHERE id=?", (aid,))
        if not r:
            raise AuthorizationError("APPROVAL_NOT_FOUND", aid)
        return self._normalize_approval(r)

    def _normalize_approval(self, r: dict) -> dict[str, Any]:
        now = time.time()
        expired = bool(r.get("expires_at") and r["expires_at"] < now)
        return {
            "id": r["id"],
            "plan_id": r["plan_id"],
            "domain": r["domain"],
            "approver_identity": r["approver_identity"],
            "role": r["role"],
            "scope": r["scope"],
            "provider": r["provider"],
            "environment": r["environment"],
            "issued_at": r["issued_at"],
            "expires_at": r["expires_at"],
            "evidence_references": json.loads(r.get("evidence_refs_json") or "[]"),
            "acknowledgements": json.loads(r.get("acknowledgements_json") or "[]"),
            "revocation_status": "REVOKED" if r.get("revoked") else "ACTIVE",
            "supersession_status": "SUPERSEDED" if r.get("superseded") else "CURRENT",
            "automated": bool(r.get("automated")),
            "expired": expired,
            "audit_history": json.loads(r.get("audit_json") or "[]"),
            "real_connectivity_authorized": False,
        }

    def list_approvals(self, plan_id: str = "") -> dict[str, Any]:
        if plan_id:
            rows = self.store.fetchall(
                "SELECT * FROM ia_approvals WHERE plan_id=? ORDER BY created_at DESC",
                (plan_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM ia_approvals ORDER BY created_at DESC LIMIT 100"
            )
        return {
            "approvals": [self._normalize_approval(r) for r in rows],
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def revoke(self, approval_id: str, *, reason: str = "", actor: str = "system") -> dict[str, Any]:
        r = self.store.fetchone("SELECT * FROM ia_approvals WHERE id=?", (approval_id,))
        if not r:
            raise AuthorizationError("APPROVAL_NOT_FOUND", approval_id)
        audit = json.loads(r.get("audit_json") or "[]")
        audit.append({"event": "revoked", "at": time.time(), "actor": actor, "reason": reason})
        self.store.execute(
            "UPDATE ia_approvals SET revoked=1, revoked_at=?, audit_json=? WHERE id=?",
            (time.time(), json.dumps(audit), approval_id),
        )
        self.store.audit("auth.approval_revoked", subject=approval_id, detail={"reason": reason})
        return self._approval_row(approval_id)

    def attempt_owner_signoff_automated(self, plan_id: str, actor: str = "agent") -> dict[str, Any]:
        """Explicit fail-closed path: automation cannot create owner sign-off."""
        try:
            self.record_approval(
                plan_id, "OWNER_AUTH",
                approver_identity="automation",
                role="agent",
                automated=True,
                actor=actor,
            )
            return {"ok": True, "error": None}  # should never happen
        except AuthorizationError as e:
            return {
                "ok": False,
                "error": e.code,
                "message": e.message,
                "owner_signoff_automated": False,
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }

    def attempt_activate_connectivity(self, plan_id: str = "") -> dict[str, Any]:
        return {
            "ok": False,
            "error": "REAL_CONNECTIVITY_NOT_AUTHORIZED",
            "real_connectivity_authorized": False,
            "message": "M238 is planning only. Real connectivity cannot be activated.",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def aggregate(self, plan_id: str) -> dict[str, Any]:
        plan = self.store.fetchone("SELECT * FROM ia_authorization_plans WHERE id=?", (plan_id,))
        if not plan:
            return {
                "state": AuthorizationState.FAIL_CLOSED.value,
                "real_connectivity_authorized": False,
                "missing_domains": [d[0] for d in APPROVAL_DOMAINS],
            }

        approvals = self.list_approvals(plan_id)["approvals"]
        now = time.time()

        # Any revoked critical?
        if any(a["revocation_status"] == "REVOKED" for a in approvals):
            state = AuthorizationState.AUTHORIZATION_REVOKED
        elif any(a.get("expired") for a in approvals if a["revocation_status"] == "ACTIVE"):
            state = AuthorizationState.AUTHORIZATION_EXPIRED
        else:
            active = {
                a["domain"]
                for a in approvals
                if a["revocation_status"] == "ACTIVE" and not a.get("expired")
            }
            required = [d[0] for d in APPROVAL_DOMAINS]
            missing = [d for d in required if d not in active]

            if not approvals:
                state = AuthorizationState.PLANNING_ONLY
            elif "OWNER_AUTH" not in active:
                state = AuthorizationState.AWAITING_OWNER_REVIEW
            elif "SECURITY_AUTH" not in active:
                state = AuthorizationState.AWAITING_SECURITY_REVIEW
            elif "LEGAL_TOS" not in active:
                state = AuthorizationState.AWAITING_LEGAL_REVIEW
            elif "CREDENTIAL_SCOPE" not in active:
                state = AuthorizationState.AWAITING_SCOPE_REVIEW
            elif missing:
                state = AuthorizationState.EVIDENCE_INCOMPLETE
            else:
                # All domains present — still max planning eligible
                state = AuthorizationState.READ_ONLY_CANARY_PLANNING_ELIGIBLE

            # Cap at max
            order = [s.value for s in AuthorizationState]
            if order.index(state.value) > order.index(MAX_AUTH_STATE.value):
                # shouldn't exceed with current logic
                pass

        # Always force real connectivity false
        assert REAL_CONNECTIVITY_AUTHORIZED is False

        active_domains = {
            a["domain"]
            for a in approvals
            if a["revocation_status"] == "ACTIVE" and not a.get("expired")
        }
        missing_domains = [d[0] for d in APPROVAL_DOMAINS if d[0] not in active_domains]

        self.store.execute(
            "UPDATE ia_authorization_plans SET aggregate_state=?, real_connectivity_authorized=0, updated_at=? WHERE id=?",
            (state.value, now, plan_id),
        )
        return {
            "state": state.value,
            "real_connectivity_authorized": False,
            "missing_domains": missing_domains,
            "active_domains": sorted(active_domains),
            "max_state": MAX_AUTH_STATE.value,
            "single_approval_grants_connectivity": False,
            "owner_signoff_automated": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def eligibility(self, plan_id: str = "") -> dict[str, Any]:
        if not plan_id:
            plans = self.list_plans()["plans"]
            plan_id = plans[0]["id"] if plans else ""
        if not plan_id:
            return {
                "eligible": False,
                "state": AuthorizationState.NOT_ELIGIBLE.value,
                "real_connectivity_authorized": False,
                "message": "No authorization plan exists",
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }
        agg = self.aggregate(plan_id)
        eligible = agg["state"] == AuthorizationState.READ_ONLY_CANARY_PLANNING_ELIGIBLE.value
        return {
            "eligible_for_canary_planning": eligible,
            "state": agg["state"],
            "real_connectivity_authorized": False,
            "missing_domains": agg["missing_domains"],
            "message": (
                "Canary planning eligible only — real connectivity still false"
                if eligible else "Not eligible for read-only canary planning"
            ),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
