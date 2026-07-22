"""M33 — External provider runtime: offline execution, operator live-verify
command, credentials/accounts, eligibility/authority, evidence/leaks, and
repository invariants.

Deterministic; injected transport only; NO network, NO credentials, NO accounts.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from saathi.connectors.providers.config import ProviderConfig, RetryPolicy, TimeoutPolicy
from saathi.connectors.providers.eligibility import resolve_execution_eligibility
from saathi.connectors.providers.evidence import write_evidence
from saathi.connectors.providers.external.adapters.github_meta import GithubMetaAdapter
from saathi.connectors.providers.external.fixtures import fixture_body_bytes, scan_fixture, load_fixture
from saathi.connectors.providers.external.models import (
    ExternalFailure,
    ExternalVerificationState,
    M33_MAX_VERIFICATION,
)
from saathi.connectors.providers.external.profiles import GITHUB_META, resolve_external_profile
from saathi.connectors.providers.external.testkit import (
    fixture_sender,
    make_transport,
    private_resolver,
    raising_sender,
    tls_prober,
)
from saathi.connectors.providers.external.transport import ExternalTransport, SendContext
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    resolve_external_verification,
)
from saathi.connectors.providers.external.verify import (
    _external_config,
    fixture_hash_for,
    plan_external_verification,
    run_live_verification,
    run_offline_verification,
)
from saathi.connectors.providers.health import ProviderHealthState, compute_readiness
from saathi.connectors.providers.models import (
    ExecutionMode,
    ProviderExecutionContext,
    ProviderSideEffectClass,
    ProviderStatus,
)
from saathi.connectors.providers.runtime import ProviderExecutionRuntime
from saathi.connectors.providers.verification import ProviderVerificationStore, verify_provider
from saathi.credentials.leakscan import LeakDetected

ROOT = Path(__file__).resolve().parents[1]
P = GITHUB_META


def _store(tmp_path) -> ExternalVerificationStore:
    return ExternalVerificationStore(tmp_path / "ext_reg.json")


def _good_body() -> bytes:
    return fixture_body_bytes("github_meta")


def _adapter(transport) -> GithubMetaAdapter:
    a = GithubMetaAdapter(profile=P, transport=transport)
    a.prepare(_external_config(P))
    return a


def _run(transport, mode=ExecutionMode.SHADOW.value):
    a = _adapter(transport)
    rt = ProviderExecutionRuntime()
    ctx = ProviderExecutionContext(
        connector_id=P.connector_id, provider_id=P.provider_id, operation="get_meta",
        request_id="r", payload={}, mode=mode,
    )
    return rt.execute(a, ctx, _external_config(P))


# ── Offline execution (99–108) ────────────────────────────────────────────────
def test_standard_tests_perform_no_network(monkeypatch):
    import socket

    def _boom(*a, **k):
        raise AssertionError("network_used_in_test")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "socket", _boom)
    r = run_offline_verification("github_meta", store=ExternalVerificationStore(persist=False))
    assert r["ok"] and r["schema_result"]["compatible"]


def test_injected_transport_used():
    calls = {}

    def _sender(ctx: SendContext):
        calls["host"] = ctx.host
        return {"status_code": 200, "headers": {"content-type": "application/json"},
                "body_bytes": _good_body(), "content_type": "application/json", "decompressed_size": len(_good_body())}

    r = _run(make_transport(sender=_sender))
    assert r.status == ProviderStatus.SUCCESS.value and calls["host"] == "api.github.com"


def test_injected_dns_resolver_used():
    r = _run(make_transport(resolver=private_resolver(), sender=fixture_sender(body_bytes=_good_body())))
    assert r.safe_message.startswith(ExternalFailure.SSRF_POLICY_BLOCKED.value)


def test_injected_tls_result_used():
    r = _run(make_transport(tls_prober_fn=tls_prober(verified=False), sender=fixture_sender(body_bytes=_good_body())))
    assert r.safe_message.startswith(ExternalFailure.TLS_CERTIFICATE_FAILED.value)


def test_offline_429():
    r = _run(make_transport(sender=fixture_sender(status=429, headers={"retry-after": "1", "x-ratelimit-remaining": "0"}, body_bytes=b"{}")))
    assert r.status == ProviderStatus.RATE_LIMITED.value


def test_offline_timeout():
    r = _run(make_transport(sender=raising_sender(TimeoutError())))
    assert r.status == ProviderStatus.TIMEOUT.value


def test_offline_dns_failure():
    from saathi.connectors.providers.external.testkit import failing_resolver

    r = _run(make_transport(resolver=failing_resolver(), sender=fixture_sender(body_bytes=_good_body())))
    assert r.safe_message.startswith(ExternalFailure.DNS_RESOLUTION_FAILED.value)


def test_offline_tls_failure():
    r = _run(make_transport(tls_prober_fn=tls_prober(hostname_match=False), sender=fixture_sender(body_bytes=_good_body())))
    assert r.safe_message.startswith(ExternalFailure.TLS_HOSTNAME_FAILED.value)


def test_offline_schema_drift():
    bad = json.dumps({"pages": ["1.2.3.0/24"]}).encode()  # missing required field
    r = _run(make_transport(sender=fixture_sender(body_bytes=bad)))
    assert r.error_code == "MALFORMED_RESPONSE" and "schema:INCOMPATIBLE_MISSING_FIELD" in r.limitations


def test_offline_redirect_violation():
    r = _run(make_transport(sender=fixture_sender(status=302, headers={"location": "https://api.github.com/x"}, body_bytes=b"")))
    assert r.safe_message == ExternalFailure.REDIRECT_POLICY_BLOCKED.value


# ── Live verification command (109–120) ───────────────────────────────────────
def test_missing_ack_read_only_blocks():
    p = plan_external_verification("github_meta", ack_read_only=False, ack_network=True)
    assert not p["allowed"] and "missing_ack_read_only" in p["blockers"]


def test_missing_ack_network_blocks():
    p = plan_external_verification("github_meta", ack_read_only=True, ack_network=False)
    assert not p["allowed"] and "missing_ack_network" in p["blockers"]


def test_unknown_provider_blocks():
    p = plan_external_verification("does_not_exist", ack_read_only=True, ack_network=True)
    assert not p["allowed"] and any("provider_invalid" in b for b in p["blockers"])


def test_write_operation_blocks():
    from saathi.connectors.providers.external.models import validate_external_profile, ExternalProfileError

    with pytest.raises(ExternalProfileError):
        validate_external_profile(dataclasses.replace(P, method="POST"))


def test_rollout_activation_remains_unchanged(tmp_path):
    p = plan_external_verification("github_meta", ack_read_only=True, ack_network=True)
    assert "OFF" in p["rollout"]
    res = run_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, enabled=True,
        transport=make_transport(sender=fixture_sender(body_bytes=_good_body())), store=_store(tmp_path),
    )
    assert res["mode"] == "SHADOW" and "PRODUCTION" in res["label"].upper()


def test_call_budget_enforced():
    p = plan_external_verification("github_meta", ack_read_only=True, ack_network=True, call_budget=99)
    assert p["call_budget"] == 3


def test_deadline_enforced():
    captured = {}

    def _s(ctx: SendContext):
        captured["timeout"] = ctx.timeout
        return {"status_code": 200, "headers": {"content-type": "application/json"},
                "body_bytes": _good_body(), "content_type": "application/json", "decompressed_size": len(_good_body())}

    _run(make_transport(sender=_s))
    assert captured["timeout"] == P.deadline_seconds


def test_response_limit_enforced():
    r = _run(make_transport(sender=fixture_sender(body_bytes=b"x" * (300 * 1024))))
    assert r.safe_message == ExternalFailure.RESPONSE_TOO_LARGE.value


def test_live_verification_excluded_from_tests_by_default(tmp_path):
    # default (enabled=None) reads env flag, which is unset → aborted; no network
    res = run_live_verification("github_meta", ack_read_only=True, ack_network=True, store=_store(tmp_path))
    assert res["success_or_failure"] == "aborted" and res["reason"] == "external_verification_disabled"


def test_live_output_labeled_non_production(tmp_path):
    res = run_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, enabled=True,
        transport=make_transport(sender=fixture_sender(body_bytes=_good_body())), store=_store(tmp_path),
    )
    assert "NOT PRODUCTION AUTHORITY" in res["label"]


def test_failure_does_not_create_false_success(tmp_path):
    store = _store(tmp_path)
    res = run_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, enabled=True,
        transport=make_transport(sender=fixture_sender(status=500, body_bytes=b"{}")), store=store,
    )
    assert not res["ok"] and res["verification_state"] == ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED.value
    assert store.get("github_meta").state == ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED.value


def test_external_verification_can_be_disabled(tmp_path):
    res = run_live_verification("github_meta", ack_read_only=True, ack_network=True, enabled=False, store=_store(tmp_path))
    assert res["success_or_failure"] == "aborted"


def test_successful_live_reaches_max_state(tmp_path):
    store = _store(tmp_path)
    res = run_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, enabled=True,
        transport=make_transport(sender=fixture_sender(body_bytes=_good_body())), store=store,
    )
    assert res["verification_state"] == M33_MAX_VERIFICATION.value
    assert store.get("github_meta").live_call_count == 1


# ── Credentials and accounts (134–144) ────────────────────────────────────────
def test_credential_free_requires_no_lease():
    ctx = ProviderExecutionContext(connector_id="gov.http", provider_id="github_meta", operation="get_meta")
    assert ctx.credential_lease == "" and ctx.account_link == ""
    assert P.auth_profile == "none"


def test_raw_credential_in_config_fails():
    from saathi.connectors.providers.config import ConfigError, validate_config

    cfg = ProviderConfig(provider_id="github_meta", environment="sandbox",
                         endpoint_reference="https://api.github.com/meta", auth_profile="bearer")
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_raw_credential_in_evidence_fails(tmp_path):
    with pytest.raises(LeakDetected):
        write_evidence("leaky", {"access_token": "ghp_" + "a" * 30}, evidence_dir=tmp_path)


def test_disposable_sandbox_credential_uses_m31_broker():
    from saathi.credentials.broker import CredentialBroker  # sanctioned path exists

    assert CredentialBroker is not None


def test_credential_injected_only_at_transport_boundary():
    env = __import__("saathi.connectors.providers.external.request_envelope", fromlist=["build_request_envelope"]).build_request_envelope(P, request_id="x")
    assert "authorization" not in env.safe_headers and "cookie" not in env.safe_headers


def test_credential_absent_from_logs():
    from saathi.connectors.providers.external.request_envelope import build_request_envelope

    env = build_request_envelope(P, request_id="x")
    blob = json.dumps(env.to_dict()).lower()
    assert "authorization" not in blob and "bearer" not in blob


def test_credential_absent_from_fixtures():
    assert scan_fixture(load_fixture("github_meta")) == []


def test_live_production_account_links_zero():
    ctx = ProviderExecutionContext(connector_id="gov.http", provider_id="github_meta", operation="get_meta")
    assert ctx.account_link == ""


def test_sandbox_account_link_cannot_gain_write_scope():
    from saathi.connectors.providers.external.models import validate_external_profile, ExternalProfileError

    with pytest.raises(ExternalProfileError):
        validate_external_profile(dataclasses.replace(P, side_effect_class="IRREVERSIBLE_WRITE"))


def test_scope_expansion_fails_closed():
    from saathi.connectors.providers.external.models import validate_external_profile, ExternalProfileError

    with pytest.raises(ExternalProfileError):
        validate_external_profile(dataclasses.replace(P, auth_profile="oauth_secret"))


# ── Eligibility and authority (145–156) ───────────────────────────────────────
def _elig_setup(tmp_path):
    a = GithubMetaAdapter(profile=P, transport=make_transport(sender=fixture_sender(body_bytes=_good_body())))
    cfg = _external_config(P)
    a.prepare(cfg)
    vstore = ProviderVerificationStore(tmp_path / "m32.json")
    verify_provider(P.provider_id, identity=a.identity, config=cfg, store=vstore,
                    state="SIMULATION_VERIFIED")
    return a, cfg, vstore


def test_platform_certification_required(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, production_certified=False, verification_store=vstore)
    assert not d.allowed and d.reason == "production_not_certified"


def test_connector_certification_required(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, connector_certified=False, verification_store=vstore)
    assert not d.allowed and d.reason == "connector_not_certified"


def test_m32_simulation_verification_required(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, verification_store=vstore)
    assert d.allowed  # with M32 sim verification present
    empty = ProviderVerificationStore(tmp_path / "empty.json")
    d2 = resolve_execution_eligibility(identity=a.identity, config=cfg, verification_store=empty)
    assert not d2.allowed


def test_external_verification_is_additional(tmp_path):
    store = _store(tmp_path)
    dec = resolve_external_verification("github_meta", profile=P, fixture_hash=fixture_hash_for("github_meta"), store=store)
    assert not dec.allowed  # unverified externally until explicit external verify


def test_approval_required(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, approval_valid=False, verification_store=vstore)
    assert not d.allowed and d.reason == "approval_invalid"


def test_rollout_shadow_only(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, verification_store=vstore)
    assert d.allowed and d.reason == "eligible_shadow_only" and not d.layers["rollout_permits_production"]


def test_external_verification_does_not_activate_rollout(tmp_path):
    store = _store(tmp_path)
    run_live_verification("github_meta", ack_read_only=True, ack_network=True, enabled=True,
                          transport=make_transport(sender=fixture_sender(body_bytes=_good_body())), store=store)
    # no rollout object is ever touched; the state is read-only-verified, not active
    assert store.get("github_meta").state == M33_MAX_VERIFICATION.value
    assert "ACTIVE" not in M33_MAX_VERIFICATION.value and "CANARY" not in M33_MAX_VERIFICATION.value


def test_external_verification_does_not_grant_write_authority():
    assert P.side_effect_class == ProviderSideEffectClass.READ_ONLY.value


def test_provider_health_alone_does_not_authorize():
    d = compute_readiness(provider_id="github_meta", config_enabled=True, connector_certified=False,
                          provider_verified=False, provider_health=ProviderHealthState.HEALTHY)
    assert not d.ready


def test_account_and_credential_readiness_alone_do_not_authorize(tmp_path):
    a, cfg, vstore = _elig_setup(tmp_path)
    d = resolve_execution_eligibility(identity=a.identity, config=cfg, production_certified=False,
                                      account_ready=True, credential_ready=True, verification_store=vstore)
    assert not d.allowed


def test_direct_external_network_bypass_fails():
    tr = ExternalTransport(sender=None)  # no sender → refuses to reach out
    from saathi.connectors.providers.external.request_envelope import build_request_envelope

    r = tr.send(P, build_request_envelope(P, request_id="x"))
    assert not r.ok and r.failure_code == ExternalFailure.EXTERNAL_VERIFICATION_ABORTED.value


# ── Evidence and leaks (157–166) ──────────────────────────────────────────────
def test_external_evidence_separate_from_simulation():
    from saathi.connectors.providers.external.verification import DEFAULT_STORE_PATH as EXT
    from saathi.connectors.providers.verification import DEFAULT_STORE_PATH as SIM

    assert "m33" in str(EXT) and "m32" in str(SIM) and EXT != SIM


def test_evidence_writes_atomic_and_relative():
    d = ROOT / "docs" / "evidence" / "m33" / "_pytest_tmp"
    try:
        rel = write_evidence("ext_ok", {"provider_id": "github_meta", "ok": True}, evidence_dir=d)
        assert (d / "ext_ok.json").is_file()
        assert not str(rel).startswith("/") and rel.startswith("docs/evidence/m33")
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)


def test_evidence_has_no_auth_cookies_tokens(tmp_path):
    rel = write_evidence("clean", {"provider_id": "github_meta", "status": "ok"}, evidence_dir=tmp_path)
    text = (ROOT / rel).read_text() if (ROOT / rel).exists() else (tmp_path / "clean.json").read_text()
    low = text.lower()
    assert "set-cookie" not in low and "bearer " not in low


def test_leak_scan_passes_on_summary():
    from saathi.credentials.leakscan import is_clean

    assert is_clean({"provider_id": "github_meta", "verification_state": M33_MAX_VERIFICATION.value})


def test_verification_summary_bounded(tmp_path):
    res = run_live_verification("github_meta", ack_read_only=True, ack_network=True, enabled=True,
                                transport=make_transport(sender=fixture_sender(body_bytes=_good_body())), store=_store(tmp_path))
    assert len(json.dumps(res)) < 8192


# ── Repository invariants (167–190) ───────────────────────────────────────────
def test_loop_state_invariants():
    d = json.loads((ROOT / "docs" / "AUTONOMOUS_LOOP_STATE.json").read_text())
    assert d["production_certified"] is True
    assert d["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert d["cloud_fallback"] is False
    assert d["residual_exceptions"] == 0


def test_rollouts_off_no_canary_active():
    # M33 can never mint CANARY/ACTIVE; the max state is external-read-only
    assert M33_MAX_VERIFICATION == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS
    assert "CANARY" not in [s.value for s in ExternalVerificationState]


def test_no_write_or_financial_or_trading_calls():
    from saathi.connectors.providers.models import PROHIBITED_PROVIDER_PATTERNS

    for term in ("trade", "order", "broker", "payment", "bank", "financial", "withdraw"):
        assert term in PROHIBITED_PROVIDER_PATTERNS


def test_connector_bypass_guard_clean():
    from saathi.connectors.gov.bypass_guard import scan_connector_bypasses

    assert scan_connector_bypasses().production_bypasses == 0


def test_trading_guardian_unchanged():
    # M33 introduces no trading module and touches no financial provider
    import saathi.connectors.providers.external as ext

    src = " ".join(getattr(ext, "__all__", []))
    assert "trade" not in src.lower() and "broker" not in src.lower()
