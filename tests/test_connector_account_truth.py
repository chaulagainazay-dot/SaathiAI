"""No connector may claim CONNECTED without provider evidence.

`AccountStore.add()` defaulted to ``status="connected"``, so writing a row was
enough to assert that Google, Meta or Telegram had accepted a credential — a
green light no external system had ever agreed to. These tests pin the corrected
contract at the source rather than at each caller.

PERSISTENCE IS NOT VERIFICATION.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from saathi.connectors import manager
from saathi.connectors.accounts import (
    CALLER_SETTABLE_STATUSES, AccountStatus, AccountStore,
)


def _store() -> AccountStore:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return AccountStore(path)


# ── 1 & 2: creation never implies verification ──────────────────────────────

def test_a_new_account_is_not_connected():
    a = _store().add(provider="gmail", display_name="g")
    assert a["status"] == AccountStatus.AUTH_REQUIRED.value
    assert a["status"] != AccountStatus.CONNECTED.value


def test_storing_a_credential_does_not_connect_it():
    """The strongest form of the defect: a real-looking secret changes nothing."""
    s = _store()
    a = s.add(provider="telegram", display_name="bot",
              secret={"bot_token": "123:ABC", "chat_id": "42"})
    assert a["has_secret"] is True
    assert a["status"] == AccountStatus.AUTH_REQUIRED.value


def test_a_caller_cannot_declare_connected_at_creation():
    with pytest.raises(ValueError, match="mark_verified"):
        _store().add(provider="gmail", status=AccountStatus.CONNECTED.value)


def test_a_caller_cannot_declare_connected_afterwards():
    s = _store()
    a = s.add(provider="gmail")
    with pytest.raises(ValueError, match="mark_verified"):
        s.set_status(a["id"], AccountStatus.CONNECTED.value)


def test_an_unknown_status_is_refused_rather_than_stored():
    with pytest.raises(ValueError, match="unknown account status"):
        _store().add(provider="gmail", status="totally-fine-honest")


def test_connected_is_not_caller_settable():
    assert AccountStatus.CONNECTED.value not in CALLER_SETTABLE_STATUSES


# ── 3: verification succeeds → CONNECTED ────────────────────────────────────

def test_provider_evidence_is_what_mints_connected():
    s = _store()
    a = s.add(provider="facebook")
    # The shape meta_post.verify_token() actually returns.
    assert s.mark_verified(a["id"], evidence={"ok": True, "page_name": "pielts", "page_id": "1"})
    assert s.get(a["id"])["status"] == AccountStatus.CONNECTED.value


# ── 4, 5, 6: every failure mode stays not-connected ─────────────────────────

@pytest.mark.parametrize("evidence, label", [
    ({"ok": False, "error": "Invalid OAuth access token"}, "provider rejected"),
    ({"ok": False, "error": "timeout"}, "timeout"),
    ({}, "empty response"),
    ({"unexpected": "shape"}, "malformed — no ok field"),
    ({"ok": "yes"}, "malformed — ok is not a boolean"),
    ({"ok": None}, "malformed — ok is null"),
])
def test_a_failed_or_malformed_verification_never_connects(evidence, label):
    s = _store()
    a = s.add(provider="facebook")
    with pytest.raises(ValueError):
        s.mark_verified(a["id"], evidence=evidence)
    assert s.get(a["id"])["status"] == AccountStatus.AUTH_REQUIRED.value, label


def test_no_response_at_all_never_connects():
    """A provider that answered nothing gives the caller nothing to pass."""
    s = _store()
    a = s.add(provider="facebook")
    for nothing in (None, "", 0, [], False):
        with pytest.raises(ValueError):
            s.mark_verified(a["id"], evidence=nothing)
    assert s.get(a["id"])["status"] == AccountStatus.AUTH_REQUIRED.value


# ── 7: a simulated adapter is never a real connection ───────────────────────

def test_a_simulated_provider_is_marked_simulated_not_connected():
    s = _store()
    a = s.add(provider="youtube")
    s.mark_simulated(a["id"])
    got = s.get(a["id"])
    assert got["status"] == AccountStatus.SIMULATED.value
    assert got["status"] != AccountStatus.CONNECTED.value


def test_a_simulated_account_may_dispatch_only_simulated_work():
    s = _store()
    a = s.add(provider="gmail")
    s.mark_simulated(a["id"])
    out = manager.execute(a["id"], "email.send", {"to": "x"}, store=s)
    assert out["ok"] is True
    assert out["mode"] == "simulated", "a simulated account must not reach a real provider"


def test_a_simulated_account_cannot_drive_a_live_adapter():
    """The day a provider gains a live adapter, old SIMULATED rows must not inherit reach."""
    assert manager.provider_health()["telegram"] == "live", "telegram is the live reference adapter"
    s = _store()
    a = s.add(provider="telegram", secret={"bot_token": "x", "chat_id": "1"})
    s.mark_simulated(a["id"])
    out = manager.execute(a["id"], "messaging.send", {"text": "hi"}, store=s)
    assert out["ok"] is False
    assert "reconnect" in out["error"]


def test_an_unverified_account_cannot_execute_at_all():
    s = _store()
    a = s.add(provider="gmail")
    out = manager.execute(a["id"], "email.send", {"to": "x"}, store=s)
    assert out["ok"] is False


# ── 8: persisted state survives, it is not reclassified ─────────────────────

def test_a_verified_account_stays_verified_across_reopen():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = AccountStore(path)
    a = s.add(provider="facebook")
    s.mark_verified(a["id"], evidence={"ok": True, "page_name": "pielts"})
    assert AccountStore(path).get(a["id"])["status"] == AccountStatus.CONNECTED.value


def test_downgrades_need_no_evidence():
    """Failing closed never has to justify itself."""
    s = _store()
    a = s.add(provider="facebook")
    s.mark_verified(a["id"], evidence={"ok": True})
    for state in (AccountStatus.REVOKED, AccountStatus.EXPIRED, AccountStatus.MISCONFIGURED):
        assert s.set_status(a["id"], state.value)
        assert s.get(a["id"])["status"] == state.value


# ── 9: the legacy restore path is explicit and must announce itself ─────────

def test_restore_verified_is_named_and_demands_a_reason():
    s = _store()
    a = s.add(provider="facebook")
    with pytest.raises(ValueError, match="reason"):
        s.restore_verified(a["id"], reason="")
    assert s.restore_verified(a["id"], reason="migrated from the 2026-09 VM export")
    assert s.get(a["id"])["status"] == AccountStatus.CONNECTED.value


# ── 10: health counts only what was verified ────────────────────────────────

def test_health_counts_only_genuinely_connected_accounts():
    s = _store()
    s.add(provider="gmail")                                   # auth_required
    sim = s.add(provider="youtube"); s.mark_simulated(sim["id"])
    real = s.add(provider="facebook")
    s.mark_verified(real["id"], evidence={"ok": True, "page_name": "pielts"})
    h = s.health()
    assert h["total"] == 3
    assert h["connected"] == 1, "simulated and unverified accounts must not count as connected"
