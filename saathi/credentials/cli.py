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
    p = argparse.ArgumentParser(prog="python -m saathi.credentials")
    sub = p.add_subparsers(dest="cmd")
    for name in ("status", "readiness", "profiles", "list-credentials", "list-links", "demo", "emit-evidence", "verify"):
        sub.add_parser(name)
    ic = sub.add_parser("inspect-credential"); ic.add_argument("id")
    il = sub.add_parser("inspect-link"); il.add_argument("id")
    args = p.parse_args(argv)

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
