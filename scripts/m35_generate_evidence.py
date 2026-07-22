"""M35 — Deterministic sandbox-credential governance evidence generator.

Exercises the M35 governance surface entirely OFFLINE with synthetic fixtures:
no network, no real secret source, no OS keychain, no real environment secret,
no account connection, no provider call. Every payload is leak-scanned before it
is written (fail-closed, via M32 ``write_evidence``). Volatile ids are aliased to
canonical synthetic ids so the evidence is byte-deterministic across runs.

Run:  .venv/bin/python scripts/m35_generate_evidence.py
"""
from __future__ import annotations

from pathlib import Path

from saathi.credentials import m35
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.leakscan import is_clean
from saathi.connectors.providers.external.profiles import resolve_external_profile

ROOT = Path(__file__).resolve().parents[1]
REL = "docs/evidence/m35"
FIXED_TS = 1752800000.0
PROVIDER = "github_meta"
SYNTH = "SYNTHETIC_SECRET_VALUE"
PROFILE = resolve_external_profile(PROVIDER)

# canonical synthetic ids for deterministic evidence
CRED_ID = "cred_m35_synth_0001"
ACCT_ID = "acct_m35_synth_0001"
SESS_ID = "sess_m35_synth_0001"
APPR_ID = "appr_m35_synth_0001"


def _clock() -> float:
    return FIXED_TS


def _run_session() -> dict:
    broker = CredentialBroker(persist=False, clock=_clock)
    registry = m35.SandboxAccountRegistry(clock=_clock)
    leases = m35.SessionLeaseStore(clock=_clock)

    cred = broker.create_reference(
        owner_scope="user:synthetic", provider_id=PROVIDER, credential_type="api_key",
        secret_fields={"api_key": SYNTH}, scopes=("metadata:read",), connector_ids=("gov.http",),
    )
    acct = registry.register_sandbox(
        provider_id=PROVIDER, environment_class="SANDBOX", subject="SYNTHETIC_ACCOUNT_SUBJECT",
        display_alias="synthetic-sandbox", declared_scopes=("metadata:read",),
        account_ref_id=ACCT_ID,
    )
    registry.verify(acct.account_ref_id, observed_scopes=("metadata:read",), verified_at=str(int(FIXED_TS)))
    approval = m35.build_approval(
        purpose="m35_sandbox_governance_verification", provider_id=PROVIDER,
        account_ref_id=acct.account_ref_id, credential_ref_id=cred.credential_ref_id,
        operation="get_meta", environment_class="SANDBOX", approved_scopes=("metadata:read",),
        read_only_acknowledged=True, sandbox_acknowledged=True, secret_access_acknowledged=True,
        non_production_acknowledged=True, write_prohibited=True, created_at=str(int(FIXED_TS)),
        approval_id=APPR_ID,
    )
    result = m35.run_sandbox_session(
        provider_id=PROVIDER, profile=PROFILE, account_registry=registry,
        account_ref_id=acct.account_ref_id, broker=broker, credential_ref_id=cred.credential_ref_id,
        approval=approval, lease_store=leases, environment_class="SANDBOX",
        requested_scopes=("metadata:read",), observed_scopes=("metadata:read",),
        synthetic=True, session_id=SESS_ID, clock=_clock,
    )
    # alias the volatile broker credential id to a canonical synthetic id in
    # every artifact that will be written to deterministic evidence
    alias = {cred.credential_ref_id: CRED_ID}
    sess = result["session"]
    for k in ("credential_ref_id", "lease_id"):
        if sess.get(k) in alias:
            sess[k] = alias[sess[k]]
    if sess.get("lease_id", "").startswith("lease_m35_"):
        sess["lease_id"] = "lease_m35_synth_0001"
    if approval.credential_ref_id in alias:
        approval.credential_ref_id = alias[approval.credential_ref_id]
    return {
        "broker": broker, "registry": registry, "leases": leases,
        "cred": cred, "acct": acct, "approval": approval, "result": result,
    }


def _bodies(ctx: dict) -> dict:
    result = ctx["result"]
    approval = ctx["approval"]
    certification, cert_lims = m35.assess_sandbox_certification(
        governance_ok=result["ok"], synthetic_session_ok=result["ok"],
    )
    ceiling = m35.ceiling_from_profile(PROFILE, environment_class="SANDBOX", allowed_scopes=("metadata:read",))
    cred_drift_fp = m35.credential_drift_fingerprint(
        provider_id=PROVIDER, environment_class="SANDBOX", credential_type="api_key",
        secret_source=m35.SecretSourceKind.IN_MEMORY_TEST.value, scopes=("metadata:read",),
        capability_ceiling=ceiling.to_dict(), account_ref_id=ACCT_ID,
    )
    acct = ctx["acct"]
    health = m35.credential_health(ctx["broker"].get_ref(ctx["cred"].credential_ref_id),
                                   now=FIXED_TS, expires_at=FIXED_TS + 100000.0)
    elig_ok, elig_blockers = m35.compose_session_eligibility(
        production_certified=True, connector_certified=True, provider_simulation_fresh=True,
        external_profile_fresh=True, credential_valid=True, secret_source_ready=True,
        environment_class="SANDBOX", account_verified=True, scope_verified=True, within_ceiling=True,
        credential_healthy=True, lease_valid=True, approval_valid=True, provider_healthy=True,
        quarantined=False, rollout_off=True,
    )

    return {
        "baseline": {
            "milestone": "M35", "provider": PROVIDER, "operation": "get_meta",
            "starting_head": "ff1022d", "environment": "SANDBOX",
            "extends": "M31 credential architecture", "offline": True, "network_calls": 0,
        },
        "credential_reference_schema": {
            "schema": m35.SCHEMA_VERSION,
            "allowed_environment_classes": sorted(m35._ALLOWED_ENVIRONMENTS),
            "forbidden_environment_class": "PRODUCTION",
            "credential_types": ["api_key", "bearer_token", "oauth_token_set", "generic"],
            "never_contains": ["secret_value", "api_key_value", "access_token", "refresh_token",
                               "password", "private_key", "session_cookie", "authorization_header"],
            "fingerprint": "non_reversible_domain_separated_hmac",
        },
        "secret_source_policy": {
            "retrievable": sorted(m35._RETRIEVABLE_SOURCES),
            "structural_only": sorted(s.value for s in m35.SecretSourceKind if s.value not in m35._RETRIEVABLE_SOURCES),
            "prohibited": sorted(m35.PROHIBITED_SECRET_SOURCES),
            "fallback_permitted": False, "automatic_secret_search": False,
            "in_memory_test": m35.validate_secret_source("IN_MEMORY_TEST", want_retrieval=True),
        },
        "sandbox_account_registry": {
            "accounts": ctx["registry"].list_metadata(),
            "identity_protection": "subject_fingerprinted_never_raw",
            "production_link": "fails_closed", "real_accounts_linked": 0,
        },
        "scope_policy": {
            "allowed_classes": sorted(m35.ALLOWED_SCOPE_CLASSES),
            "forbidden_classes": sorted(m35.FORBIDDEN_SCOPE_CLASSES),
            "unknown_fails_closed": True,
            "verification_states": [s.value for s in m35.ScopeVerificationState],
        },
        "capability_ceiling": ceiling.to_dict(),
        "approval_envelope": approval.to_dict(),
        "lease_lifecycle": {
            "default_ttl_seconds": m35.M35_DEFAULT_LEASE_TTL_SEC,
            "max_ttl_seconds": m35.M35_MAX_LEASE_TTL_SEC,
            "default_max_uses": m35.M35_DEFAULT_MAX_USES,
            "states": [s.value for s in m35.SessionLeaseStatus],
            "eligibility_read_consumes_use": False,
        },
        "session_lifecycle": {
            "states": [s.value for s in m35.SessionState],
            "flow": ["authorize", "verify_account", "verify_scope", "issue_lease", "retrieve_secret",
                     "derive_fingerprint", "compose_eligibility", "bounded_session", "release_secret",
                     "consume_lease", "end", "emit_evidence"],
            "external_calls": 0, "writes": 0,
        },
        "secret_handle_security": {
            "non_printable": True, "non_serializable": True, "zeroized_on_close": True,
            "use_after_close": "rejected", "bound_to": ["session", "lease", "provider", "account"],
        },
        "expiry_and_revocation": {
            "expiry": "deterministic_clock_injectable",
            "revocation_targets": ["credential", "account", "lease", "session", "approval", "provider", "operation"],
            "unrelated_identities_unchanged": True, "audit_evidence_preserved": True,
            "rollout_unchanged": True,
        },
        "rotation": {
            "detects": ["same_secret_reuse", "provider_mismatch", "account_mismatch",
                        "environment_mismatch", "scope_broadening", "expired_replacement", "invalid_replacement"],
            "old_leases_invalidated": True, "contacts_provider": False,
        },
        "credential_drift": {
            "fingerprint": cred_drift_fp, "states": [s.value for s in m35.DriftState],
            "eligibility_read_non_mutating": True,
        },
        "account_drift": {
            "fingerprint": acct.drift_fingerprint(),
            "drift_check": ctx["registry"].check_drift(acct.account_ref_id, expected_fingerprint=acct.drift_fingerprint()),
        },
        "credential_health": {
            "current": health, "states": [s.value for s in m35.CredentialHealthState],
            "metadata_only": True, "retrieves_secret": False, "consumes_lease": False,
        },
        "eligibility_composition": {
            "allowed": elig_ok, "blockers": elig_blockers,
            "real_sandbox_session": "blocked", "provider_rollout": "OFF",
        },
        "synthetic_session_result": result,
        "sandbox_certification": {
            "state": certification, "max_state": m35.M35_MAX_CERTIFICATION_STATE,
            "limitations": cert_lims,
            "sandbox_session_certified": False,
            "real_sandbox_credential_verification": "NOT_EXERCISED",
            "real_sandbox_account_link": "NOT_EXERCISED",
            "live_provider_session": "NOT_EXERCISED",
        },
        "events": {"account_events": ctx["registry"]._events, "count": len(ctx["registry"]._events)},
        "leak_scan": {"clean": True, "findings": [], "scanner": "m31.leakscan + m35 defence-in-depth"},
        "verification_fingerprint": {
            "provider_id": PROVIDER, "fingerprint": m35.compute_m35_fingerprint(PROFILE),
            "schema_version": m35.SCHEMA_VERSION,
        },
        "validation_summary": m35.validation_summary_body(session_result=result, certification=certification),
    }


def main() -> int:
    (ROOT / REL).mkdir(parents=True, exist_ok=True)
    ctx = _run_session()
    bodies = _bodies(ctx)

    # fail closed: whole evidence set must be leak-clean before any write
    for name, body in bodies.items():
        if not is_clean(body):
            raise SystemExit(f"ABORT: evidence body '{name}' failed leak scan — nothing written")

    written = m35.write_m35_evidence(bodies, evidence_dir=REL)

    r = ctx["result"]
    print(f"provider              : {PROVIDER}")
    print(f"session ok            : {r['ok']} ({r['session_state']})")
    print(f"credential fingerprint: len={len(r['credential_fingerprint'])} (non-reversible)")
    print(f"handle_closed         : {r['handle_closed']}")
    print(f"certification         : {bodies['sandbox_certification']['state']}")
    print(f"rollout_state         : {r['rollout_state']}")
    print(f"m35 fingerprint       : {bodies['verification_fingerprint']['fingerprint']}")
    print(f"evidence files written: {len(written)}")
    for p in sorted(written):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
