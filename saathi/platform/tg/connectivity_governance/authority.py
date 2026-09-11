"""M313 Connectivity Authority Model — lattice, deny-overrides-allow, no implicit expand."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.connectivity_governance.models import (
    ACCOUNT_READ_CAPABILITIES,
    ACCOUNT_WRITE_CAPABILITIES,
    ALL_CAPABILITIES,
    AUTHORITY_VALUES,
    CREDENTIAL_CAPABILITIES,
    EXECUTION_CAPABILITIES,
    MARKET_DATA_CAPABILITIES,
    MILESTONE_ALLOWED_CAPABILITIES,
    MILESTONE_PROHIBITED_CAPABILITIES,
    AuthorityState,
)


# Authority lattice: each capability is independent; higher domain does not imply lower
# Edge list documents non-implication (source does NOT grant target)
NON_IMPLICATION_EDGES = [
    ("offline_fixture_access", "authenticated_market_data"),
    ("public_unauthenticated_data", "account_metadata"),
    ("authenticated_market_data", "balances"),
    ("balances", "positions"),
    ("positions", "orders"),
    ("orders", "submit_order"),  # order-read does not grant order-write
    ("account_metadata", "submit_order"),
    ("external_paper", "live_execution"),
    ("internal_simulation", "external_paper"),
    ("credential_reference_creation", "credential_use"),
    ("credential_reference_creation", "credential_validation"),
    ("historical_refresh", "real_time_quote_stream"),
    ("fills", "submit_order"),
    ("activity", "transfer"),
]


def domain_for(capability: str) -> str:
    if capability in MARKET_DATA_CAPABILITIES:
        return "market_data"
    if capability in ACCOUNT_READ_CAPABILITIES:
        return "account_read"
    if capability in ACCOUNT_WRITE_CAPABILITIES:
        return "account_write"
    if capability in EXECUTION_CAPABILITIES:
        return "execution"
    if capability in CREDENTIAL_CAPABILITIES:
        return "credential"
    return "unknown"


def default_state_for(capability: str) -> str:
    if capability in MILESTONE_PROHIBITED_CAPABILITIES:
        return AuthorityState.PROHIBITED.value
    if capability == "internal_simulation":
        # Internal paper sim exists elsewhere; not connectivity activation
        return AuthorityState.POLICY_ELIGIBLE.value
    if capability in MILESTONE_ALLOWED_CAPABILITIES:
        return AuthorityState.POLICY_ELIGIBLE.value
    if capability == "public_unauthenticated_data":
        return AuthorityState.APPROVAL_REQUIRED.value
    if capability == "credential_reference_creation":
        return AuthorityState.APPROVAL_REQUIRED.value
    if capability == "credential_revocation":
        return AuthorityState.POLICY_ELIGIBLE.value
    if capability == "account_metadata":
        return AuthorityState.PROHIBITED.value
    return AuthorityState.DENIED.value


def evaluate_authority(
    capability: str,
    *,
    granted: set[str] | None = None,
    denied: set[str] | None = None,
    revoked: set[str] | None = None,
    expired: set[str] | None = None,
    emergency: bool = False,
    approved: set[str] | None = None,
    environment: str = "governance",
    provider: str | None = None,
    account_ref: str | None = None,
    now: float | None = None,
    expiry: float | None = None,
) -> dict[str, Any]:
    """Deterministic authority evaluation. Deny overrides allow. No implicit expand."""
    granted = granted or set()
    denied = denied or set()
    revoked = revoked or set()
    expired = expired or set()
    approved = approved or set()
    now = now if now is not None else time.time()

    if capability not in ALL_CAPABILITIES and capability not in MILESTONE_ALLOWED_CAPABILITIES:
        # unknown capabilities fail closed
        if capability not in ALL_CAPABILITIES:
            return _result(capability, AuthorityState.PROHIBITED, "unknown_capability", emergency)

    if emergency:
        return _result(capability, AuthorityState.EMERGENCY_DISABLED, "emergency_shutdown", emergency)

    if capability in denied:
        return _result(capability, AuthorityState.DENIED, "explicit_deny", emergency)

    if capability in revoked:
        return _result(capability, AuthorityState.REVOKED, "revoked", emergency)

    if capability in expired or (expiry is not None and now > expiry):
        return _result(capability, AuthorityState.EXPIRED, "expired", emergency)

    base = default_state_for(capability)
    if base == AuthorityState.PROHIBITED.value:
        return _result(capability, AuthorityState.PROHIBITED, "milestone_prohibited", emergency)

    # Approval existence does not grant activation
    if capability in approved and capability not in granted:
        return _result(
            capability, AuthorityState.APPROVED_NOT_ACTIVE,
            "approved_not_active", emergency,
            notes="approval_does_not_equal_activation",
        )

    if capability in granted:
        # Still cannot activate connectivity authorities in this milestone
        if capability in MILESTONE_PROHIBITED_CAPABILITIES:
            return _result(capability, AuthorityState.PROHIBITED, "cannot_activate_prohibited", emergency)
        return _result(capability, AuthorityState.ACTIVE_BOUNDED, "explicit_grant", emergency)

    if base == AuthorityState.POLICY_ELIGIBLE.value:
        return _result(capability, AuthorityState.POLICY_ELIGIBLE, "policy_eligible", emergency)

    if base == AuthorityState.APPROVAL_REQUIRED.value:
        return _result(capability, AuthorityState.APPROVAL_REQUIRED, "approval_required", emergency)

    return _result(capability, AuthorityState.DENIED, "default_deny", emergency)


def _result(capability: str, state: AuthorityState, reason: str, emergency: bool, **extra) -> dict[str, Any]:
    return {
        "ok": True,
        "capability": capability,
        "domain": domain_for(capability),
        "state": state.value if isinstance(state, AuthorityState) else state,
        "reason": reason,
        "emergency": emergency,
        "activates_connectivity": False,
        "authority_does_not_implicitly_expand": True,
        "deny_overrides_allow": True,
        **extra,
        **{k: AUTHORITY_VALUES[k] for k in (
            "LIVE_TRADING_AUTHORIZED", "ORDER_SUBMISSION_AUTHORIZED",
            "CANARY_ACTIVATION_AUTHORIZED", "REAL_CONNECTIVITY_AUTHORIZED",
        )},
    }


def authority_matrix() -> dict[str, Any]:
    rows = []
    for cap in ALL_CAPABILITIES:
        ev = evaluate_authority(cap)
        rows.append({
            "capability": cap,
            "domain": ev["domain"],
            "default_state": ev["state"],
            "reason": ev["reason"],
        })
    return {
        "ok": True,
        "authority_does_not_implicitly_expand": True,
        "deny_overrides_allow": True,
        "non_implication_edges": [
            {"from": a, "to": b, "implies": False} for a, b in NON_IMPLICATION_EDGES
        ],
        "capabilities": rows,
        "domains": {
            "market_data": list(MARKET_DATA_CAPABILITIES),
            "account_read": list(ACCOUNT_READ_CAPABILITIES),
            "account_write": list(ACCOUNT_WRITE_CAPABILITIES),
            "execution": list(EXECUTION_CAPABILITIES),
            "credential": list(CREDENTIAL_CAPABILITIES),
        },
        **AUTHORITY_VALUES,
    }


def prove_no_implicit_expansion() -> dict[str, Any]:
    """Prove grant of source does not grant target for all non-implication edges."""
    proofs = []
    for src, tgt in NON_IMPLICATION_EDGES:
        src_ev = evaluate_authority(src, granted={src})
        tgt_ev = evaluate_authority(tgt, granted={src})  # only src granted
        expanded = tgt_ev["state"] in (
            AuthorityState.ACTIVE_BOUNDED.value,
            AuthorityState.APPROVED_NOT_ACTIVE.value,
        ) and tgt in {src}
        # target should NOT become ACTIVE from source grant alone
        leak = tgt_ev["state"] == AuthorityState.ACTIVE_BOUNDED.value and tgt != src
        proofs.append({
            "source": src,
            "target": tgt,
            "source_state": src_ev["state"],
            "target_state_with_source_grant_only": tgt_ev["state"],
            "implicit_expansion": leak,
        })
    any_leak = any(p["implicit_expansion"] for p in proofs)
    return {
        "ok": not any_leak,
        "authority_does_not_implicitly_expand": not any_leak,
        "proofs": proofs,
        "count": len(proofs),
    }


def prove_deny_overrides_allow() -> dict[str, Any]:
    cap = "offline_fixture_access"
    allow = evaluate_authority(cap, granted={cap})
    deny = evaluate_authority(cap, granted={cap}, denied={cap})
    return {
        "ok": deny["state"] == AuthorityState.DENIED.value,
        "granted_state": allow["state"],
        "granted_and_denied_state": deny["state"],
        "deny_overrides_allow": deny["state"] == AuthorityState.DENIED.value,
    }


def prove_emergency_override() -> dict[str, Any]:
    cap = "offline_fixture_access"
    normal = evaluate_authority(cap, granted={cap})
    em = evaluate_authority(cap, granted={cap}, emergency=True)
    return {
        "ok": em["state"] == AuthorityState.EMERGENCY_DISABLED.value,
        "normal_state": normal["state"],
        "emergency_state": em["state"],
        "emergency_dominates": em["state"] == AuthorityState.EMERGENCY_DISABLED.value,
    }


def prove_expiry() -> dict[str, Any]:
    cap = "offline_fixture_access"
    past = evaluate_authority(cap, granted={cap}, now=2000.0, expiry=1000.0)
    future = evaluate_authority(cap, granted={cap}, now=1000.0, expiry=2000.0)
    return {
        "ok": past["state"] == AuthorityState.EXPIRED.value,
        "expired_state": past["state"],
        "valid_state": future["state"],
    }


def prove_revocation() -> dict[str, Any]:
    cap = "offline_fixture_access"
    rev = evaluate_authority(cap, granted={cap}, revoked={cap})
    return {
        "ok": rev["state"] == AuthorityState.REVOKED.value,
        "state": rev["state"],
    }


def authority_model_export() -> dict[str, Any]:
    return {
        "schema": "M313_CONNECTIVITY_AUTHORITY_MODEL",
        "matrix": authority_matrix(),
        "no_implicit_expansion": prove_no_implicit_expansion(),
        "deny_overrides_allow": prove_deny_overrides_allow(),
        "expiry": prove_expiry(),
        "revocation": prove_revocation(),
        "emergency_override": prove_emergency_override(),
        "states": [s.value for s in AuthorityState],
        **AUTHORITY_VALUES,
    }
