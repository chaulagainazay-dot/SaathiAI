"""M31 — Credential control-plane CLI.

    python -m saathi.credentials <command>

Commands:
    status                     broker + account-link status (metadata only)
    readiness                  broker readiness probe
    profiles                   list auth profiles + scope governance
    list-credentials           list credential references (no values)
    list-links                 list account links (no values)
    inspect-credential <id>    one credential reference (no values)
    inspect-link <id>          one account link (no values)
    demo                       run a full deterministic fake-provider lifecycle
    emit-evidence              run demo + write leak-scanned evidence pack
    verify                     assert M31 invariants (0 real creds/oauth/links)
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from saathi.credentials import evidence, leakscan
from saathi.credentials.account_links import AccountLinkRegistry
from saathi.credentials.broker import CredentialBroker, get_broker
from saathi.credentials.oauth import OAuthLifecycle
from saathi.credentials.scopes import list_profiles
from saathi.credentials.testing.sandbox_oauth import FakeOAuthProvider


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


_M35_BANNER = (
    "SANDBOX GOVERNANCE\nNON-PRODUCTION\nNO LIVE SECRET LOADED\n"
    "NO EXTERNAL CALL\nNO WRITE AUTHORITY\nROLLOUT REMAINS OFF"
)

_M36_BANNER = (
    "REAL SANDBOX VERIFICATION\nNON-PRODUCTION\nREAD-ONLY\nBOUNDED SESSION\n"
    "ROLLOUT OFF\nNO CANARY\nNO ACTIVE\nTRADING GUARDIAN UNENGAGED"
)

_M37_BANNER = (
    "M37 SECURITY CERTIFICATION\nNON-PRODUCTION\nREAD-ONLY\nBOUNDED SANDBOX\n"
    "ROLLOUT OFF\nNO CANARY\nNO ACTIVE\nTRADING GUARDIAN UNENGAGED"
)

_M38_BANNER = (
    "M38 MULTI-SESSION RELIABILITY\nNON-PRODUCTION\nREAD-ONLY\nBOUNDED CONCURRENCY\n"
    "ROLLOUT OFF\nNO CANARY\nNO ACTIVE\nTRADING GUARDIAN UNENGAGED"
)

_M39_BANNER = (
    "M39 LIVE DISPOSABLE SANDBOX VALIDATION\nNON-PRODUCTION\nREAD-ONLY\n"
    "BOUNDED LIVE VALIDATION ONLY\nROLLOUT OFF\nNO CANARY GRANT\nNO ACTIVE\n"
    "TRADING GUARDIAN UNENGAGED"
)


def run_m35_synthetic_session() -> dict[str, Any]:
    """Deterministic, offline synthetic sandbox-governance session. No raw secret
    is accepted from the caller; a synthetic value is minted in-process only."""
    from saathi.credentials import m35
    from saathi.connectors.providers.external.profiles import resolve_external_profile

    clock = lambda: 1752800000.0  # noqa: E731
    profile = resolve_external_profile("github_meta")
    broker = CredentialBroker(persist=False, clock=clock)
    registry = m35.SandboxAccountRegistry(clock=clock)
    leases = m35.SessionLeaseStore(clock=clock)
    cred = broker.create_reference(
        owner_scope="user:synthetic", provider_id="github_meta", credential_type="api_key",
        secret_fields={"api_key": "SYNTHETIC_SECRET_VALUE"}, scopes=("metadata:read",),
        connector_ids=("gov.http",),
    )
    acct = registry.register_sandbox(
        provider_id="github_meta", environment_class="SANDBOX", subject="SYNTHETIC_ACCOUNT_SUBJECT",
        display_alias="synthetic-sandbox", declared_scopes=("metadata:read",),
    )
    registry.verify(acct.account_ref_id, observed_scopes=("metadata:read",))
    approval = m35.build_approval(
        purpose="m35_sandbox_governance_verification", provider_id="github_meta",
        account_ref_id=acct.account_ref_id, credential_ref_id=cred.credential_ref_id,
        operation="get_meta", environment_class="SANDBOX", approved_scopes=("metadata:read",),
        read_only_acknowledged=True, sandbox_acknowledged=True, secret_access_acknowledged=True,
        non_production_acknowledged=True, write_prohibited=True,
    )
    result = m35.run_sandbox_session(
        provider_id="github_meta", profile=profile, account_registry=registry,
        account_ref_id=acct.account_ref_id, broker=broker, credential_ref_id=cred.credential_ref_id,
        approval=approval, lease_store=leases, environment_class="SANDBOX",
        requested_scopes=("metadata:read",), observed_scopes=("metadata:read",),
        synthetic=True, clock=clock,
    )
    state, _lims = m35.assess_sandbox_certification(governance_ok=result["ok"], synthetic_session_ok=result["ok"])
    return {"session_result": result, "sandbox_certification": state,
            "max_certification_state": m35.M35_MAX_CERTIFICATION_STATE}


def run_demo(*, persist: bool = False, seed: int = 1) -> dict[str, Any]:
    """Deterministic end-to-end lifecycle against a fake provider only.

    Exercises: request link → begin OAuth (PKCE) → provider authorize → callback
    (state + PKCE verified) → token exchange → store via broker → complete link →
    lease + inject (scrubbed) → refresh → revoke. No network, no real provider.
    """
    tick = {"t": 1_000_000.0}

    def clock() -> float:
        tick["t"] += 1.0
        return tick["t"]

    counter = {"n": seed}

    def rng(n: int) -> bytes:
        counter["n"] += 1
        return (str(counter["n"]).encode() * n)[:n]

    broker = CredentialBroker(persist=persist, clock=clock)
    registry = AccountLinkRegistry(broker=broker, persist=persist)
    provider = FakeOAuthProvider(clock=clock)
    oauth = OAuthLifecycle(clock=clock, rng=rng, provider=provider)

    owner = "user:test"
    provider_id = "fakemail"
    connector_id = "gov.http"
    requested = ("mail.read", "mail.send")
    allowed = ("mail.read", "mail.send", "mail.admin")

    link = registry.request_link(
        owner_scope=owner, provider_id=provider_id, connector_ids=(connector_id,),
        auth_profile="oauth2_pkce", requested_scopes=requested, allowed_scopes=allowed,
    )

    begin = oauth.begin_link(
        provider_id=provider_id, owner_scope=owner, redirect_uri="https://app.local/cb",
        requested_scopes=requested, connector_ids=(connector_id,),
        account_link_id=link.account_link_id, approval_token="approval-demo",
    )
    registry.mark_authorization_pending(link.account_link_id, oauth_session_id=begin["session_id"])

    auth = begin["authorization"]
    prov_resp = provider.authorize(
        state=auth["state"], code_challenge=auth["code_challenge"],
        redirect_uri="https://app.local/cb", provider_id=provider_id,
        scopes=list(requested),
    )
    cb = oauth.handle_callback(
        state=prov_resp["state"], code=prov_resp["code"],
        redirect_uri="https://app.local/cb", provider_id=provider_id, owner_scope=owner,
    )
    tokens = oauth.take_tokens_for_broker(begin["session_id"])
    cred = broker.create_reference(
        owner_scope=owner, provider_id=provider_id, credential_type="oauth_token_set",
        secret_fields=tokens, scopes=tuple(cb["granted_scopes"]), connector_ids=(connector_id,),
        account_link_id=link.account_link_id,
    )
    registry.complete_link(
        link.account_link_id, granted_scopes=tuple(cb["granted_scopes"]),
        credential_ref_id=cred.credential_ref_id,
    )

    # Lease + inject (scrubbed inside the boundary)
    from saathi.credentials.injection import SecretInjectionContext
    injected_fields: list[str] = []
    with SecretInjectionContext(
        broker, credential_ref_id=cred.credential_ref_id, request_id="req-demo-1",
        connector_id=connector_id, operation="send", actor="agent", owner_scope=owner,
    ) as secrets:
        injected_fields = sorted(secrets.keys())

    refresh = oauth.refresh(begin["session_id"])
    readiness = registry.readiness(link.account_link_id, connector_id=connector_id, owner_scope=owner)
    revoked = registry.revoke(link.account_link_id, reason="demo_complete", owner_scope=owner)

    scenario = {
        "owner_scope": owner,
        "provider_id": provider_id,
        "connector_id": connector_id,
        "account_link_id": link.account_link_id,
        "credential_ref_id": cred.credential_ref_id,
        "oauth_session_id": begin["session_id"],
        "granted_scopes": list(cb["granted_scopes"]),
        "callback_state_after": cb["status"],
        "injected_fields": injected_fields,
        "refresh_state_after": refresh["status"],
        "readiness_when_linked": readiness["readiness"],
        "final_link_status": revoked.status,
        "final_credential_status": broker.get_ref(cred.credential_ref_id).status,
        "provider": "FakeOAuthProvider (in-process, no network)",
        "real_oauth_endpoints_contacted": 0,
    }
    return {"broker": broker, "registry": registry, "scenario": scenario}


def _fresh_broker_registry() -> tuple[CredentialBroker, AccountLinkRegistry]:
    b = get_broker()
    r = AccountLinkRegistry(broker=b)
    return b, r


def main(argv: Optional[list[str]] = None) -> int:
    # Fail closed on raw secret carriers before argparse (so --token is never a
    # silent "unrecognized arguments" only).
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    if any(str(a).split("=")[0].lower() in (
        "--token", "--api-key", "--apikey", "--password", "--secret",
        "--authorization-header", "--authorization", "--bearer",
    ) for a in raw_argv):
        print(_M36_BANNER)
        _print({"ok": False, "error": "raw_secret_cli_rejected"})
        return 2

    p = argparse.ArgumentParser(prog="python -m saathi.credentials")
    sub = p.add_subparsers(dest="cmd")
    for name in ("status", "readiness", "profiles", "list-credentials", "list-links", "demo", "emit-evidence", "verify"):
        sub.add_parser(name)
    ic = sub.add_parser("inspect-credential"); ic.add_argument("id")
    il = sub.add_parser("inspect-link"); il.add_argument("id")
    # ── M35 sandbox-credential governance (metadata only; no raw secret) ──────
    for name in ("m35-verify", "m35-drift", "m35-scope-policy",
                 "m35-secret-source-policy", "emit-m35-evidence"):
        sub.add_parser(name)
    # ── M36 real sandbox verification (offline preflight / evidence; live gated) ─
    m36_pre = sub.add_parser("m36-preflight")
    m36_auth = sub.add_parser("m36-authorize")
    m36_auth.add_argument("--account-ref", required=False, default="")
    m36_auth.add_argument("--credential-ref", required=False, default="")
    m36_auth.add_argument("--ack", action="append", default=[], dest="acks")
    m36_qual = sub.add_parser("m36-qualify-account")
    m36_qual.add_argument("--alias", default="sbx-readonly")
    m36_qual.add_argument("--purpose", default="m36 disposable sandbox verification")
    m36_qual.add_argument("--revocation-plan", default="manual_github_pat_delete")
    m36_qual.add_argument("--deletion-plan", default="delete_after_m36")
    m36_qual.add_argument("--disposable-ack", action="store_true")
    sub.add_parser("m36-verify-secret-reference")
    sub.add_parser("m36-verify-scope")
    sub.add_parser("m36-eligibility")
    m36_run = sub.add_parser("m36-run-session")
    m36_run.add_argument("--authorization-id", default="")
    m36_run.add_argument("--account-ref", default="")
    m36_run.add_argument("--credential-ref", default="")
    m36_run.add_argument("--secret-source", default="OS_KEYCHAIN_REFERENCE")
    m36_run.add_argument("--secret-locator", default="")
    m36_run.add_argument("--operation", default="get_meta")
    m36_run.add_argument("--call-budget", type=int, default=3)
    m36_run.add_argument("--ack", action="append", default=[], dest="acks")
    m36_run.add_argument("--live", action="store_true",
                         help="require SAATHI_M36_ALLOW_LIVE_SANDBOX_VERIFICATION=1")
    sub.add_parser("m36-session-status")
    sub.add_parser("m36-revoke-session")
    sub.add_parser("m36-cleanup-status")
    sub.add_parser("emit-m36-evidence")
    # ── M37 security certification / provider contract ───────────────────────
    for name in ("m37-preflight", "m37-validate", "m37-negative", "m37-certify",
                 "m37-provider-model", "emit-m37-evidence"):
        sub.add_parser(name)
    # ── M38 multi-session reliability / canary readiness (no grant) ──────────
    for name in ("m38-preflight", "m38-run-offline-multisession", "m38-list-sessions",
                 "m38-session-status", "m38-reconcile", "m38-recover-session",
                 "m38-run-failure-matrix", "m38-evaluate-canary-readiness",
                 "emit-m38-evidence"):
        sub.add_parser(name)
    # ── M39 live disposable sandbox validation / canary eligibility (no grant) ─
    sub.add_parser("m39-preflight")
    m39_auth = sub.add_parser("m39-authorize-live-validation")
    m39_auth.add_argument("--account-ref", default="")
    m39_auth.add_argument("--credential-ref", default="")
    m39_auth.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m39_auth.add_argument("--ack", action="append", default=[], dest="acks")
    m39_qual = sub.add_parser("m39-qualify-secret-reference")
    m39_qual.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m39_qual.add_argument("--locator", default="")
    m39_qual.add_argument("--env-var-name", default="")
    m39_single = sub.add_parser("m39-run-live-single-session")
    m39_single.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m39_single.add_argument("--locator", default="")
    m39_single.add_argument("--env-var-name", default="")
    m39_single.add_argument("--expected-subject-fp", default="")
    m39_single.add_argument("--ack", action="append", default=[], dest="acks")
    m39_multi = sub.add_parser("m39-run-live-multisession")
    m39_multi.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m39_multi.add_argument("--locator", default="")
    m39_multi.add_argument("--env-var-name", default="")
    m39_multi.add_argument("--expected-subject-fp", default="")
    m39_multi.add_argument("--ack", action="append", default=[], dest="acks")
    m39_int = sub.add_parser("m39-interrupt-session")
    m39_int.add_argument("--session-id", default="")
    m39_rec = sub.add_parser("m39-recover-session")
    m39_rec.add_argument("--session-id", default="")
    m39_rev = sub.add_parser("m39-confirm-external-revocation")
    m39_rev.add_argument("--confirmed", action="store_true")
    m39_rev.add_argument("--note", default="")
    sub.add_parser("m39-evaluate-canary-eligibility")
    sub.add_parser("emit-m39-evidence")

    # ── M39.1 operator dry-run tooling (offline; no secret resolution) ─────────
    m391_plan = sub.add_parser("m39-1-plan")
    m391_plan.add_argument("--mode", default="single", choices=["single", "multi"])
    m391_plan.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m391_plan.add_argument("--locator", default="")
    m391_plan.add_argument("--env-var-name", default="")
    m391_preview = sub.add_parser("m39-1-preview")
    m391_preview.add_argument("--mode", default="single", choices=["single", "multi"])
    m391_preview.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m391_preview.add_argument("--locator", default="")
    m391_preview.add_argument("--env-var-name", default="")
    m391_avail = sub.add_parser("m39-1-backend-availability")
    m391_avail.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m391_avail.add_argument("--locator", default="")
    m391_avail.add_argument("--env-var-name", default="")
    m391_rev = sub.add_parser("m39-1-revocation-checklist")
    m391_rev.add_argument("--source-kind", default="OS_KEYCHAIN_REFERENCE")
    m391_rev.add_argument("--locator", default="")
    sub.add_parser("m39-1-diagnostics")
    sub.add_parser("m39-1-emit-evidence")

    # ── M39.2 failure-mode simulation (offline; SIMULATED_NOT_LIVE) ────────────
    m392_sim = sub.add_parser("m39-2-simulate-fault")
    m392_sim.add_argument("--mode", required=True)
    sub.add_parser("m39-2-simulation-matrix")
    sub.add_parser("m39-2-emit-evidence")

    # ── M39.3 canary-readiness framework (offline; CANARY never granted) ──────
    sub.add_parser("m39-3-prerequisites")
    sub.add_parser("m39-3-framework")
    sub.add_parser("m39-3-approval-schema")
    m393_val = sub.add_parser("m39-3-validate-approval")
    m393_val.add_argument("--record-file", default="")
    sub.add_parser("m39-3-canary-decision")
    sub.add_parser("m39-3-emit-evidence")

    # ── M39.4 deployment & rollback preparation (offline; executes nothing) ────
    m394_cfg = sub.add_parser("m39-4-validate-config")
    m394_cfg.add_argument("--config-file", default="")
    sub.add_parser("m39-4-release-checklist")
    sub.add_parser("m39-4-rollback-plan")
    sub.add_parser("m39-4-backward-compat")
    sub.add_parser("m39-4-emit-evidence")
    args = p.parse_args(argv)

    # Reject raw secret CLI carriers globally for any m36 command
    if args.cmd and str(args.cmd).startswith("m36"):
        from saathi.credentials.m36 import reject_forbidden_cli_argv, M36Error as _M36E
        try:
            reject_forbidden_cli_argv(list(argv or sys.argv[1:]))
        except _M36E as e:
            _print({"ok": False, "error": e.code, "banner": _M36_BANNER})
            return 2

    if args.cmd in ("m35-verify", "m35-drift", "m35-scope-policy",
                    "m35-secret-source-policy", "emit-m35-evidence"):
        from saathi.credentials import m35
        from saathi.connectors.providers.external.profiles import resolve_external_profile
        print(_M35_BANNER)
        if args.cmd == "m35-verify":
            out = run_m35_synthetic_session()
            summary = m35.validation_summary_body(
                session_result=out["session_result"], certification=out["sandbox_certification"])
            res = {"ok": out["session_result"]["ok"], "sandbox_certification": out["sandbox_certification"],
                   "max_certification_state": out["max_certification_state"],
                   "real_sandbox_session": "NOT_EXERCISED", "validation_summary": summary}
            if not leakscan.is_clean(res):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print(res)
            return 0 if out["session_result"]["ok"] else 3
        if args.cmd == "m35-drift":
            _print({"provider_id": "github_meta",
                    "fingerprint": m35.compute_m35_fingerprint(resolve_external_profile("github_meta")),
                    "schema_version": m35.SCHEMA_VERSION})
            return 0
        if args.cmd == "m35-scope-policy":
            _print({"allowed_classes": sorted(m35.ALLOWED_SCOPE_CLASSES),
                    "forbidden_classes": sorted(m35.FORBIDDEN_SCOPE_CLASSES),
                    "unknown_fails_closed": True})
            return 0
        if args.cmd == "m35-secret-source-policy":
            _print({"retrievable": sorted(m35._RETRIEVABLE_SOURCES),
                    "prohibited": sorted(m35.PROHIBITED_SECRET_SOURCES),
                    "fallback_permitted": False})
            return 0
        if args.cmd == "emit-m35-evidence":
            import subprocess
            import sys as _sys
            rc = subprocess.call([_sys.executable, "scripts/m35_generate_evidence.py"])
            return rc

    if args.cmd in (
        "m36-preflight", "m36-authorize", "m36-qualify-account",
        "m36-verify-secret-reference", "m36-verify-scope", "m36-eligibility",
        "m36-run-session", "m36-session-status", "m36-revoke-session",
        "m36-cleanup-status", "emit-m36-evidence",
    ):
        import os
        from saathi.credentials import m36
        print(_M36_BANNER)
        if args.cmd == "m36-preflight":
            _print(m36.preflight_summary())
            return 0
        if args.cmd == "m36-authorize":
            # Structural authorize demo only when refs supplied; otherwise policy dump
            if not args.account_ref or not args.credential_ref:
                _print({
                    "ok": False,
                    "error": "account_ref_and_credential_ref_required_for_live_authorize",
                    "required_acks": list(m36.M36_ACK_TOKENS),
                    "note": "offline authorize needs refs + all 8 acknowledgements",
                })
                return 1
            store = m36.AuthorizationStore()
            try:
                auth = store.create(
                    provider_id="github_meta",
                    account_ref_id=args.account_ref,
                    credential_ref_id=args.credential_ref,
                    acknowledgements=tuple(args.acks),
                )
            except m36.M36Error as e:
                _print({"ok": False, "error": e.code, "detail": e.detail})
                return 3
            out = auth.to_safe_dict()
            if not leakscan.is_clean(out):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print({"ok": True, "authorization": out})
            return 0
        if args.cmd == "m36-qualify-account":
            q = m36.qualify_sandbox_identity(
                provider_id="github_meta",
                account_alias=args.alias,
                environment_class="SANDBOX",
                declared_purpose=args.purpose,
                revocation_plan=args.revocation_plan,
                expiration_or_deletion_plan=args.deletion_plan,
                operator_disposable_ack=bool(args.disposable_ack),
            )
            _print(q)
            return 0 if q.get("qualified") else 3
        if args.cmd == "m36-verify-secret-reference":
            _print({
                "keychain": m36.validate_m36_secret_reference(source_kind="OS_KEYCHAIN_REFERENCE"),
                "env": m36.validate_m36_secret_reference(source_kind="ENV_REFERENCE"),
                "raw_token_rejected": True,
            })
            return 0
        if args.cmd == "m36-verify-scope":
            _print({
                "read_only": m36.classify_observed_scopes(("identity:read",), ("read:user",)),
                "write_fails": m36.classify_observed_scopes(("identity:read",), ("repo",)),
                "unobserved": m36.classify_observed_scopes(("identity:read",), None),
            })
            return 0
        if args.cmd == "m36-eligibility":
            ok, blockers = m36.compose_m36_eligibility(
                production_certified=True, connector_certified=True, m30_drift_fresh=True,
                m31_credential_governance=True, m32_provider_adapter_verified=True,
                m33_external_profile_verified=True, m34_live_controls=True,
                m35_sandbox_governance=True, m36_authorization_valid=True,
                sandbox_identity_qualified=True, credential_healthy=True,
                credential_fingerprint_present=True, account_verified=True,
                scope_verified=True, approval_valid=True, lease_valid=True,
                call_budget_remaining=True, provider_healthy=True, quarantined=False,
                rollout_off=True, verification_only_exception=True,
            )
            _print({"eligible": ok, "blockers": blockers, "rollout": "OFF",
                    "verification_only_exception": "session_specific"})
            return 0 if ok else 3
        if args.cmd == "m36-run-session":
            live_flag = os.environ.get(m36.ENV_LIVE_FLAG, "") == "1"
            if not args.live or not live_flag:
                _print({
                    "ok": False,
                    "error": "live_session_not_enabled",
                    "blocker": (
                        "Real sandbox session requires --live AND "
                        f"{m36.ENV_LIVE_FLAG}=1 plus a disposable Keychain/env "
                        "secret reference, all 8 acknowledgements, and offline "
                        "gates green. Offline path: emit-m36-evidence."
                    ),
                    "real_sandbox_session": "NOT_EXERCISED",
                    "banner": _M36_BANNER,
                })
                return 4
            # Live path: still reject if no secret locator (never accept raw token)
            if not args.secret_locator or not args.authorization_id:
                _print({"ok": False, "error": "authorization_id_and_secret_locator_required"})
                return 3
            _print({
                "ok": False,
                "error": "live_session_requires_operator_wired_backends",
                "blocker": (
                    "Live Keychain backend and operator session wiring are "
                    "intentionally operator-run; use documented runbook. "
                    "No credential was loaded in this CLI invocation."
                ),
                "real_sandbox_session": "NOT_EXERCISED",
            })
            return 5
        if args.cmd in ("m36-session-status", "m36-revoke-session", "m36-cleanup-status"):
            _print({
                "ok": True,
                "status": "NO_ACTIVE_M36_SESSION",
                "real_sandbox_session": "NOT_EXERCISED",
                "cleanup": "N/A",
            })
            return 0
        if args.cmd == "emit-m36-evidence":
            import subprocess
            import sys as _sys
            rc = subprocess.call([_sys.executable, "scripts/m36_generate_evidence.py", "--offline"])
            return rc

    if args.cmd in (
        "m37-preflight", "m37-validate", "m37-negative", "m37-certify",
        "m37-provider-model", "emit-m37-evidence",
    ):
        from saathi.credentials import m37
        print(_M37_BANNER)
        if args.cmd == "m37-preflight":
            _print(m37.preflight_summary())
            return 0
        if args.cmd == "m37-validate":
            out = m37.run_m37_validation(live_exercised=False)
            if not leakscan.is_clean(out):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print({
                "ok": out["ok"],
                "certification": out["certification"]["state"],
                "live_exercised": False,
                "m36_regression_ok": out["m36_regression_ok"],
                "negative_passed": out["negative"]["passed"],
                "negative_total": out["negative"]["total"],
                "fingerprint": out["fingerprint"],
                "authorities": out["authorities"],
                "m38_started": False,
            })
            return 0 if out["ok"] else 3
        if args.cmd == "m37-negative":
            rep = m37.run_negative_validation()
            _print({"ok": rep["failed"] == 0, "report": rep})
            return 0 if rep["failed"] == 0 else 3
        if args.cmd == "m37-certify":
            out = m37.run_m37_validation(live_exercised=False)
            _print(out["certification"])
            return 0 if out["ok"] else 3
        if args.cmd == "m37-provider-model":
            from saathi.credentials.sandbox_provider import resolve_sandbox_provider, list_sandbox_providers
            pvd = resolve_sandbox_provider("github_meta")
            _print({
                "registered": list_sandbox_providers(),
                "capabilities": pvd.capabilities().to_dict(),
                "health": pvd.health().to_dict(),
                "contract": ["identity", "health", "operation", "capabilities", "qualification", "cleanup"],
            })
            return 0
        if args.cmd == "emit-m37-evidence":
            import subprocess
            import sys as _sys
            rc = subprocess.call([_sys.executable, "scripts/m37_generate_evidence.py", "--offline"])
            return rc

    if args.cmd in (
        "m38-preflight", "m38-run-offline-multisession", "m38-list-sessions",
        "m38-session-status", "m38-reconcile", "m38-recover-session",
        "m38-run-failure-matrix", "m38-evaluate-canary-readiness", "emit-m38-evidence",
    ):
        from saathi.credentials import m38
        print(_M38_BANNER)
        if args.cmd == "m38-preflight":
            _print(m38.preflight_summary())
            return 0
        if args.cmd == "m38-run-offline-multisession":
            rep = m38.run_offline_multisession_validation()
            _print({"ok": rep["failed"] == 0, "report": {
                "total": rep["total"], "passed": rep["passed"], "failed": rep["failed"],
                "leak_clean": rep["leak_clean"],
            }})
            return 0 if rep["failed"] == 0 else 3
        if args.cmd == "m38-list-sessions":
            _print({"sessions": [], "note": "ephemeral_coordinator_no_persisted_sessions"})
            return 0
        if args.cmd == "m38-session-status":
            _print({"found": False, "note": "ephemeral_coordinator_no_persisted_sessions"})
            return 0
        if args.cmd == "m38-reconcile":
            c = m38.MultiSessionCoordinator()
            _print(c.reconcile())
            return 0
        if args.cmd == "m38-recover-session":
            c = m38.MultiSessionCoordinator()
            _print(c.recover_session("none"))
            return 0
        if args.cmd == "m38-run-failure-matrix":
            rep = m38.run_failure_injection_matrix()
            _print({"ok": rep["failed"] == 0, "passed": rep["passed"], "total": rep["total"]})
            return 0 if rep["failed"] == 0 else 3
        if args.cmd == "m38-evaluate-canary-readiness":
            out = m38.run_m38_validation(live_exercised=False)
            _print(out["canary_readiness"])
            return 0
        if args.cmd == "emit-m38-evidence":
            import subprocess
            import sys as _sys
            rc = subprocess.call([_sys.executable, "scripts/m38_generate_evidence.py", "--offline"])
            return rc

    if args.cmd and str(args.cmd).startswith("m39"):
        import os
        from saathi.credentials import m39
        print(_M39_BANNER)
        try:
            m39.reject_m39_forbidden_argv(list(argv or sys.argv[1:]))
        except m39.M39Error as e:
            _print({"ok": False, "error": e.code, "banner": _M39_BANNER})
            return 2

        if args.cmd == "m39-preflight":
            _print(m39.preflight_summary())
            return 0

        if args.cmd == "m39-authorize-live-validation":
            if not args.account_ref or not args.credential_ref:
                _print({
                    "ok": False,
                    "error": "account_ref_and_credential_ref_required",
                    "required_acks": list(m39.M39_ACK_TOKENS),
                    "note": "all 10 M39 acknowledgements required at runtime",
                })
                return 1
            from saathi.credentials.m36 import AuthorizationStore
            store = AuthorizationStore()
            try:
                auth = m39.create_live_authorization(
                    store,
                    account_ref_id=args.account_ref,
                    credential_ref_id=args.credential_ref,
                    acknowledgements=tuple(args.acks),
                    secret_source_kind=args.source_kind,
                )
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "detail": e.detail})
                return 3
            out = auth.to_safe_dict()
            if not leakscan.is_clean(out):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print({"ok": True, "authorization": out, "grants_canary": False})
            return 0

        if args.cmd == "m39-qualify-secret-reference":
            if not args.locator:
                _print({
                    "ok": False,
                    "error": "locator_required",
                    "blocker": "approved disposable secret reference required",
                    "status": "NOT_EXERCISED",
                })
                return 4
            try:
                q = m39.qualify_secret_reference(
                    source_kind=args.source_kind,
                    locator=args.locator,
                    env_var_name=args.env_var_name,
                    require_exists=True,
                )
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "status": "BLOCKED"})
                return 3
            if not leakscan.is_clean(q):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print({"ok": q.get("qualified"), "qualification": q})
            return 0 if q.get("qualified") else 3

        if args.cmd in ("m39-run-live-single-session", "m39-run-live-multisession"):
            live_flag = os.environ.get(m39.ENV_LIVE_FLAG, "") == "1"
            if not live_flag:
                _print({
                    "ok": False,
                    "error": "live_session_not_enabled",
                    "blocker": (
                        f"Live validation requires {m39.ENV_LIVE_FLAG}=1, "
                        "approved secret reference, all 10 acknowledgements, "
                        "and successful preflight. Offline path: emit-m39-evidence."
                    ),
                    "live_single_session": "NOT_EXERCISED",
                    "live_multi_session": "NOT_EXERCISED",
                    "banner": _M39_BANNER,
                    "grants_canary": False,
                })
                return 4
            if not args.locator or not args.acks:
                _print({
                    "ok": False,
                    "error": "locator_and_acknowledgements_required",
                    "required_acks": list(m39.M39_ACK_TOKENS),
                })
                return 3
            if args.cmd == "m39-run-live-single-session":
                out = m39.run_live_single_session(
                    secret_source_kind=args.source_kind,
                    secret_locator=args.locator,
                    acknowledgements=tuple(args.acks),
                    expected_subject_fingerprint=args.expected_subject_fp,
                    env_var_name=args.env_var_name,
                    live_flag=True,
                )
            else:
                out = m39.run_live_multisession(
                    secret_source_kind=args.source_kind,
                    secret_locator=args.locator,
                    acknowledgements=tuple(args.acks),
                    expected_subject_fingerprint=args.expected_subject_fp,
                    env_var_name=args.env_var_name,
                    live_flag=True,
                )
            if not leakscan.is_clean(out):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print(out)
            return 0 if out.get("ok") else 3

        if args.cmd == "m39-interrupt-session":
            ks = m39.LiveKillSwitch()
            ks.trip("cli_interrupt")
            _print({
                "ok": True,
                "kill_switch": ks.to_dict(),
                "session_id": args.session_id or None,
                "note": "new_provider_calls_blocked; local cleanup required",
                "grants_authority": False,
            })
            return 0

        if args.cmd == "m39-recover-session":
            from saathi.credentials import m38 as _m38
            c = _m38.MultiSessionCoordinator()
            out = c.recover_session(args.session_id or "none")
            _print(out)
            return 0

        if args.cmd == "m39-confirm-external-revocation":
            out = m39.record_external_revocation(
                confirmed=bool(args.confirmed),
                operator_note=args.note or "",
            )
            _print(out)
            return 0 if out.get("confirmed") else 5

        if args.cmd == "m39-evaluate-canary-eligibility":
            out = m39.run_m39_validation()
            if not leakscan.is_clean(out["canary_eligibility"]):
                _print({"ok": False, "error": "leak_detected"}); return 2
            _print(out["canary_eligibility"])
            return 0

        if args.cmd == "emit-m39-evidence":
            import subprocess
            import sys as _sys
            rc = subprocess.call([_sys.executable, "scripts/m39_generate_evidence.py", "--offline"])
            return rc

        # ── M39.1 operator dry-run tooling (offline; never resolves a secret) ──
        if args.cmd and str(args.cmd).startswith("m39-1-"):
            from saathi.credentials import m39_1
            try:
                if args.cmd == "m39-1-plan":
                    out = m39_1.build_execution_plan(
                        mode=args.mode, source_kind=args.source_kind,
                        locator=args.locator, env_var_name=args.env_var_name,
                    )
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0 if out.get("plan_valid") else 5
                if args.cmd == "m39-1-preview":
                    plan = m39_1.build_execution_plan(
                        mode=args.mode, source_kind=args.source_kind,
                        locator=args.locator, env_var_name=args.env_var_name,
                    )
                    print(m39_1.render_command_preview(plan))
                    return 0 if plan.get("plan_valid") else 5
                if args.cmd == "m39-1-backend-availability":
                    out = m39_1.check_backend_availability(
                        source_kind=args.source_kind, locator=args.locator,
                        env_var_name=args.env_var_name,
                    )
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0 if out.get("ready") else 5
                if args.cmd == "m39-1-revocation-checklist":
                    out = m39_1.generate_revocation_checklist(
                        source_kind=args.source_kind, locator=args.locator,
                    )
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    print(m39_1.render_revocation_checklist(out))
                    return 0
                if args.cmd == "m39-1-diagnostics":
                    out = m39_1.collect_offline_diagnostics()
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0
                if args.cmd == "m39-1-emit-evidence":
                    res = m39_1.emit_m39_1_evidence("docs/evidence/m39_1")
                    _print(res)
                    return 0
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "detail": getattr(e, "detail", ""),
                        "banner": _M39_BANNER})
                return 2

        # ── M39.2 failure-mode simulation (offline; SIMULATED_NOT_LIVE) ────────
        if args.cmd and str(args.cmd).startswith("m39-2-"):
            from saathi.credentials import m39_2
            try:
                if args.cmd == "m39-2-simulate-fault":
                    out = m39_2.simulate_fault(args.mode)
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0 if out.get("fails_closed") else 5
                if args.cmd == "m39-2-simulation-matrix":
                    out = m39_2.run_simulation_matrix()
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0 if out.get("verdict") == "ALL_FAULTS_FAIL_CLOSED" else 5
                if args.cmd == "m39-2-emit-evidence":
                    res = m39_2.emit_m39_2_evidence("docs/evidence/m39_2")
                    _print(res)
                    return 0
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "detail": getattr(e, "detail", ""),
                        "banner": _M39_BANNER})
                return 2

        # ── M39.3 canary-readiness framework (offline; CANARY never granted) ──
        if args.cmd and str(args.cmd).startswith("m39-3-"):
            from saathi.credentials import m39_3
            import json as _json
            try:
                if args.cmd == "m39-3-prerequisites":
                    _print(m39_3.evaluate_prerequisites())
                    return 0
                if args.cmd == "m39-3-framework":
                    _print(m39_3.framework_definitions())
                    return 0
                if args.cmd == "m39-3-approval-schema":
                    _print(m39_3.approval_record_schema())
                    return 0
                if args.cmd == "m39-3-validate-approval":
                    record = None
                    if args.record_file:
                        with open(args.record_file) as fh:
                            record = _json.load(fh)
                    out = m39_3.validate_operator_approval_record(record)
                    _print(out)
                    return 0 if out.get("valid") else 5
                if args.cmd == "m39-3-canary-decision":
                    out = m39_3.evaluate_canary_decision()
                    if out.get("grants_canary") is not False:
                        _print({"ok": False, "error": "invariant_violation_canary_granted"})
                        return 2
                    if not leakscan.is_clean(out):
                        _print({"ok": False, "error": "leak_detected"}); return 2
                    _print(out)
                    return 0
                if args.cmd == "m39-3-emit-evidence":
                    res = m39_3.emit_m39_3_evidence("docs/evidence/m39_3")
                    _print(res)
                    return 0
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "detail": getattr(e, "detail", ""),
                        "banner": _M39_BANNER})
                return 2

        # ── M39.4 deployment & rollback preparation (offline; executes nothing) ─
        if args.cmd and str(args.cmd).startswith("m39-4-"):
            from saathi.credentials import m39_4
            import json as _json4
            try:
                if args.cmd == "m39-4-validate-config":
                    config = None
                    if args.config_file:
                        with open(args.config_file) as fh:
                            config = _json4.load(fh)
                    out = m39_4.validate_deployment_config(config)
                    _print(out)
                    return 0 if out.get("valid") else 5
                if args.cmd == "m39-4-release-checklist":
                    _print(m39_4.release_checklist())
                    return 0
                if args.cmd == "m39-4-rollback-plan":
                    _print(m39_4.rollback_plan())
                    return 0
                if args.cmd == "m39-4-backward-compat":
                    out = m39_4.backward_compatibility_check()
                    _print(out)
                    return 0 if out.get("all_present") else 5
                if args.cmd == "m39-4-emit-evidence":
                    res = m39_4.emit_m39_4_evidence("docs/evidence/m39_4")
                    _print(res)
                    return 0
            except m39.M39Error as e:
                _print({"ok": False, "error": e.code, "detail": getattr(e, "detail", ""),
                        "banner": _M39_BANNER})
                return 2

    if args.cmd == "profiles":
        _print(list_profiles())
        return 0

    if args.cmd == "demo":
        out = run_demo(persist=False)
        _print(out["scenario"])
        return 0

    if args.cmd == "emit-evidence":
        out = run_demo(persist=True)
        try:
            path = evidence.generate_evidence(out["broker"], out["registry"], scenario=out["scenario"])
        except leakscan.LeakDetected as e:
            _print({"ok": False, "error": "leak_detected", "findings": [f.to_dict() for f in e.findings]})
            return 2
        _print({"ok": True, "evidence": str(path), "scenario": out["scenario"]})
        return 0

    if args.cmd == "verify":
        b, r = _fresh_broker_registry()
        rep = {**b.status_report(), "account_links_report": r.status_report()}
        inv_ok = (
            rep.get("real_credentials_stored") == 0
            and rep.get("real_oauth_flows_completed") == 0
            and rep.get("live_accounts_linked") == 0
            and rep.get("trading_guardian") == "UNCHANGED / UNENGAGED"
        )
        clean = leakscan.is_clean(rep)
        _print({"invariants_ok": inv_ok, "leak_clean": clean, "trading_guardian": rep.get("trading_guardian")})
        return 0 if (inv_ok and clean) else 1

    b, r = _fresh_broker_registry()
    if args.cmd == "status":
        _print({"broker": b.status_report(), "account_links": r.status_report()})
    elif args.cmd == "readiness":
        _print(b.readiness())
    elif args.cmd == "list-credentials":
        _print(b.list_metadata())
    elif args.cmd == "list-links":
        _print(r.list_metadata())
    elif args.cmd == "inspect-credential":
        _print(b.inspect(args.id))
    elif args.cmd == "inspect-link":
        _print(r.inspect(args.id))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
