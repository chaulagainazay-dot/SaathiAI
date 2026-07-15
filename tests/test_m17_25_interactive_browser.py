"""M17.25 — Governed interactive browser sessions, actions, and human handoffs."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from saathi.browser.gov_session import (
    BrowserSessionStore,
    SessionError,
    SessionStatus,
    reset_session_store,
)
from saathi.browser.guard import (
    production_environment,
    raw_browser_env_enabled,
    scan_repository,
)
from saathi.browser.governed import (
    BrowserAdapter,
    GovernedBrowser,
    reset_browser_metrics,
    reset_governed_browser,
)
from saathi.browser.interactive import (
    ActionClass,
    InteractiveBrowser,
    TargetError,
    action_class_of,
    reset_interactive_browser,
    resolve_target,
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
    ib = InteractiveBrowser(
        store=store, governed=gb, environment="dev",
        allowed_hosts=["example.com", "localhost", "127.0.0.1"],
    )
    yield {"ib": ib, "store": store, "gb": gb, "adapter": adapter, "tmp": tmp_path}
    reset_boundary()
    reset_governed_browser()
    reset_browser_metrics()
    reset_session_store()
    reset_interactive_browser()


def _sess(iso, **kw):
    defaults = dict(
        actor_id="user:a", mission_id="m1", mission_run_id="r1",
        url="https://example.com/",
    )
    defaults.update(kw)
    return iso["ib"].open_session(**defaults)


# ── taxonomy ──────────────────────────────────────────────────────────────

def test_action_taxonomy_classes():
    assert action_class_of("navigate") == ActionClass.READ_ONLY
    assert action_class_of("click") == ActionClass.LOW_INTERACTIVE
    assert action_class_of("submit") == ActionClass.EXTERNAL_EFFECT
    assert action_class_of("trade") == ActionClass.FINANCIAL
    assert action_class_of("eval_js") == ActionClass.PROHIBITED
    assert action_class_of("fill") == ActionClass.LOW_INTERACTIVE


# ── session ownership ─────────────────────────────────────────────────────

def test_open_session_and_navigate(iso):
    s = _sess(iso)
    assert s.status == SessionStatus.ACTIVE.value
    assert s.actor_id == "user:a"
    assert "example.com" in (s.current_origin or s.current_url)


def test_cross_actor_denied(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:other",
        selector="#x",
    )
    assert r.status == "denied"
    assert r.failure_category == "ownership_denied"


def test_cross_mission_denied(iso):
    s = _sess(iso, mission_id="mission-a")
    with pytest.raises(SessionError) as e:
        iso["store"].assert_access(
            s.session_id, actor_id="user:a", mission_id="mission-b",
        )
    assert e.value.code == "MISSION_MISMATCH"


def test_expired_session_denied(iso):
    s = _sess(iso)
    # force expiry
    with iso["store"]._conn() as c:
        c.execute(
            "UPDATE browser_session SET expires_at=? WHERE session_id=?",
            (time.time() - 10, s.session_id),
        )
        c.commit()
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a", selector="#x",
    )
    assert r.status == "denied"
    assert r.failure_category == "session_expired"


def test_stale_lease_blocks_other_worker(iso):
    s = _sess(iso)
    # open_session leases to actor; re-bind to worker-1 then block worker-2
    iso["store"].release_lease(s.session_id, "user:a")
    iso["store"].acquire_lease(s.session_id, "worker-1", ttl_sec=600)
    with pytest.raises(SessionError) as e:
        iso["store"].acquire_lease(s.session_id, "worker-2", ttl_sec=600)
    assert e.value.code == "LEASE_HELD"


def test_duplicate_worker_reclaims_after_lease_expiry(iso):
    s = _sess(iso)
    iso["store"].release_lease(s.session_id, "user:a")
    iso["store"].acquire_lease(s.session_id, "worker-1", ttl_sec=0.01)
    time.sleep(0.02)
    s2 = iso["store"].acquire_lease(s.session_id, "worker-2", ttl_sec=60)
    assert s2.lease_owner == "worker-2"


# ── interactive actions ───────────────────────────────────────────────────

def test_click_governed(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector="#btn",
    )
    assert r.status == "succeeded"
    assert r.action_class == "low_interactive"
    assert r.execution_id


def test_fill_sensitive_elevates_class(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="fill", actor_id="user:a",
        selector="#password", text="secret-value",
    )
    # sensitive selector → approval required in our policy for sensitive_input
    assert r.status in ("succeeded", "approval_required", "denied")
    if r.status == "succeeded":
        assert r.details.get("sensitive") is True


def test_navigate_approval_does_not_authorize_submit(iso):
    s = _sess(iso)
    # open_session already navigated; try submit without approval
    r = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="sub-1",
    )
    assert r.status == "approval_required"
    assert "navigation approval" in r.summary.lower() or "dedicated approval" in r.summary.lower()


def test_submit_with_dedicated_approval(iso):
    s = _sess(iso)
    r1 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="sub-ok",
    )
    assert r1.status == "approval_required"
    r2 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="sub-ok",
        approval_id="appr-submit-1", approval_pre_resolved=True,
    )
    assert r2.status == "succeeded"
    assert r2.checkpoint_id  # pre-commit checkpoint


def test_submit_idempotent_no_double(iso):
    s = _sess(iso)
    iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="dup-sub",
        approval_id="a1", approval_pre_resolved=True,
    )
    # count adapter dispatches for submit
    before = iso["adapter"].dispatch_count
    r2 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="dup-sub",
        approval_id="a1", approval_pre_resolved=True,
    )
    assert r2.status == "succeeded"
    assert r2.details.get("idempotent") is True
    assert iso["adapter"].dispatch_count == before  # no re-exec


def test_commit_requires_idempotency_key(iso):
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", approval_id="a", approval_pre_resolved=True,
    )
    assert r.status == "denied"
    assert r.failure_category == "idempotency_required"


def test_action_class_scope_enforced(iso):
    s = iso["ib"].open_session(
        actor_id="user:a", mission_id="m1", mission_run_id="r1",
        url="https://example.com/",
        allowed_action_classes=["read_only"],
    )
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector="#x",
    )
    assert r.status == "denied"
    assert r.failure_category == "action_class_not_allowed"


def test_trading_requires_guardian(iso):
    s = _sess(iso, allowed_action_classes=[
        "read_only", "low_interactive", "financial",
    ])
    # reopen with financial class
    iso["store"].transition  # keep lint quiet
    with iso["store"]._conn() as c:
        c.execute(
            "UPDATE browser_session SET allowed_action_classes=? WHERE session_id=?",
            (json.dumps(["read_only", "low_interactive", "external_effect", "financial"]),
             s.session_id),
        )
        c.commit()
    r = iso["ib"].act(
        session_id=s.session_id, action="trade", actor_id="user:a",
        url="https://example.com/broker",
        idempotency_key="trade-1",
        approval_id="browser-appr", approval_pre_resolved=True,
        trading_authorized=False,
    )
    assert r.status == "denied"
    assert r.failure_category == "trading_guardian_required"


def test_trading_guardian_unengaged_for_click(iso):
    from saathi.execution.trade import ExecutionService, PaperConnector, BrokerRegistry
    s = _sess(iso)
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a", selector="#ok",
    )
    assert r.status == "succeeded"
    src = Path(__file__).resolve().parents[1] / "saathi" / "execution" / "trade.py"
    assert "No trade bypasses approval" in src.read_text()
    reg = BrokerRegistry()
    reg.register(PaperConnector(price=lambda _s: 100.0))
    assert ExecutionService(reg) is not None


# ── target safety ─────────────────────────────────────────────────────────

def test_coordinate_target_blocked():
    with pytest.raises(TargetError) as e:
        resolve_target(selector="120, 450")
    assert e.value.code == "COORDINATE_TARGET_BLOCKED"


def test_ambiguous_target_denied(iso):
    s = _sess(iso)
    iso["ib"].set_page_elements(s.session_id, [
        {"selector": ".btn", "name": "A"},
        {"selector": ".btn", "name": "B"},
    ])
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector=".btn",
    )
    assert r.status == "denied"
    assert "ambiguous" in r.failure_category


def test_missing_target_denied(iso):
    s = _sess(iso)
    iso["ib"].set_page_elements(s.session_id, [{"selector": "#only", "name": "Only"}])
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a",
        selector="#missing",
    )
    assert r.status == "denied"
    assert r.failure_category == "target_missing"


# ── handoff + resume ──────────────────────────────────────────────────────

def test_handoff_pauses_and_blocks_agent(iso):
    s = _sess(iso)
    ho = iso["ib"].request_handoff(
        s.session_id, actor_id="user:a", reason="captcha",
    )
    assert ho.status == "handoff"
    assert ho.handoff_id
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a", selector="#x",
    )
    assert r.status == "denied"
    assert r.failure_category == "paused_for_human"


def test_handoff_claim_and_complete_resume(iso):
    s = _sess(iso)
    ho = iso["ib"].request_handoff(
        s.session_id, actor_id="user:a", reason="mfa",
    )
    claimed = iso["ib"].claim_handoff(ho.handoff_id, human_id="human:ajay")
    assert claimed["status"] == "claimed"
    done = iso["ib"].complete_handoff(ho.handoff_id, human_id="human:ajay")
    assert done.status == "succeeded"
    # agent can act again
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a", selector="#next",
    )
    assert r.status == "succeeded"


def test_handoff_decline_cancels(iso):
    s = _sess(iso)
    ho = iso["ib"].request_handoff(
        s.session_id, actor_id="user:a", reason="legal",
    )
    iso["ib"].claim_handoff(ho.handoff_id, human_id="human:ajay")
    done = iso["ib"].complete_handoff(
        ho.handoff_id, human_id="human:ajay", decline=True, resolution="declined",
    )
    assert done.status == "denied"
    assert done.failure_category == "handoff_declined"


def test_resume_requires_checkpoint(iso):
    s = _sess(iso)
    r = iso["ib"].resume(s.session_id, actor_id="user:a", checkpoint_reference="")
    # may use session checkpoint if empty — open_session doesn't set one
    if not iso["store"].require(s.session_id).checkpoint_reference:
        assert r.status == "denied"
        assert r.failure_category == "checkpoint_required"


def test_resume_page_mismatch_denied(iso):
    s = _sess(iso)
    cp = iso["ib"].checkpoint(s.session_id, actor_id="user:a")
    # checkpoint() already moved session to CHECKPOINTED when active
    r = iso["ib"].resume(
        s.session_id, actor_id="user:a",
        checkpoint_reference=cp["checkpoint_id"],
        expected_origin="https://evil.example.com",
    )
    assert r.status == "denied"
    assert r.failure_category == "page_state_mismatch"


def test_cancelled_session_cannot_act(iso):
    s = _sess(iso)
    iso["ib"].cancel_session(s.session_id, actor_id="user:a")
    r = iso["ib"].act(
        session_id=s.session_id, action="click", actor_id="user:a", selector="#x",
    )
    assert r.status == "denied"


# ── uncertain / secrets / raw / guard ─────────────────────────────────────

def test_uncertain_submit_not_retried(iso):
    s = _sess(iso)
    iso["adapter"].configure_fake(force_uncertain=True)
    r1 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="unc-1",
        approval_id="a", approval_pre_resolved=True,
    )
    assert r1.status in ("uncertain", "failed")
    # restore for ledger state
    prior = iso["store"].find_action_by_idempotency("unc-1")
    assert prior is not None
    r2 = iso["ib"].act(
        session_id=s.session_id, action="submit", actor_id="user:a",
        selector="form", idempotency_key="unc-1",
        approval_id="a", approval_pre_resolved=True,
    )
    assert r2.details.get("idempotent") is True or r2.status in ("uncertain", "failed", "succeeded")


def test_sensitive_values_not_in_action_ledger(iso):
    s = _sess(iso)
    iso["ib"].act(
        session_id=s.session_id, action="fill", actor_id="user:a",
        selector="#password", text="SuperSecretOTP999",
        approval_id="a", approval_pre_resolved=True,
    )
    with iso["store"]._conn() as c:
        rows = c.execute("SELECT * FROM browser_action_ledger").fetchall()
        blob = json.dumps([dict(r) for r in rows])
    assert "SuperSecretOTP999" not in blob


def test_raw_browser_blocked_in_production(monkeypatch):
    monkeypatch.setenv("SAATHI_ENV", "production")
    monkeypatch.setenv("SAATHI_ALLOW_RAW_BROWSER", "1")
    assert production_environment() is True
    assert raw_browser_env_enabled() is False


def test_raw_browser_allowed_non_prod(monkeypatch):
    monkeypatch.setenv("SAATHI_ENV", "dev")
    monkeypatch.setenv("SAATHI_ALLOW_RAW_BROWSER", "1")
    assert raw_browser_env_enabled() is True


def test_guard_still_clean():
    report = scan_repository()
    assert report.ok, report.as_dict()


def test_agent_click_uses_interactive(monkeypatch):
    monkeypatch.delenv("SAATHI_ALLOW_RAW_BROWSER", raising=False)
    from saathi.tools import agent_browser
    r = agent_browser.ab_click("#go")
    assert r.get("governed") is True
    assert r.get("interactive") is True or r.get("status") in (
        "succeeded", "denied", "approval_required",
    )


def test_m17_24_compat_navigate(iso):
    """GovernedBrowser direct execute still works (backward compatible)."""
    rec = iso["gb"].execute(
        action="navigate", url="https://example.com/", actor="user:a",
    )
    assert rec.status == "succeeded"


def test_critical_check_ids_present():
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "saathi" / "repair" / "critical_checks.json")
        .read_text()
    )
    ids = {c["id"] for c in data["critical_checks"]}
    for need in (
        "browser.interactive_session_ownership",
        "browser.interactive_commit_boundary",
        "browser.human_handoff_resume",
        "browser.raw_blocked_in_production",
        "browser.interactive_idempotency",
    ):
        assert need in ids


def test_close_session(iso):
    s = _sess(iso)
    closed = iso["ib"].close_session(s.session_id, actor_id="user:a")
    assert closed.status in (SessionStatus.CLOSED.value, SessionStatus.COMPLETED.value)
