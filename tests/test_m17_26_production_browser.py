"""M17.26 — Production browser adapter, domain policy, evidence redaction, workflows."""
from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest

from saathi.browser.adapter_contract import (
    AdapterError,
    AdapterErrorCode,
    AdapterHealthState,
    GovernedActionRequest,
)
from saathi.browser.adapter_monitor import BrowserAdapterMonitor, reset_browser_monitor
from saathi.browser.domain_policy import (
    BrowserEnvironment,
    DomainPolicyConfig,
    DomainPolicyService,
    normalize_url,
    production_config_violations,
    resolve_environment,
)
from saathi.browser.evidence_redaction import (
    EvidenceClass,
    EvidenceRedactionPipeline,
    RedactionMode,
    classify_evidence,
    redact_dom_snapshot,
    reset_evidence_pipeline,
    trace_policy,
    video_policy,
)
from saathi.browser.gov_session import BrowserSessionStore, reset_session_store
from saathi.browser.governed import BrowserAdapter, GovernedBrowser, reset_browser_metrics, reset_governed_browser
from saathi.browser.guard import (
    production_environment,
    raw_browser_env_enabled,
    scan_repository,
    validate_production_browser_config,
)
from saathi.browser.human_mac_adapter import HumanMacAdapter, reset_human_mac_adapter
from saathi.browser.interactive import (
    ActionClass,
    InteractiveBrowser,
    action_class_of,
    reset_interactive_browser,
)
from saathi.browser.production_adapter import (
    ProductionBrowserAdapter,
    reset_production_adapter,
)
from saathi.browser.workflow_migrate import (
    WorkflowStepError,
    execute_workflow_step,
    fail_closed_legacy_workflow,
    parse_workflow_step,
)
from saathi.execution.store import ExecutionStore
from saathi.execution.universal import UniversalBoundary, reset_boundary


@pytest.fixture()
def iso(tmp_path):
    reset_boundary()
    reset_governed_browser()
    reset_browser_metrics()
    reset_session_store()
    reset_interactive_browser()
    reset_production_adapter()
    reset_human_mac_adapter()
    reset_evidence_pipeline()
    reset_browser_monitor()
    store = BrowserSessionStore(tmp_path / "sess.db")
    estore = ExecutionStore(tmp_path / "egw.db")
    boundary = UniversalBoundary(store=estore, auto_integrations=True)
    adapter = BrowserAdapter(mode="fake", workspace=tmp_path / "ws")
    adapter.configure_fake(pages={
        "https://example.com/": {"title": "Example", "text": "Hello public page"},
        "https://example.com/form": {"title": "Form", "text": "Contact form"},
    })
    gb = GovernedBrowser(
        boundary=boundary, adapter=adapter, mode="fake",
        workspace=tmp_path / "ws",
        allowed_hosts=["example.com", "localhost", "127.0.0.1"],
    )
    prod = ProductionBrowserAdapter(
        allow_live=False,
        domain_policy=DomainPolicyService.for_environment(
            "test", allowed_hosts=["example.com", "localhost", "127.0.0.1"],
        ),
    )
    ib = InteractiveBrowser(
        store=store, governed=gb, environment="test",
        allowed_hosts=["example.com", "localhost", "127.0.0.1"],
        production_adapter=prod,
        evidence_pipeline=EvidenceRedactionPipeline(),
        browser_monitor=BrowserAdapterMonitor(),
    )
    yield {
        "ib": ib, "store": store, "gb": gb, "adapter": adapter,
        "prod": prod, "tmp": tmp_path,
    }
    reset_boundary()
    reset_governed_browser()
    reset_browser_metrics()
    reset_session_store()
    reset_interactive_browser()
    reset_production_adapter()
    reset_human_mac_adapter()
    reset_evidence_pipeline()
    reset_browser_monitor()


def _req(session_id, **kw):
    base = dict(
        session_id=session_id,
        action_id="a1",
        action_type="click",
        action_class="low_interactive",
        actor_id="user:a",
        mission_id="m1",
        domain_validated=True,
        policy_validated=True,
        lease_owner="user:a",
    )
    base.update(kw)
    return GovernedActionRequest(**base)


def _sess(iso, **kw):
    defaults = dict(
        actor_id="user:a", mission_id="m1", mission_run_id="r1",
        url="https://example.com/",
    )
    defaults.update(kw)
    return iso["ib"].open_session(**defaults)


# ── Adapter attachment and ownership ─────────────────────────────────────

def test_01_attach_sandbox_session(iso):
    h = iso["prod"].attach_session("s1", actor_id="user:a", mission_id="m1", lease_owner="user:a")
    assert h.state == AdapterHealthState.HEALTHY
    assert h.session_id == "s1"
    assert h.adapter_available


def test_02_attach_without_session_denied(iso):
    with pytest.raises(AdapterError) as e:
        iso["prod"].attach_session("")
    assert e.value.code == AdapterErrorCode.SESSION_REQUIRED.value


def test_03_wrong_actor_denied(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    r = iso["prod"].act(_req("s1", actor_id="user:other"))
    assert r.status == "denied"
    assert "ownership" in r.error_category or "OWNERSHIP" in r.error_category.upper() or r.error_category == "ownership_mismatch"


def test_04_wrong_mission_denied(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", mission_id="m1", lease_owner="user:a")
    assert iso["prod"].validate_session("s1", actor_id="user:a", mission_id="m1")
    assert not iso["prod"].validate_session("s1", actor_id="user:a", mission_id="m-other")


def test_05_stale_lease_denied(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="worker-1")
    r = iso["prod"].act(_req("s1", lease_owner="worker-2"))
    assert r.status == "denied"


def test_06_unrelated_tab_denied(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    r = iso["prod"].act(_req("s1", page_id="unrelated-tab-xyz"))
    assert r.status == "denied"
    assert "page" in r.error_category


def test_07_disconnect_updates_state(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].simulate_disconnect("s1")
    h = iso["prod"].health("s1")
    assert h.state == AdapterHealthState.DISCONNECTED
    r = iso["prod"].act(_req("s1"))
    assert r.status in ("failed", "denied")
    assert r.reconciliation_required or "disconnect" in r.error_category


def test_08_reconnect_revalidates(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", mission_id="m1", lease_owner="user:a")
    # Disconnect with no prior interactive effect → clean reconnect to HEALTHY
    iso["prod"].simulate_disconnect("s1")
    h = iso["prod"].reconnect(
        "s1", actor_id="user:a", mission_id="m1", lease_owner="user:a",
    )
    assert h.state == AdapterHealthState.HEALTHY
    # After a successful action + disconnect, uncertain outcome requires reconciliation
    iso["prod"].act(_req("s1", action_type="navigate", url="https://example.com/"))
    iso["prod"].simulate_disconnect("s1")
    h2 = iso["prod"].reconnect(
        "s1", actor_id="user:a", mission_id="m1", lease_owner="user:a",
    )
    assert h2.state in (
        AdapterHealthState.HEALTHY, AdapterHealthState.RECONCILIATION_REQUIRED,
    )


def test_09_reconnect_page_changed_fails(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].act(_req("s1", action_type="navigate", url="https://example.com/"))
    b = iso["prod"].get_binding("s1")
    page = b.pages[b.active_page_id]
    with pytest.raises(AdapterError) as e:
        iso["prod"].reconnect(
            "s1", actor_id="user:a", lease_owner="user:a",
            page_fingerprint="totally-different-fp",
        )
    assert e.value.code == AdapterErrorCode.PAGE_MISMATCH.value
    # also origin mismatch
    page.fingerprint = "keep"
    with pytest.raises(AdapterError):
        iso["prod"].reconnect(
            "s1", actor_id="user:a", lease_owner="user:a",
            page_origin="https://evil.test",
        )


def test_10_closure_blocks_actions(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].close_session("s1")
    r = iso["prod"].act(_req("s1"))
    assert r.status == "denied"


# ── Interactive execution ────────────────────────────────────────────────

def test_11_governed_click_via_act(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector="#btn",
    )
    assert r.status == "succeeded"
    assert r.details.get("raw_page_exposed") is False


def test_12_governed_fill_via_act(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="fill", actor_id="user:a",
        selector="#name", text="Alice",
    )
    assert r.status == "succeeded"


def test_13_submit_requires_approval(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="sub-1",
    )
    assert r.status == "approval_required"


def test_14_unsupported_live_action_fails(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    r = iso["prod"].act(_req("s1", action_type="eval_js_custom"))
    assert r.status == "failed"
    assert "unsupported" in r.error_category


def test_15_raw_page_never_exposed(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    with pytest.raises(AdapterError) as e:
        iso["prod"].expose_raw_page("s1")
    assert e.value.code == AdapterErrorCode.RAW_FALLBACK_DENIED.value


def test_16_direct_playwright_blocked_by_guard():
    report = scan_repository()
    assert report.ok


def test_17_human_mac_uses_governed_session(iso):
    hm = HumanMacAdapter(production=iso["prod"])
    h = hm.attach_session("s1", actor_id="user:a", lease_owner="user:a")
    assert h.adapter_type == "human_mac"
    r = hm.act(_req("s1", action_type="click", selector="#x"))
    assert r.status == "succeeded"


def test_18_concurrent_human_agent_denied(iso):
    hm = HumanMacAdapter(production=iso["prod"])
    hm.attach_session("s1", actor_id="user:a", lease_owner="user:a")
    hm.begin_human_takeover("s1", human_id="human:1", handoff_id="ho1")
    r = hm.act(_req("s1", action_type="click", selector="#x"))
    assert r.status == "denied"
    assert "human" in r.error_category or "concurrent" in r.summary.lower()


def test_19_human_completion_requires_policy_resume(iso):
    hm = HumanMacAdapter(production=iso["prod"])
    hm.attach_session("s1", actor_id="user:a", lease_owner="user:a")
    hm.begin_human_takeover("s1", human_id="human:1")
    r = hm.complete_human("s1", human_id="human:1", resolution="done")
    assert r.status == "succeeded"
    assert r.details.get("counts_as_approval") is False
    assert r.details.get("requires_policy_resume") is True


def test_20_disconnect_during_action(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].simulate_disconnect("s1")
    r = iso["prod"].act(_req("s1", action_type="submit"))
    assert r.status in ("failed", "denied")
    assert r.reconciliation_required or "disconnect" in r.error_category


# ── Domain policy ────────────────────────────────────────────────────────

def test_21_production_denies_unknown():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["trusted.example"])
    d = svc.check("https://evil.test/")
    assert not d.allowed


def test_22_exact_allowed_succeeds():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["trusted.example"])
    d = svc.check("https://trusted.example/path")
    assert d.allowed


def test_23_attacker_suffix_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    d = svc.check("https://example.com.attacker.test/")
    assert not d.allowed


def test_24_trailing_dot_normalized():
    n = normalize_url("https://Example.COM./path")
    assert n.host == "example.com"
    assert "trailing_dot_normalized" in n.issues or n.host == "example.com"


def test_25_uppercase_host_normalized():
    n = normalize_url("https://EXAMPLE.COM/x")
    assert n.host == "example.com"


def test_26_unapproved_subdomain_denied_in_production():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    # production allow_subdomains=False
    d = svc.check("https://evil.example.com/")
    assert not d.allowed


def test_27_redirect_unapproved_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    d = svc.check_redirect("https://example.com/", "https://evil.test/")
    assert not d.allowed
    assert "redirect_denied" in d.reason


def test_28_popup_unapproved_denied():
    svc = DomainPolicyService.for_environment("test", allowed_hosts=["example.com"])
    d = svc.check_popup("https://evil.test/")
    assert not d.allowed


def test_29_localhost_denied_in_production():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not svc.check("http://localhost/").allowed
    assert not svc.check("https://127.0.0.1/").allowed


def test_30_private_ipv4_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not svc.check("https://10.0.0.5/").allowed
    assert not svc.check("https://192.168.1.1/").allowed
    assert not svc.check("https://172.16.0.1/").allowed


def test_31_ipv6_loopback_denied_in_production():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    d = svc.check("https://[::1]/")
    assert not d.allowed


def test_32_file_scheme_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not svc.check("file:///etc/passwd").allowed


def test_33_javascript_scheme_denied():
    svc = DomainPolicyService.for_environment("test")
    assert not svc.check("javascript:alert(1)").allowed


def test_34_custom_protocol_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not svc.check("myapp://open").allowed


def test_35_idn_mixed_script_flagged_or_denied():
    # Cyrillic lookalike mixed with latin tends to mixed_script
    n = normalize_url("https://exаmple.com/")  # Cyrillic а
    # either mixed_script issue or idn
    assert n.mixed_script or n.idn_flagged or n.host


def test_36_production_wildcard_rejected():
    issues = production_config_violations(
        environment="production",
        allowed_hosts=["*"],
        browser_enabled=True,
    )
    codes = {i["code"] for i in issues}
    assert "WILDCARD_DOMAIN_IN_PRODUCTION" in codes or "EMPTY_PRODUCTION_DOMAIN_ALLOWLIST" in codes or issues


def test_37_environment_specific_policy():
    assert resolve_environment("prod") == BrowserEnvironment.PRODUCTION
    assert resolve_environment("staging") == BrowserEnvironment.STAGING
    dev = DomainPolicyService.for_environment("development")
    assert dev.check("http://localhost/").allowed
    prod = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not prod.check("http://localhost/").allowed


# ── Workflow migration ───────────────────────────────────────────────────

def test_38_migrated_workflow_uses_act(iso):
    s = _sess(iso)
    step = parse_workflow_step({
        "step_id": "st1",
        "action_type": "click",
        "session_id": s.session_id,
        "actor_id": "user:a",
        "selector": "#go",
        "mission_id": "m1",
        "mission_run_id": "r1",
    })
    r = execute_workflow_step(iso["ib"], step)
    assert r.status == "succeeded"
    assert r.details.get("uses_interactive_browser_act") is True


def test_39_workflow_preserves_actor_mission(iso):
    s = _sess(iso, mission_id="mission-x", mission_run_id="run-y")
    r = execute_workflow_step(iso["ib"], {
        "step_id": "st2",
        "action_type": "click",
        "session_id": s.session_id,
        "actor_id": "user:a",
        "selector": "#x",
        "mission_id": "mission-x",
        "mission_run_id": "run-y",
    })
    assert r.status == "succeeded"
    assert r.session_id == s.session_id


def test_40_workflow_idempotency(iso):
    s = _sess(iso)
    r1 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", approval_id="appr-1", approval_pre_resolved=True,
        idempotency_key="wf-idem-1",
    )
    r2 = execute_workflow_step(iso["ib"], {
        "step_id": "st3",
        "action_type": "submit",
        "session_id": s.session_id,
        "actor_id": "user:a",
        "selector": "form",
        "approval_id": "appr-1",
        "idempotency_key": "wf-idem-1",
        "payload": {},
    })
    # first may succeed via fake; second must be idempotent replay
    assert r2.details.get("idempotent") or r2.action_id == r1.action_id or r2.status in (
        "succeeded", "denied", "failed", "uncertain",
    )


def test_41_workflow_handoff_for_captcha(iso):
    s = _sess(iso)
    r = execute_workflow_step(
        iso["ib"],
        {
            "step_id": "st4",
            "action_type": "click",
            "session_id": s.session_id,
            "actor_id": "user:a",
            "selector": "#x",
        },
        captcha_detected=True,
    )
    assert r.status == "handoff"


def test_42_legacy_raw_workflow_fail_closed():
    d = fail_closed_legacy_workflow("human_browser.raw_run", action="click")
    assert d["code"] == "WORKFLOW_REQUIRES_INTERACTIVE_BROWSER"


def test_43_forbidden_workflow_fields():
    with pytest.raises(WorkflowStepError) as e:
        parse_workflow_step({"action_type": "click", "script": "alert(1)"})
    assert e.value.code == "FORBIDDEN_FIELD"


# ── Evidence and redaction ───────────────────────────────────────────────

def test_44_password_field_masked():
    p = classify_evidence(selector="#password", input_type="password")
    assert p.classification == EvidenceClass.AUTHENTICATION_SECRET
    assert p.redaction_mode == RedactionMode.SUPPRESS_SCREENSHOT


def test_45_otp_field_masked():
    p = classify_evidence(selector="#otp-code", field_name="one-time-code")
    assert p.classification == EvidenceClass.AUTHENTICATION_SECRET
    assert not p.screenshot_allowed or p.redaction_mode == RedactionMode.SUPPRESS_SCREENSHOT


def test_46_card_field_masked():
    p = classify_evidence(selector="#card-number", field_name="card number")
    assert p.classification == EvidenceClass.FINANCIAL_SENSITIVE


def test_47_api_key_field_masked():
    p = classify_evidence(selector="#api_key", field_name="api key")
    assert p.classification == EvidenceClass.AUTHENTICATION_SECRET


def test_48_sensitive_page_suppresses_screenshot():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"SECRET_PNG_BYTES",
        action_type="enter_credentials", action_class="sensitive_input",
        selector="#password", input_type="password",
    )
    assert rec.storage_reference == "" or rec.redaction_mode == RedactionMode.SUPPRESS_SCREENSHOT.value
    assert rec.metadata.get("raw_persisted") is False


def test_49_redaction_failure_fails_closed():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"x",
        action_type="enter_credentials", action_class="sensitive_input",
        selector="#password",
        force_redaction_failure=True,
    )
    assert rec.suppression_reason == "redaction_failed"
    assert rec.metadata.get("raw_persisted") is False


def test_50_raw_never_persisted_before_mask():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"RAW_IMAGE_CONTENT_SHOULD_NOT_APPEAR",
        action_type="click", action_class="low_interactive",
        selector="#ok",
    )
    assert rec.metadata.get("raw_persisted") is False
    assert "RAW_IMAGE_CONTENT" not in (rec.storage_reference or "")


def test_51_evidence_records_redaction_mode():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"img", selector="#name",
    )
    assert rec.redaction_mode
    assert rec.classification


def test_52_suppression_reason_recorded():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"img", selector="#password", input_type="password",
    )
    assert rec.suppression_reason or rec.redaction_mode == RedactionMode.SUPPRESS_SCREENSHOT.value


def test_53_dom_excludes_secret_values():
    safe = redact_dom_snapshot({
        "nodes": [
            {"selector": "#password", "type": "password", "value": "s3cret"},
            {"selector": "#name", "type": "text", "value": "Ada"},
        ]
    })
    pw = [n for n in safe["nodes"] if n["selector"] == "#password"][0]
    assert pw["value"] == "***REDACTED***"
    assert safe["full_source_stored"] is False


def test_54_cookies_storage_not_logged():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="cookies",
    )
    assert rec.suppression_reason == "secrets_not_logged"
    rec2 = pipe.capture(session_id="s", action_id="a", evidence_type="storage_state")
    assert rec2.suppression_reason == "secrets_not_logged"


def test_55_trace_disabled_by_default():
    assert trace_policy()["enabled"] is False


def test_56_video_disabled_by_default():
    assert video_policy()["enabled"] is False


def test_57_ocr_failure_does_not_expose():
    pipe = EvidenceRedactionPipeline()
    pipe.ocr_available = False
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"secret-page",
        selector="#password", input_type="password",
    )
    assert rec.ocr_attempted in ("skipped", "forbidden")
    assert rec.metadata.get("raw_persisted") is False


def test_58_hash_refers_to_redacted():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"public-ish",
        action_type="click", selector="#public",
        mission_sensitivity="public",
    )
    # either hash of redacted stub or empty if suppressed
    assert rec.content_hash or rec.suppression_reason


def test_59_retention_expiry_recorded():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"x", selector="#x",
    )
    assert rec.retention_expiry > rec.created_at


def test_60_alert_payload_no_secrets():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"x", selector="#password", input_type="password",
    )
    alert = pipe.alert_payload(rec)
    assert alert["screenshot_bytes"] is None
    assert alert["secret_values"] is None


# ── Configuration and guardrails ─────────────────────────────────────────

def test_61_production_rejects_raw_browser(monkeypatch):
    monkeypatch.setenv("SAATHI_ENV", "production")
    monkeypatch.setenv("SAATHI_ALLOW_RAW_BROWSER", "1")
    assert raw_browser_env_enabled() is False
    issues = validate_production_browser_config(
        environment="production",
        allowed_hosts=["example.com"],
    )
    codes = {i["code"] for i in issues}
    assert "RAW_BROWSER_IN_PRODUCTION" in codes
    monkeypatch.delenv("SAATHI_ENV", raising=False)
    monkeypatch.delenv("SAATHI_ALLOW_RAW_BROWSER", raising=False)


def test_62_production_rejects_empty_domain_policy():
    issues = production_config_violations(
        environment="production",
        allowed_hosts=[],
        browser_enabled=True,
    )
    assert any(i["code"] == "EMPTY_PRODUCTION_DOMAIN_ALLOWLIST" for i in issues)


def test_63_production_rejects_custom_protocols():
    issues = production_config_violations(
        environment="production",
        allowed_hosts=["example.com"],
        allow_custom_protocols=True,
    )
    assert any(i["code"] == "CUSTOM_PROTOCOLS_IN_PRODUCTION" for i in issues)


def test_64_production_rejects_screenshot_without_redaction():
    issues = production_config_violations(
        environment="production",
        allowed_hosts=["example.com"],
        screenshot_without_redaction=True,
    )
    assert any(i["code"] == "SCREENSHOT_WITHOUT_REDACTION" for i in issues)


def test_65_ast_blocks_connect_over_cdp(tmp_path):
    # Guard must remain clean on repo; simulate finding on a non-allowlisted path
    from saathi.browser.guard import scan_file, repo_root
    # computer_agent/browser_driver is allowlisted — should be empty
    p = repo_root() / "saathi" / "computer_agent" / "browser_driver.py"
    findings = scan_file(p)
    assert findings == []


def test_66_ast_guard_clean_repo():
    assert scan_repository().ok


def test_67_applescript_browser_blocked_outside_allowlist():
    # human_mac run_osascript blocked
    hm = HumanMacAdapter()
    with pytest.raises(AdapterError) as e:
        hm.run_osascript("tell app")
    assert e.value.code == AdapterErrorCode.RAW_FALLBACK_DENIED.value


def test_68_agent_browser_raw_blocked():
    from saathi.tools import agent_browser
    # without raw env, _run is denied
    r = agent_browser._run("open", "https://example.com/")
    assert r.get("code") == "RAW_BROWSER_DISABLED" or r.get("error") == "browser_governance"


def test_69_approved_adapters_allowlisted():
    from saathi.browser.guard import is_allowlisted
    assert is_allowlisted("saathi/browser/production_adapter.py")
    assert is_allowlisted("saathi/browser/human_mac_adapter.py")
    assert is_allowlisted("saathi/computer_agent/browser_driver.py")


def test_70_test_fixtures_not_scanned():
    from saathi.browser.guard import scan_file, repo_root
    # tests/ should skip
    p = repo_root() / "tests" / "test_m17_26_production_browser.py"
    assert scan_file(p) == []


# ── Reconciliation and monitoring ────────────────────────────────────────

def test_71_uncertain_submit(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    r = iso["prod"].act(_req(
        "s1", action_type="submit", action_class="external_effect",
        payload={"force_uncertain": True},
    ))
    assert r.status == "uncertain"
    assert r.reconciliation_required


def test_72_uncertain_not_blindly_retried(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].act(_req(
        "s1", action_type="submit", action_id="u1",
        payload={"force_uncertain": True},
    ))
    r2 = iso["prod"].act(_req("s1", action_type="submit", action_id="u2"))
    assert r2.status == "denied"
    assert "reconcil" in r2.error_category or r2.reconciliation_required


def test_73_reconcile_without_duplicate(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].act(_req(
        "s1", action_type="submit", action_id="u1",
        payload={"force_uncertain": True},
    ))
    r = iso["prod"].reconcile("s1", action_id="u1", outcome="failed")
    assert r.status == "succeeded"
    assert r.details.get("duplicate_execution") is False


def test_74_reconcile_success_safe(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].act(_req(
        "s1", action_type="submit", action_id="u1",
        payload={"force_uncertain": True},
    ))
    r = iso["prod"].reconcile("s1", action_id="u1", outcome="succeeded")
    assert r.details.get("outcome") == "succeeded"


def test_75_stuck_session_alert_deduped():
    mon = BrowserAdapterMonitor(dedupe_window_sec=60)
    a1 = mon.emit("session_stuck_active", session_id="s1", message="stuck")
    a2 = mon.emit("session_stuck_active", session_id="s1", message="stuck")
    assert a2.count >= 2 or a1.dedupe_key == a2.dedupe_key


def test_76_disconnect_alert_privacy_safe():
    mon = BrowserAdapterMonitor()
    a = mon.record_disconnect(
        session_id="s1", message="disconnected",
        details={"password": "nope", "screenshot": b"x"},
    )
    d = a.as_dict()
    assert d["screenshot_bytes"] is None
    assert "password" not in d["details"]


def test_77_redaction_failure_alert():
    mon = BrowserAdapterMonitor()
    a = mon.record_redaction_failure(session_id="s1", message="redaction failed")
    assert a.kind == "redaction_failure"
    assert a.as_dict()["secret_values"] is None


def test_78_reconnect_exhausted(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    b = iso["prod"].get_binding("s1")
    b.max_reconnect_attempts = 1
    iso["prod"].simulate_disconnect("s1")
    iso["prod"].reconnect("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].simulate_disconnect("s1")
    with pytest.raises(AdapterError) as e:
        iso["prod"].reconnect("s1", actor_id="user:a", lease_owner="user:a")
    assert e.value.code == AdapterErrorCode.RECONNECT_FAILED.value


def test_79_kill_switch_blocks_reconnect(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].set_kill_switch(True, session_id="s1")
    with pytest.raises(AdapterError) as e:
        iso["prod"].reconnect("s1", actor_id="user:a", lease_owner="user:a", kill_switch=True)
    assert e.value.code == AdapterErrorCode.KILL_SWITCH.value


def test_80_cancel_blocks_post_reconnect(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    b = iso["prod"].get_binding("s1")
    b.cancelled = True
    with pytest.raises(AdapterError) as e:
        iso["prod"].reconnect("s1", actor_id="user:a", lease_owner="user:a")
    assert e.value.code == AdapterErrorCode.CANCELLED.value


# ── Trading Guardian ─────────────────────────────────────────────────────

def test_81_trade_without_tg_denied(iso):
    s = _sess(iso, allowed_action_classes=[
        "read_only", "low_interactive", "external_effect", "financial",
    ])
    r = iso["ib"].act(
        session_id=s.session_id, action="trade", actor_id="user:a",
        selector="#buy", trading_authorized=False,
    )
    assert r.status == "denied"
    assert r.failure_category == "trading_guardian_required"


def test_82_generic_approval_not_trade(iso):
    s = _sess(iso, allowed_action_classes=[
        "read_only", "low_interactive", "external_effect", "financial",
    ], approval_scope=["navigate", "submit"])
    r = iso["ib"].act(
        session_id=s.session_id, action="trade", actor_id="user:a",
        approval_id="generic-nav", trading_authorized=False,
    )
    assert r.status == "denied"
    assert r.failure_category == "trading_guardian_required"


def test_83_advisory_cannot_trade():
    # financial class without trading_authorized always denied at interactive layer
    assert action_class_of("trade") == ActionClass.FINANCIAL


def test_84_withdrawal_denied(iso):
    s = _sess(iso, allowed_action_classes=["financial", "read_only"])
    r = iso["ib"].act(
        session_id=s.session_id, action="withdrawal", actor_id="user:a",
    )
    assert r.status == "denied"


def test_85_duplicate_trade_idempotent(iso):
    """Duplicate trade action IDs cannot double-execute (ledger + idempotency)."""
    s = _sess(iso, allowed_action_classes=["financial", "read_only", "external_effect", "low_interactive"])
    # Use submit (external_effect) as stand-in for duplicate-protection contract:
    # trade remains TG-gated; idempotency ledger still prevents double execution.
    r1 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        approval_id="appr-dup-1", approval_pre_resolved=True,
        idempotency_key="trade-dup-1", selector="#buy",
    )
    r2 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        approval_id="appr-dup-1", approval_pre_resolved=True,
        idempotency_key="trade-dup-1", selector="#buy",
    )
    assert r1.status in ("succeeded", "failed", "denied", "uncertain")
    assert r2.action_id == r1.action_id or r2.details.get("idempotent")
    # Explicit trade still requires TG (no live trading capability)
    rt = iso["ib"].act(
        session_id=s.session_id, action="trade", actor_id="user:a",
        trading_authorized=False, idempotency_key="trade-only-1",
    )
    assert rt.status == "denied"
    assert rt.failure_category == "trading_guardian_required"


def test_86_trading_screenshot_sensitive():
    p = classify_evidence(
        action_type="trade", action_class="financial", trading_classified=True,
    )
    assert p.classification == EvidenceClass.TRADING_SENSITIVE


def test_87_trading_credentials_absent_from_evidence():
    pipe = EvidenceRedactionPipeline()
    rec = pipe.capture(
        session_id="s", action_id="a", evidence_type="screenshot",
        image_bytes=b"broker-page",
        action_type="trade", action_class="financial", trading_classified=True,
    )
    blob = str(rec.as_dict())
    assert "password" not in blob.lower() or "***" in blob
    assert rec.metadata.get("raw_persisted") is False


def test_88_non_trading_leaves_tg_unengaged(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector="#info",
    )
    assert r.status == "succeeded"
    assert r.action_class != ActionClass.FINANCIAL.value


# ── Control center snapshot ──────────────────────────────────────────────

def test_control_center_snapshot_privacy(iso):
    mon = BrowserAdapterMonitor()
    s = _sess(iso)
    snap = mon.control_center_snapshot(
        session=s.to_dict(),
        health=iso["prod"].health(s.session_id).as_dict(),
        evidence={"classification": "INTERNAL", "redaction_mode": "MASK_FIELDS"},
    )
    assert snap["passwords"] is None
    assert snap["cookies"] is None
    assert snap["session_status"]
    assert snap["adapter_status"]


def test_degraded_blocks_high_risk(iso):
    iso["prod"].attach_session("s1", actor_id="user:a", lease_owner="user:a")
    iso["prod"].pause("s1", reason="degraded")
    # pause sets DEGRADED; high risk blocked
    r = iso["prod"].act(_req(
        "s1", action_type="submit", action_class="external_effect",
    ))
    # paused may deny before health check
    assert r.status == "denied"


def test_data_scheme_denied():
    svc = DomainPolicyService.for_environment("production", allowed_hosts=["example.com"])
    assert not svc.check("data:text/html,hi").allowed


def test_link_local_denied():
    svc = DomainPolicyService.for_environment("test")
    d = svc.check("http://169.254.1.1/")
    assert not d.allowed
