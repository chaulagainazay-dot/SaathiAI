"""M341 — safety properties the soak validation is required to prove.

The soak found a real defect: four concurrent `decide_approval` calls on one
approval all succeeded, because the guard was a read-check-write. These tests
pin the fix so it cannot silently regress, and cover the sibling races.

Fast and deterministic — the long-running soak itself lives in
scripts/m341_private_alpha_soak.py.
"""
from __future__ import annotations

import threading

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests

OWNER_PASSWORD = "OwnerPassw0rd!1"
OPERATOR_PASSWORD = "OperatorPassw0rd!1"
TOOL_LOCAL_WRITE = "m49.local_note_write"


@pytest.fixture()
def tenant(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m341.db")
    import saathi.platform.alpha  # noqa: F401

    owner = platform.bootstrap_owner_secure(
        email="owner@m341.local", name="Owner", password=OWNER_PASSWORD,
        org_name="M341 Org", workspace_name="M341 WS",
    )
    octx = platform.require_context(owner["token"])
    invite = platform.create_invitation(octx, email="operator@m341.local", role="operator")
    operator = platform.accept_invitation(
        invite_code=invite["invite_code"], name="Operator", password=OPERATOR_PASSWORD
    )
    uctx = platform.require_context(operator["token"])
    return platform, octx, uctx, operator["token"]


def _request(platform, uctx, ttl=300):
    return platform.request_approval(
        uctx, tool_id=TOOL_LOCAL_WRITE, capability="write",
        side_effect_class="LOCAL_REVERSIBLE", authority="LOCAL_MUTATION", ttl_sec=ttl,
    )


def _race(fn, n):
    outcomes: list[str] = []
    lock = threading.Lock()

    def _go(i):
        try:
            fn(i)
            with lock:
                outcomes.append("ok")
        except Exception as exc:  # noqa: BLE001
            with lock:
                outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=_go, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes


@pytest.mark.parametrize("deciders", [2, 4, 8])
def test_exactly_one_concurrent_decision_wins(tenant, deciders):
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    outcomes = _race(
        lambda i: platform.decide_approval(octx, approval.approval_id, approve=True), deciders
    )
    assert outcomes.count("ok") == 1, outcomes
    assert platform.store.get_approval(approval.approval_id).status == "approved"


def test_concurrent_approve_and_reject_cannot_both_win(tenant):
    """A reject racing an approve must not be overwritten by the loser."""
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    outcomes = _race(
        lambda i: platform.decide_approval(octx, approval.approval_id, approve=(i % 2 == 0)), 6
    )
    assert outcomes.count("ok") == 1, outcomes
    status = platform.store.get_approval(approval.approval_id).status
    assert status in ("approved", "rejected")


def test_sequential_second_decision_is_still_refused(tenant):
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    platform.decide_approval(octx, approval.approval_id, approve=True)
    with pytest.raises(PlatformContextError) as excinfo:
        platform.decide_approval(octx, approval.approval_id, approve=False)
    assert excinfo.value.code == "APPROVAL_NOT_PENDING"


def test_concurrent_revocation_is_single_winner(tenant):
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    platform.decide_approval(octx, approval.approval_id, approve=True)
    outcomes = _race(lambda i: platform.revoke_approval(octx, approval.approval_id), 4)
    assert outcomes.count("ok") == 1, outcomes
    assert platform.store.get_approval(approval.approval_id).status == "revoked"


def test_decision_still_records_the_deciding_human(tenant):
    """The atomic path must not lose the decider, timestamp or reason."""
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    record = platform.decide_approval(
        octx, approval.approval_id, approve=True, reason="reviewed by owner"
    )
    assert record.status == "approved"
    assert record.decided_by == octx.user_id
    assert record.decided_at > 0
    assert record.reason == "reviewed by owner"
    events = platform.store.list_audit(org_id=octx.org_id, limit=100)
    assert any(e["event"] == "approval.decided" for e in events)


def test_requester_still_cannot_decide_own_approval(tenant):
    platform, _, uctx, _ = tenant
    approval = _request(platform, uctx)
    with pytest.raises(PlatformContextError):
        platform.decide_approval(uctx, approval.approval_id, approve=True)


def test_expired_approval_is_still_refused(tenant):
    import time

    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx, ttl=0.05)
    time.sleep(0.2)
    with pytest.raises(PlatformContextError):
        platform.decide_approval(octx, approval.approval_id, approve=True)


def test_cross_org_decision_is_still_refused(tenant):
    platform, octx, uctx, _ = tenant
    approval = _request(platform, uctx)
    outsider = platform.store.create_user(email="outsider@other.local", name="Outsider")
    org = platform.store.create_org("Other Org", outsider.user_id)
    workspace = platform.store.create_workspace(org.org_id, "Other WS", outsider.user_id)
    platform.store.add_member(org.org_id, outsider.user_id, "owner")
    foreign = platform.require_context(
        platform.login(
            email="outsider@other.local", org_id=org.org_id, workspace_id=workspace.workspace_id
        )["token"]
    )
    with pytest.raises(PlatformContextError) as excinfo:
        platform.decide_approval(foreign, approval.approval_id, approve=True)
    assert excinfo.value.code == "APPROVAL_ISOLATION"


def test_concurrent_execution_consumes_an_approval_once(tenant):
    """Single-use dispatch: one approval must authorize at most one execution."""
    platform, octx, uctx, token = tenant
    approval = _request(platform, uctx)
    platform.decide_approval(octx, approval.approval_id, approve=True)
    results: list[bool] = []
    refusals: list[str] = []
    lock = threading.Lock()

    def _exec(i):
        try:
            result = platform.execute_tool(
                uctx, tool_id=TOOL_LOCAL_WRITE, arguments={"key": f"k{i}", "value": "v"},
                approval_id=approval.approval_id, capability="write",
            )
            with lock:
                results.append(bool(getattr(result, "ok", False)))
        except PlatformContextError as exc:
            # Losers are refused, which is the property under test.
            with lock:
                results.append(False)
                refusals.append(exc.code)

    threads = [threading.Thread(target=_exec, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert results.count(True) == 1, results
    assert all(code in ("APPROVAL_REPLAY", "APPROVAL_REQUIRED") for code in refusals), refusals
