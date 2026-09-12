"""Session lifecycle + auth-recovery milestone — deterministic core tests.

Exercises the session store + sessions module against an isolated temp DB
(SAATHI_SECURITY_DB), so nothing touches the real ~/.saathi/security.db.
Endpoint-level (validate/chat/voice/diagnostics) behaviour is proven separately
against the live server (see the milestone report's curl evidence)."""
import hashlib
import importlib
import os
import time

import pytest


@pytest.fixture()
def sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_SECURITY_DB", str(tmp_path / "sec.db"))
    from saathi.security import store as store_mod
    store_mod.close_store()  # drop any cached singleton so the temp path is used
    import saathi.sessions as s
    importlib.reload(s)
    yield s
    store_mod.close_store()


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


# 2 / valid token → AUTHENTICATED (validate True, status authenticated)
def test_valid_token_is_authenticated(sessions):
    tok = sessions.create(ua="pytest", kind="password")
    assert sessions.validate(tok) is True
    st = sessions.status(tok)
    assert st["authenticated"] is True
    assert st["session"]["id"] == _sha(tok)[:12]


# 4 / invalid (unknown) token → not authenticated
def test_invalid_token_rejected(sessions):
    assert sessions.validate("not-a-real-token") is False
    assert sessions.status("not-a-real-token")["authenticated"] is False


# 1 / empty token → not authenticated (drives AUTH_REQUIRED on the client)
def test_empty_token_rejected(sessions):
    assert sessions.validate("") is False
    assert sessions.status("")["authenticated"] is False
    assert sessions.status("")["session"] is None


# 6 / expired token → rejected + pruned
def test_expired_token_rejected_and_pruned(sessions):
    from saathi.security.store import get_store
    raw = "expired-raw-token"
    get_store().session_create(
        user_id=sessions._owner_id(), token_hash=_sha(raw),
        expires_at=time.time() - 10, remember_me=0,
    )
    assert sessions.validate(raw) is False
    pruned = sessions.prune()
    assert pruned["expired"] >= 1
    assert get_store().session_by_hash(_sha(raw)) is None


# 5 / revoked token → rejected + pruned
def test_revoked_token_rejected_and_pruned(sessions):
    tok = sessions.create(ua="pytest")
    assert sessions.validate(tok) is True
    assert sessions.revoke(sessions.session_id(tok)) is True
    assert sessions.validate(tok) is False
    pruned = sessions.prune()
    assert pruned["revoked"] >= 1


# 15 / revoke current session only
def test_revoke_current_session(sessions):
    a = sessions.create(ua="A")
    b = sessions.create(ua="B")
    assert sessions.revoke(sessions.session_id(a)) is True
    assert sessions.validate(a) is False
    assert sessions.validate(b) is True  # other session untouched


# 16 / revoke all OTHER sessions, keep current
def test_revoke_all_others_keeps_current(sessions):
    keep = sessions.create(ua="keep")
    sessions.create(ua="x")
    sessions.create(ua="y")
    revoked = sessions.revoke_all(except_token=keep)
    assert revoked >= 2
    assert sessions.validate(keep) is True


# 17 / emergency revoke ALL including current
def test_revoke_all_including_current(sessions):
    a = sessions.create(ua="a")
    b = sessions.create(ua="b")
    n = sessions.revoke_all_including_current()
    assert n >= 2
    assert sessions.validate(a) is False
    assert sessions.validate(b) is False


# 18+19 / prune removes expired AND revoked, never live
def test_prune_removes_dead_keeps_live(sessions):
    from saathi.security.store import get_store
    live = sessions.create(ua="live")
    dead = sessions.create(ua="dead")
    sessions.revoke(sessions.session_id(dead))
    raw_exp = "exp"
    get_store().session_create(user_id=sessions._owner_id(),
                               token_hash=_sha(raw_exp), expires_at=time.time() - 5)
    res = sessions.prune()
    assert res["revoked"] >= 1 and res["expired"] >= 1
    assert sessions.validate(live) is True  # live survives
    counts = sessions.counts()
    assert counts["active"] >= 1


# 20 / status + diagnostics never leak raw token material
def test_no_raw_token_leaked(sessions):
    tok = sessions.create(ua="secret-device")
    st = sessions.status(tok)
    blob = repr(st) + repr(sessions.counts()) + repr(sessions.listing(current_token=tok))
    assert tok not in blob                 # never the raw token
    assert _sha(tok) not in blob           # never the full hash either
    assert st["session"]["id"] == _sha(tok)[:12]  # only the 12-char fingerprint


# TTL policy: remember_me is bounded and longer than a normal login
def test_ttl_bounded_and_remember_longer(sessions):
    short = sessions.create(ua="s", remember_me=False)
    long = sessions.create(ua="l", remember_me=True)
    ss = sessions.status(short)["session"]
    ls = sessions.status(long)["session"]
    now = time.time()
    assert 0 < (ss["expires_at"] - now) <= 24 * 3600 + 5          # ~24h
    assert 24 * 3600 < (ls["expires_at"] - now) <= 30 * 24 * 3600 + 5  # ~30d, bounded


# ── M — bounded active-session concurrency (session cap + LRU eviction) ──
def test_session_cap_enforced_lru_eviction(sessions):
    # cap = 3; create 5 live sessions; the newest one is "current" and kept
    toks = [sessions.create(ua=f"s{i}") for i in range(5)]
    # touch is by last_seen; create order == last_seen order (ascending)
    evicted = sessions.enforce_cap(keep_token=toks[-1], cap=3)
    assert evicted == 2  # 5 - 3
    live = [t for t in toks if sessions.validate(t, touch=False)]
    assert len(live) == 3
    assert sessions.validate(toks[-1], touch=False) is True   # current survives
    assert sessions.validate(toks[0], touch=False) is False   # oldest evicted
    assert sessions.validate(toks[1], touch=False) is False


def test_login_below_cap_keeps_all(sessions):
    toks = [sessions.create(ua=f"s{i}") for i in range(3)]
    evicted = sessions.enforce_cap(keep_token=toks[-1], cap=5)
    assert evicted == 0
    assert all(sessions.validate(t, touch=False) for t in toks)


def test_cap_never_revokes_current_no_lockout(sessions):
    # Safety-first: even when the current session is the OLDEST, cap enforcement
    # must never revoke it (no owner lockout). It may leave cap+1 in that edge;
    # in the real login path current is always newest, so the cap is exact.
    a = sessions.create(ua="old")
    import time as _t; _t.sleep(0.01)
    sessions.create(ua="new")
    sessions.enforce_cap(keep_token=a, cap=1)
    assert sessions.validate(a, touch=False) is True  # current never revoked


def test_cap_ignores_expired_and_revoked(sessions):
    from saathi.security.store import get_store
    import hashlib, time as _t
    live = [sessions.create(ua=f"L{i}") for i in range(2)]
    # an expired row + a revoked row should not count toward the cap
    get_store().session_create(user_id=sessions._owner_id(),
        token_hash=hashlib.sha256(b"exp").hexdigest(), expires_at=_t.time()-5)
    dead = sessions.create(ua="dead"); sessions.revoke(sessions.session_id(dead))
    evicted = sessions.enforce_cap(keep_token=live[-1], cap=5)
    assert evicted == 0  # only 2 active, under cap
    assert all(sessions.validate(t, touch=False) for t in live)


def test_cap_eviction_is_auditable_via_revoke(sessions):
    # evicted sessions are soft-revoked (validate False) then prunable
    toks = [sessions.create(ua=f"s{i}") for i in range(4)]
    sessions.enforce_cap(keep_token=toks[-1], cap=2)
    pruned = sessions.prune()
    assert pruned["revoked"] >= 2  # evicted rows are revoked, then hard-pruned


# ── Issue 2: cap migration is consent-gated (login never silently collapses) ──
def test_cap_not_enforced_before_migration(sessions):
    toks = [sessions.create(ua=f"s{i}") for i in range(15)]
    assert sessions.policy_migrated() is False
    # login-time enforcement is a no-op until explicit migration
    evicted = sessions.enforce_cap_if_migrated(keep_token=toks[-1])
    assert evicted == 0
    assert sessions.counts()["active"] == 15  # historical untouched


def test_explicit_migration_collapses_then_marks(sessions):
    toks = [sessions.create(ua=f"s{i}") for i in range(15)]
    res = sessions.migrate_sessions(keep_token=toks[-1], cap=10)
    assert res["already_migrated"] is False
    assert sessions.policy_migrated() is True
    assert sessions.counts()["active"] == 10
    assert sessions.validate(toks[-1], touch=False) is True  # current preserved


def test_cap_enforced_after_migration_on_login(sessions):
    sessions.mark_policy_migrated()
    toks = [sessions.create(ua=f"s{i}") for i in range(13)]
    evicted = sessions.enforce_cap_if_migrated(keep_token=toks[-1])
    assert evicted == 3  # 13 - 10
    assert sessions.counts()["active"] == 10


def test_default_cap_is_ten(sessions):
    assert sessions.MAX_ACTIVE_SESSIONS == 10
