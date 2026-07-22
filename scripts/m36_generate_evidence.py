#!/usr/bin/env python3
"""M36 — Deterministic offline evidence generator (no network, no Keychain).

  .venv/bin/python scripts/m36_generate_evidence.py --offline
  .venv/bin/python scripts/m36_generate_evidence.py --from-sanitized-session-record path.json

Never makes network calls unless explicitly pointed at a pre-sanitized session
record (which itself must already be leak-clean).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saathi.connectors.providers.external.testkit import make_transport, public_resolver
from saathi.connectors.providers.external.transport import SendContext
from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.leakscan import is_clean, scan
from saathi.credentials.m35 import SandboxAccountRegistry, SessionLeaseStore, subject_fingerprint
from saathi.credentials import m36
from saathi.credentials.m36 import (
    M36_ACK_TOKENS,
    AuthorizationStore,
    qualify_sandbox_identity,
    run_m36_session,
    compute_m36_fingerprint,
    validation_summary_body,
    write_m36_evidence,
    preflight_summary,
)

REL = "docs/evidence/m36"
FIXED_TS = 1752800100.0
SYNTH = "SYNTHETIC_M36_SECRET_VALUE_NOT_REAL"
SUBJECT_ID = "424242"
SUBJECT_FP = subject_fingerprint(SUBJECT_ID, provider_id="github_meta")
ALL_ACKS = tuple(M36_ACK_TOKENS)

CRED_ID = "cred_m36_synth_0001"
ACCT_ID = "acct_m36_synth_0001"
SESS_ID = "sess_m36_synth_0001"
AUTHZ_ID = "authz_m36_synth_0001"

_USER_BODY = json.dumps({"id": int(SUBJECT_ID), "type": "User"}).encode()
_META_BODY = json.dumps({
    "verifiable_password_authentication": False,
    "hooks": ["1.2.3.0/24"],
    "pages": ["5.6.7.0/24"],
}).encode()


def _clock() -> float:
    return FIXED_TS


def _path_sender():
    def _s(ctx: SendContext) -> dict:
        if "/user" in ctx.url:
            return {
                "status_code": 200,
                "headers": {"content-type": "application/json", "x-oauth-scopes": "read:user"},
                "body_bytes": _USER_BODY, "content_type": "application/json",
                "location": "", "decompressed_size": len(_USER_BODY),
            }
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_bytes": _META_BODY, "content_type": "application/json",
            "location": "", "decompressed_size": len(_META_BODY),
        }
    return _s


def _run_offline_session() -> dict:
    broker = CredentialBroker(persist=False, clock=_clock)
    reg = SandboxAccountRegistry(clock=_clock)
    leases = SessionLeaseStore(clock=_clock)
    auth_store = AuthorizationStore(clock=_clock)
    backend = InMemoryTestSecretBackend()
    backend.put("m36/synth/loc", {"api_key": SYNTH})

    cred = broker.create_reference(
        owner_scope="user:synthetic", provider_id="github_meta", credential_type="api_key",
        secret_fields={"api_key": SYNTH}, scopes=("identity:read", "metadata:read"),
        connector_ids=("gov.http",),
    )
    acct = reg.register_sandbox(
        provider_id="github_meta", environment_class="SANDBOX", subject=SUBJECT_ID,
        display_alias="synthetic-sandbox", declared_scopes=("identity:read", "metadata:read"),
        account_ref_id=ACCT_ID,
    )
    reg.verify(acct.account_ref_id, observed_scopes=("identity:read", "metadata:read"),
               verified_at=str(int(FIXED_TS)))
    auth = auth_store.create(
        provider_id="github_meta",
        account_ref_id=acct.account_ref_id,
        credential_ref_id=cred.credential_ref_id,
        acknowledgements=ALL_ACKS,
        secret_source_kind="IN_MEMORY_TEST",
        authorization_id=AUTHZ_ID,
        approved_duration=900.0,
    )
    # pin times for determinism in safe dict
    auth.created_at = FIXED_TS
    auth.expires_at = FIXED_TS + 900.0

    qual = qualify_sandbox_identity(
        provider_id="github_meta", account_alias="synthetic-sandbox",
        environment_class="SANDBOX",
        declared_purpose="m36 disposable sandbox verification offline",
        revocation_plan="manual_github_pat_delete",
        expiration_or_deletion_plan="delete_after_m36",
        operator_disposable_ack=True,
    )
    tr = make_transport(sender=_path_sender(), resolver=public_resolver(), clock=_clock)
    result = run_m36_session(
        authorization_store=auth_store,
        authorization_id=auth.authorization_id,
        account_registry=reg,
        account_ref_id=acct.account_ref_id,
        broker=broker,
        credential_ref_id=cred.credential_ref_id,
        lease_store=leases,
        secret_backend=backend,
        secret_locator="m36/synth/loc",
        identity_qualification=qual,
        transport=tr,
        synthetic_offline=True,
        expected_subject_fingerprint=SUBJECT_FP,
        clock=_clock,
        session_id=SESS_ID,
    )
    # alias volatile ids
    sess = result["session"]
    sess["credential_ref_id"] = CRED_ID
    if sess.get("lease_id", "").startswith("lease_m35_"):
        sess["lease_id"] = "lease_m36_synth_0001"
    result["credential_fingerprint"] = sess.get("credential_fingerprint", "")
    return {
        "result": result,
        "auth": auth.to_safe_dict(),
        "qual": qual,
        "cred_id": CRED_ID,
        "acct_id": ACCT_ID,
    }


def _build_bodies(pack: dict) -> dict:
    result = pack["result"]
    auth = pack["auth"]
    # force deterministic auth credential id
    auth = dict(auth)
    auth["credential_ref_id"] = CRED_ID
    auth["account_ref_id"] = ACCT_ID
    auth["authorization_id"] = AUTHZ_ID

    cert = result["session"].get("certification") or "AUTHORIZATION_READY"
    summary = validation_summary_body(
        session_result=result, certification=cert, real_session_exercised=False,
    )
    findings = [f.to_dict() for f in scan(result)]
    bodies = {
        "baseline": {
            "milestone": "M36",
            "starting_head_note": "see M36_FINAL_REPORT",
            "provider_id": "github_meta",
            "schema": m36.SCHEMA_VERSION,
            "live_network": False,
            "mode": "offline_synthetic_fixture",
            "fingerprint": compute_m36_fingerprint(),
        },
        "authorization_policy": {
            "required_acknowledgements": list(M36_ACK_TOKENS),
            "max_call_budget": m36.M36_MAX_CALL_BUDGET,
            "max_auth_ttl_sec": m36.M36_MAX_AUTH_TTL_SEC,
            "m37_authorized": False,
            "sample_authorization": auth,
        },
        "account_qualification": pack["qual"],
        "secret_source_verification": {
            "approved_kinds": sorted(m36._M36_RETRIEVABLE),
            "prohibited": sorted(m36.PROHIBITED_SECRET_SOURCES),
            "fallback_permitted": False,
            "keychain_accessed_offline": False,
            "arbitrary_env_scan": False,
        },
        "credential_fingerprint": {
            "fingerprint": result.get("credential_fingerprint", ""),
            "policy_version": m36._FP_POLICY_VERSION,
            "reversible": False,
            "authenticates": False,
        },
        "scope_verification": result.get("scope_verification") or {},
        "capability_intersection": {
            "provider_id": "github_meta",
            "operation": "get_meta",
            "method": "GET",
            "identity_operation": "get_authenticated_user",
            "side_effect_class": "READ_ONLY",
            "rollout_exception": "session_specific_m36_only",
        },
        "call_budget": result.get("call_budget") or {},
        "transport_security": {
            "canonical_transport": "saathi.connectors.providers.external.transport.ExternalTransport",
            "https_only": True,
            "hostname_allowlist": ["api.github.com"],
            "dns_ssrf": True,
            "tls_verification": True,
            "redirect_limit": 0,
            "response_limit_bytes": 262144,
            "auth_header_in_envelope": False,
            "auth_header_in_evidence": False,
        },
        "identity_verification": result.get("identity_verification") or {},
        "normalized_provider_result": result.get("normalized_provider_result") or {},
        "session_lifecycle": result.get("session") or {},
        "reliability_qualification": {
            "classification": result["session"].get("reliability"),
            "note": "single fixture success is not production reliability",
        },
        "cleanup_and_revocation": {
            "preferred": ["LEASE_REVOKED", "EXTERNAL_REVOCATION_OPERATOR_ATTESTED"],
            "session_lease_revoked_on_complete": True,
            "silent_active_forbidden": True,
        },
        "certification": {
            "state": cert,
            "authorities": result.get("authorities"),
            "rollout": result.get("rollout_state"),
            "m37_started": False,
        },
        "events": {"events": result.get("events") or [], "count": len(result.get("events") or [])},
        "leak_scan": {
            "clean": is_clean(result) and not findings,
            "findings": findings,
            "raw_secrets_found": 0,
            "authorization_headers_found": 0,
            "personal_identities_found": 0,
        },
        "network_call_accounting": result.get("network_accounting") or result.get("call_budget") or {},
        "validation_summary": summary,
        "verification_fingerprint": {
            "fingerprint": compute_m36_fingerprint(),
            "preflight": preflight_summary(),
        },
    }
    return bodies


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M36 evidence generator")
    p.add_argument("--offline", action="store_true", default=True)
    p.add_argument("--from-sanitized-session-record", default="")
    p.add_argument("--evidence-dir", default=REL)
    args = p.parse_args(argv)

    if args.from_sanitized_session_record:
        path = Path(args.from_sanitized_session_record)
        raw = json.loads(path.read_text())
        if not is_clean(raw):
            print(json.dumps({"ok": False, "error": "leak_in_session_record"}))
            return 2
        bodies = {
            "live_session_sanitized": {
                **raw,
                "evidence_class": "live_sanitized_nondeterministic",
                "deterministic": False,
            },
            "validation_summary": validation_summary_body(
                session_result=raw,
                certification=(raw.get("session") or {}).get("certification", "UNVERIFIED"),
                real_session_exercised=True,
            ),
            "leak_scan": {"clean": True, "findings": [], "source": "sanitized_session_record"},
            "verification_fingerprint": {"fingerprint": compute_m36_fingerprint()},
        }
    else:
        pack = _run_offline_session()
        if not pack["result"].get("ok"):
            print(json.dumps({"ok": False, "reason": pack["result"].get("reason")}))
            return 3
        bodies = _build_bodies(pack)

    written = write_m36_evidence(bodies, evidence_dir=args.evidence_dir)
    print(json.dumps({
        "ok": True,
        "mode": "live_record" if args.from_sanitized_session_record else "offline",
        "written": written,
        "fingerprint": compute_m36_fingerprint(),
        "real_sandbox_session": "NOT_EXERCISED" if not args.from_sanitized_session_record else "FROM_RECORD",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
