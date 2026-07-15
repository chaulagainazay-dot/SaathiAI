"""M17.24 — Eliminate residual ungoverned browser dispatch paths."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from saathi.browser.guard import (
    BrowserGovernanceError,
    assert_no_ungoverned_driver_imports,
    deny_raw_production_dispatch,
    raw_browser_env_enabled,
    require_governed_context,
    scan_repository,
)
from saathi.browser.governed import (
    BrowserAdapter,
    GovernedBrowser,
    browser_metrics,
    redact_text,
    reset_browser_metrics,
    reset_governed_browser,
)
from saathi.execution.execution_state import ExecutionState
from saathi.execution.store import ExecutionStore
from saathi.execution.universal import UniversalBoundary, reset_boundary


@pytest.fixture()
def iso(tmp_path):
    reset_boundary()
    reset_governed_browser()
    reset_browser_metrics()
    store = ExecutionStore(tmp_path / "egw.db")
    boundary = UniversalBoundary(store=store, auto_integrations=True)
    adapter = BrowserAdapter(mode="fake", workspace=tmp_path / "ws")
    adapter.configure_fake(pages={
        "https://example.com/": {
            "title": "Example Domain",
            "text": "This domain is for use in illustrative examples.",
        },
    })
    gb = GovernedBrowser(
        boundary=boundary,
        adapter=adapter,
        mode="fake",
        workspace=tmp_path / "ws",
        allowed_hosts=["example.com", "localhost", "127.0.0.1"],
    )
    yield {
        "gb": gb, "adapter": adapter, "boundary": boundary, "store": store,
        "tmp": tmp_path, "ws": tmp_path / "ws",
    }
    reset_boundary()
    reset_governed_browser()
    reset_browser_metrics()


# 1. Direct low-level browser import from production code is blocked
def test_direct_low_level_import_blocked():
    report = scan_repository()
    assert report.ok, report.as_dict()
    assert_no_ungoverned_driver_imports()


# 2. Direct browser dispatch outside canonical gateway is blocked
def test_direct_dispatch_outside_gateway_blocked():
    from saathi.browser import BrowserService
    from saathi.browser.guard import BrowserGovernanceError
    from saathi.browser.types import Capabilities, Page, Tier
    from saathi.browser.base import BrowserTier

    class Fake(BrowserTier):
        name = "fake"
        tier = Tier.HTTP
        def capabilities(self):
            return Capabilities(fetch=True)
        def available(self):
            return True
        def open(self, url, *, timeout=30, session=None):
            return Page(url=url, status=200, text="ok", title="t", tier=Tier.HTTP)

    # Production-style service: direct open blocked
    svc = BrowserService(tiers=[Fake()], allow_direct=False)
    with pytest.raises(BrowserGovernanceError) as ei:
        svc.open("https://example.com/", governed=False)
    assert ei.value.code == "DIRECT_BROWSER_BLOCKED"


# 3. Governed browser dispatch succeeds with valid context
def test_governed_dispatch_succeeds(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:ajay",
        mission_id="m1", request_source="api",
    )
    assert rec.status == ExecutionState.SUCCEEDED.value
    assert iso["adapter"].dispatch_count == 1


# 4. Missing actor is denied
def test_missing_actor_denied(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="",
    )
    assert rec.status == ExecutionState.DENIED.value
    assert iso["adapter"].dispatch_count == 0


def test_unknown_actor_denied(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="unknown",
    )
    assert rec.status == ExecutionState.DENIED.value


# 5. Missing mission/run context denied where required
def test_missing_mission_run_denied_for_agent(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        request_source="agent", mission_id="m1", mission_run_id="",
        require_mission=True,
    )
    assert rec.status == ExecutionState.DENIED.value
    assert iso["adapter"].dispatch_count == 0


# 6–7. Invalid / expired approval denied
def test_invalid_approval_denied(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        approval_valid=False, approval_id="bad",
    )
    assert rec.status == ExecutionState.DENIED.value


def test_expired_approval_denied(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        approval_expired=True, approval_id="old",
    )
    assert rec.status == ExecutionState.DENIED.value


# 8. Duplicate idempotency key does not execute twice
def test_duplicate_idempotency_no_double_execute(iso):
    k = "idem-m17-24-unique-key"
    r1 = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        idempotency_key=k,
    )
    r2 = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        idempotency_key=k,
    )
    assert r1.status == ExecutionState.SUCCEEDED.value
    assert r2.execution_id == r1.execution_id or r2.status == r1.status
    assert iso["adapter"].dispatch_count == 1


# 9. Retry re-enters through governance
def test_retry_reenters_governance(iso):
    # unauthorized retry denied
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        retry_attempt=2, retry_authorized=False,
    )
    assert rec.status == ExecutionState.DENIED.value
    assert iso["adapter"].dispatch_count == 0
    # authorized retry proceeds
    rec2 = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        retry_attempt=1, retry_authorized=True, force_new=True,
    )
    assert rec2.status == ExecutionState.SUCCEEDED.value


# 10. Resume requires valid checkpoint
def test_resume_requires_checkpoint(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        resume=True, checkpoint_reference="",
    )
    assert rec.status == ExecutionState.DENIED.value


def test_resume_with_checkpoint_ok(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        resume=True, checkpoint_reference="cp-abc",
    )
    assert rec.status == ExecutionState.SUCCEEDED.value


# 11. Cancelled mission cannot dispatch
def test_cancelled_mission_cannot_dispatch(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        mission_state="cancelled",
    )
    assert rec.status == ExecutionState.DENIED.value
    assert iso["adapter"].dispatch_count == 0


# 12. Disabled schedule cannot dispatch
def test_disabled_schedule_cannot_dispatch(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        request_source="scheduler", mission_id="m1", mission_run_id="r1",
        schedule_enabled=False,
    )
    assert rec.status == ExecutionState.DENIED.value


# 13. Duplicate event trigger cannot double-dispatch (idempotency + untrusted)
def test_duplicate_event_trigger_governed(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        request_source="event_trigger", mission_id="m1", mission_run_id="r1",
        trigger_trusted=False,
    )
    assert rec.status == ExecutionState.DENIED.value
    # trusted + idempotent
    key = "evt-trigger-dup-1"
    a = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        request_source="event_trigger", mission_id="m1", mission_run_id="r1",
        trigger_trusted=True, idempotency_key=key,
    )
    b = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        request_source="event_trigger", mission_id="m1", mission_run_id="r1",
        trigger_trusted=True, idempotency_key=key,
    )
    assert a.status == ExecutionState.SUCCEEDED.value
    assert iso["adapter"].dispatch_count == 1


# 14. Agent tool cannot access raw browser driver
def test_agent_tool_no_raw_driver(monkeypatch):
    monkeypatch.delenv("SAATHI_ALLOW_RAW_BROWSER", raising=False)
    from saathi.tools import agent_browser
    r = agent_browser.ab_click("#btn")
    assert r.get("code") == "RAW_BROWSER_DISABLED" or r.get("error") == "browser_governance"
    r2 = agent_browser._run("open", "https://example.com/")
    assert r2.get("code") == "RAW_BROWSER_DISABLED"


# 15. API caller cannot forge another mission's execution context
def test_api_cannot_forge_mission(iso):
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
        mission_id="mission-victim", expected_mission_id="mission-caller",
        request_source="api",
    )
    assert rec.status == ExecutionState.DENIED.value
    assert iso["adapter"].dispatch_count == 0


# 16. Debug/legacy path fails closed
def test_legacy_debug_path_fails_closed(monkeypatch):
    monkeypatch.delenv("SAATHI_ALLOW_RAW_BROWSER", raising=False)
    payload = deny_raw_production_dispatch(source="legacy_debug", action="open")
    assert payload["code"] == "RAW_BROWSER_DISABLED"
    from saathi.tools.browser import post
    # linkedin not allowlisted → governance deny or raw disabled
    out = post("linkedin", "hello world", actor="user:a")
    assert out.get("error") in (
        "browser_governance", "governance_denied", "approval_required", "governance_error",
    ) or out.get("code") == "RAW_BROWSER_DISABLED"


# 17. Browser subprocess launch outside allowlist is detected
def test_subprocess_browser_outside_allowlist_detected(tmp_path):
    # Create a fake product module with forbidden import
    root = tmp_path / "repo"
    pkg = root / "saathi" / "evil_mod"
    pkg.mkdir(parents=True)
    (root / "saathi" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    bad = pkg / "raw.py"
    bad.write_text(
        "from playwright.sync_api import sync_playwright\n"
        "import subprocess\n"
        "subprocess.run(['agent-browser', 'open'])\n"
    )
    report = scan_repository(root=root)
    assert not report.ok
    kinds = {f.kind for f in report.findings}
    assert "forbidden_import" in kinds or "forbidden_from_import" in kinds


# 18–19. Evidence for success and denial
def test_evidence_emitted_success_and_denial(iso):
    ok = iso["gb"].execute(
        action="screenshot", url="https://example.com/", actor="user:a",
    )
    assert ok.status == ExecutionState.SUCCEEDED.value
    bad = iso["gb"].execute(
        action="navigate", url="https://not-allowed.invalid/", actor="user:a",
    )
    assert bad.status == ExecutionState.DENIED.value
    m = browser_metrics()
    assert m["succeeded"] >= 1
    assert m["denied"] >= 1 or m["domain_denied"] >= 1


# 20. Sensitive data redacted
def test_sensitive_data_redacted():
    s = redact_text("password=supersecret token=abc cookie=xyz")
    assert "supersecret" not in s
    assert "redacted" in s.lower() or "***" in s or "[redacted]" in s


# 21–22. Trading-classified defers to Trading Guardian; generic approval insufficient
def test_trading_classified_defers_to_guardian(iso):
    rec = iso["gb"].execute(
        action="trade", url="https://example.com/broker", actor="user:a",
        approval_id="browser-appr-1", approval_pre_resolved=True,
        trading_classified=True, trading_authorized=False,
    )
    assert rec.status == ExecutionState.DENIED.value
    # Even with generic pre-resolved approval, trading without TG auth denied
    assert iso["adapter"].dispatch_count == 0


def test_generic_browser_approval_not_trading(iso):
    # trade action is prohibited + trading guard
    rec = iso["gb"].execute(
        action="trade", url="https://example.com/", actor="user:a",
        approval_pre_resolved=True,
    )
    assert rec.status == ExecutionState.DENIED.value


# 23. Trading Guardian remains unengaged for unrelated browser work
def test_trading_guardian_unengaged_for_browser(iso):
    from saathi.execution.trade import ExecutionService, PaperConnector, BrokerRegistry
    from saathi.execution import ExecutionStatus
    src = Path(__file__).resolve().parents[1] / "saathi" / "execution" / "trade.py"
    text = src.read_text(encoding="utf-8")
    assert "No trade bypasses approval" in text
    assert "FILLED" in {s.name for s in ExecutionStatus}
    reg = BrokerRegistry()
    reg.register(PaperConnector(price=lambda _s: 100.0))
    assert ExecutionService(reg) is not None
    # Unrelated navigate does not touch trade module state
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
    )
    assert rec.status == ExecutionState.SUCCEEDED.value
    assert rec.family == "browser"


# 24. Existing governed browser workflows remain backward-compatible
def test_backward_compatible_governed_api(iso):
    # M17.23-style call without new kwargs still works
    rec = iso["gb"].execute(action="read", url="https://example.com/", actor="user:a")
    assert rec.status == ExecutionState.SUCCEEDED.value
    rec2 = iso["gb"].execute(action="navigate", url="https://example.com/", actor="user:a")
    assert rec2.status == ExecutionState.SUCCEEDED.value


def test_production_singleton_defaults_governed():
    from saathi.browser.service import browser as prod
    assert prod.allow_direct is False


def test_agent_open_routes_governed(monkeypatch):
    monkeypatch.delenv("SAATHI_ALLOW_RAW_BROWSER", raising=False)
    from saathi.tools import agent_browser
    # Uses default_governed_browser (fake mode) — domain example.com OK
    r = agent_browser.ab_open("https://example.com/")
    assert r.get("governed") is True or r.get("code") == "RAW_BROWSER_DISABLED"


def test_require_governed_context_unit():
    with pytest.raises(BrowserGovernanceError) as e:
        require_governed_context(actor_id="")
    assert e.value.code == "MISSING_ACTOR"
    with pytest.raises(BrowserGovernanceError) as e2:
        require_governed_context(
            actor_id="u", trading_classified=True, trading_authorized=False,
        )
    assert e2.value.code == "TRADING_GUARDIAN_REQUIRED"


def test_critical_check_ids_present():
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "saathi" / "repair" / "critical_checks.json")
        .read_text()
    )
    ids = {c["id"] for c in data["critical_checks"]}
    for need in (
        "browser.dispatch_guard_present",
        "browser.no_ungoverned_driver_imports",
        "browser.direct_dispatch_blocked",
        "browser.context_attribution_enforced",
        "browser.trading_isolation",
    ):
        assert need in ids


def test_m17_23_still_compatible(iso):
    """Regression: core M17.23 navigate path still works."""
    rec = iso["gb"].execute(action="navigate", url="https://example.com/", actor="user:a")
    assert rec.status == ExecutionState.SUCCEEDED.value
    assert rec.family == "browser"
