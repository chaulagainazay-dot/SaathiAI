"""M227 — Permission-Scope Validation and Least Privilege.

Provider-independent scope validation. Fail closed on excess, mismatch, write, unknown.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    ALLOWED_SCOPES,
    FORBIDDEN_SCOPES,
    ScopeOutcome,
)
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid


def normalize_scope(scope: str) -> str:
    return scope.strip().upper().replace(":", "_").replace(".", "_").replace("-", "_").replace(" ", "_")


class ScopeValidator:
    def __init__(self, store: ReadinessStore):
        self.store = store

    def validate(
        self,
        *,
        requested: list[str] | None = None,
        declared: list[str] | None = None,
        provider_reported: list[str] | None = None,
        approved: list[str] | None = None,
        credential_id: str = "",
    ) -> dict[str, Any]:
        requested = [normalize_scope(s) for s in (requested or [])]
        declared = [normalize_scope(s) for s in (declared or [])]
        provider_reported = [normalize_scope(s) for s in (provider_reported or [])]
        approved = [normalize_scope(s) for s in (approved or requested or declared)]

        reasons: list[str] = []
        outcome = ScopeOutcome.LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION

        # Unknown scopes
        for s in set(requested + declared + provider_reported + approved):
            if s not in ALLOWED_SCOPES and s not in FORBIDDEN_SCOPES:
                outcome = ScopeOutcome.UNKNOWN_SCOPE_REJECTED
                reasons.append(f"unknown scope: {s}")
                return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id)

        # Write / forbidden
        all_scopes = set(requested + declared + provider_reported + approved)
        write_hits = sorted(all_scopes & FORBIDDEN_SCOPES)
        if write_hits:
            outcome = ScopeOutcome.WRITE_PERMISSION_REJECTED
            reasons.append(f"write scopes present: {write_hits}")
            # Mixed: reject entirely, no silent downgrade
            return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id)

        # Excess: requested beyond approved
        req_set, appr_set = set(requested), set(approved)
        excess = sorted(req_set - appr_set) if appr_set else []
        if excess:
            outcome = ScopeOutcome.EXCESS_SCOPE_REJECTED
            reasons.append(f"requested exceeds approved: {excess}")
            return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id)

        # Mismatch: declared vs provider vs approved
        if declared and provider_reported and set(declared) != set(provider_reported):
            outcome = ScopeOutcome.SCOPE_MISMATCH_REJECTED
            reasons.append("declared scopes != provider-reported scopes")
            return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id)

        if approved and declared and not set(declared).issubset(set(approved)):
            outcome = ScopeOutcome.SCOPE_MISMATCH_REJECTED
            reasons.append("declared scopes not subset of approved")
            return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id)

        # Effective = intersection of all non-empty sets (least privilege)
        sets = [s for s in [set(requested), set(declared), set(provider_reported), set(approved)] if s]
        effective = sorted(set.intersection(*sets)) if sets else []
        if not effective and (requested or declared or approved):
            # empty intersection is a mismatch
            outcome = ScopeOutcome.SCOPE_MISMATCH_REJECTED
            reasons.append("empty effective scope intersection")
            return self._finish(outcome, requested, declared, provider_reported, approved, reasons, credential_id, effective)

        reasons.append("least privilege confirmed in simulation")
        return self._finish(
            ScopeOutcome.LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION,
            requested, declared, provider_reported, approved, reasons, credential_id, effective,
        )

    def _finish(
        self,
        outcome: ScopeOutcome,
        requested: list[str],
        declared: list[str],
        provider_reported: list[str],
        approved: list[str],
        reasons: list[str],
        credential_id: str,
        effective: list[str] | None = None,
    ) -> dict[str, Any]:
        effective = effective if effective is not None else []
        diff = {
            "requested_not_in_approved": sorted(set(requested) - set(approved)),
            "declared_not_in_approved": sorted(set(declared) - set(approved)),
            "provider_not_in_declared": sorted(set(provider_reported) - set(declared)),
            "approved_not_in_declared": sorted(set(approved) - set(declared)),
            "write_scopes": sorted((set(requested) | set(declared) | set(provider_reported) | set(approved)) & FORBIDDEN_SCOPES),
            "unknown_scopes": sorted(
                s for s in (set(requested) | set(declared) | set(provider_reported) | set(approved))
                if s not in ALLOWED_SCOPES and s not in FORBIDDEN_SCOPES
            ),
        }
        ok = outcome == ScopeOutcome.LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION
        rid = _uid("scope")
        self.store.execute(
            """INSERT INTO br_scope_reviews(
                id, credential_id, requested_json, declared_json, provider_json,
                approved_json, effective_json, outcome, diff_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                rid, credential_id,
                json.dumps(requested), json.dumps(declared), json.dumps(provider_reported),
                json.dumps(approved), json.dumps(effective), outcome.value,
                json.dumps(diff), time.time(),
            ),
        )
        self.store.audit("scope.validate", subject=credential_id or rid, detail={
            "outcome": outcome.value, "ok": ok,
        })
        return {
            "review_id": rid,
            "outcome": outcome.value,
            "ok": ok,
            "requested": requested,
            "declared": declared,
            "provider_reported": provider_reported,
            "approved": approved,
            "effective": effective if ok else [],
            "scope_diff": diff,
            "reasons": reasons,
            "fail_closed": not ok,
            "simulation_only": True,
        }


__all__ = ["ScopeValidator", "normalize_scope"]
