"""Focused tests for the local private-alpha password-reset CLI.

Covers the security properties that matter: the right user is re-credentialed,
the old password stops working, every session for that user is revoked, no other
user is touched, RBAC and workspace bindings are untouched, and neither the
password nor its hash ever reaches stdout, stderr or the audit trail.
"""

from __future__ import annotations

import sqlite3

import pytest

import saathi.platform.alpha  # noqa: F401  (patches set_password onto PlatformService)
from saathi.platform import cli
from saathi.platform.service import PlatformService
from saathi.platform.store import PlatformStore

OLD_PASSWORD = "Old-Passw0rd!x"
NEW_PASSWORD = "New-Passw0rd!x"


@pytest.fixture()
def store(tmp_path):
    """A throwaway platform store. The real database is never touched."""
    return PlatformStore(tmp_path / "platform.db")


@pytest.fixture()
def seeded(store):
    """Two credentialed users in one org, with distinct roles and a live session."""
    svc = PlatformService(store)
    owner = store.create_user(email="owner@test.local", name="Owner")
    other = store.create_user(email="operator@test.local", name="Operator")

    org = store.create_org("Test Org", owner.user_id)
    ws = store.create_workspace(org.org_id, "Test Workspace", owner.user_id)
    store.add_member(org.org_id, owner.user_id, "owner")
    store.add_member(org.org_id, other.user_id, "operator")

    svc.set_password(owner.user_id, OLD_PASSWORD)
    svc.set_password(other.user_id, OLD_PASSWORD)

    # A live session for each user, so revocation scope is observable.
    owner_sess, _ = store.create_session(
        owner.user_id, "tok_owner_seed", org_id=org.org_id,
        workspace_id=ws.workspace_id, role="owner",
    )
    other_sess, _ = store.create_session(
        other.user_id, "tok_other_seed", org_id=org.org_id,
        workspace_id=ws.workspace_id, role="operator",
    )

    return {
        "svc": svc, "org": org, "ws": ws,
        "owner": owner, "other": other,
        "owner_session": owner_sess, "other_session": other_sess,
    }


def _verify(store: PlatformStore, user_id: str, password: str) -> bool:
    from saathi.platform.identity import verify_password_scrypt

    cred = store.get_credential(user_id) or {}
    return verify_password_scrypt(password, cred.get("password_hash") or "")


def _active_sessions(store: PlatformStore, user_id: str) -> int:
    return len(store.list_sessions(user_id))


def _run_reset(monkeypatch, email, *, password=NEW_PASSWORD, confirm=None, tty=True):
    replies = iter([password, confirm if confirm is not None else password])
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_a, **_k: next(replies))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: tty, raising=False)
    return cli.main(["reset-local-password", "--email", email])


@pytest.fixture(autouse=True)
def _use_temp_store(monkeypatch, store):
    """Point the CLI at the throwaway store, never the real platform.db."""
    monkeypatch.setattr(cli, "PlatformStore", lambda *_a, **_k: store)


def test_reset_sets_the_new_password(monkeypatch, capsys, seeded, store):
    rc = _run_reset(monkeypatch, "owner@test.local")
    assert rc == cli.EXIT_OK
    assert _verify(store, seeded["owner"].user_id, NEW_PASSWORD) is True


def test_old_password_stops_working(monkeypatch, seeded, store):
    _run_reset(monkeypatch, "owner@test.local")
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is False


def test_existing_sessions_for_that_user_are_revoked(monkeypatch, seeded, store):
    assert _active_sessions(store, seeded["owner"].user_id) == 1
    _run_reset(monkeypatch, "owner@test.local")
    assert _active_sessions(store, seeded["owner"].user_id) == 0


def test_other_users_are_untouched(monkeypatch, seeded, store):
    other_id = seeded["other"].user_id
    _run_reset(monkeypatch, "owner@test.local")

    # Credential unchanged, and their session survives.
    assert _verify(store, other_id, OLD_PASSWORD) is True
    assert _verify(store, other_id, NEW_PASSWORD) is False
    assert _active_sessions(store, other_id) == 1


def test_rbac_and_workspace_bindings_are_unchanged(monkeypatch, seeded, store):
    org_id = seeded["org"].org_id
    before = {
        "owner_role": store.membership_role(org_id, seeded["owner"].user_id),
        "other_role": store.membership_role(org_id, seeded["other"].user_id),
        "workspace_org": store.get_workspace(seeded["ws"].workspace_id).org_id,
        "status": store.get_user(seeded["owner"].user_id).status,
    }
    _run_reset(monkeypatch, "owner@test.local")
    after = {
        "owner_role": store.membership_role(org_id, seeded["owner"].user_id),
        "other_role": store.membership_role(org_id, seeded["other"].user_id),
        "workspace_org": store.get_workspace(seeded["ws"].workspace_id).org_id,
        "status": store.get_user(seeded["owner"].user_id).status,
    }
    assert before == after
    assert after["owner_role"] == "owner"
    assert after["other_role"] == "operator"


def test_password_and_hash_never_appear_in_output_or_audit(monkeypatch, capsys, seeded, store):
    _run_reset(monkeypatch, "owner@test.local")
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert NEW_PASSWORD not in blob
    assert OLD_PASSWORD not in blob

    stored_hash = (store.get_credential(seeded["owner"].user_id) or {}).get("password_hash") or ""
    assert stored_hash
    assert stored_hash not in blob
    # A scrypt record is salt$hash; make sure no fragment of it leaked either.
    for fragment in [p for p in stored_hash.split("$") if len(p) > 8]:
        assert fragment not in blob

    # The audit trail records that a password was set, never the material.
    rows = store._conn.execute(
        "SELECT event, detail FROM audit_events ORDER BY rowid DESC LIMIT 20"
    ).fetchall()
    audit_blob = " ".join(f"{r['event']} {r['detail']}" for r in rows)
    assert "credential.password_set" in audit_blob
    assert NEW_PASSWORD not in audit_blob
    assert OLD_PASSWORD not in audit_blob
    assert stored_hash not in audit_blob


def test_unknown_user_fails_without_changing_anything(monkeypatch, seeded, store):
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "nobody@test.local")
    assert exc.value.code == cli.EXIT_NOT_FOUND
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True
    assert _active_sessions(store, seeded["owner"].user_id) == 1


def test_schema_prevents_duplicate_emails(seeded, store):
    """The first line of defence: the database will not hold two rows per email."""
    dup = seeded["owner"]
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "INSERT INTO users (user_id, email, name, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            ("usr_duplicate_row", dup.email, "Dupe", "active", 0, 0),
        )


def test_ambiguous_match_refuses_to_guess(store):
    """The second line of defence.

    A UNIQUE constraint makes duplicates unreachable through SQL today, so the
    guard is exercised directly. If that constraint is ever relaxed, the CLI must
    still refuse rather than silently re-credential whichever row came back first.
    """

    class _TwoMatches:
        def list_users(self):
            class _U:
                def __init__(self, uid):
                    self.user_id = uid
                    self.email = "owner@test.local"
                    self.status = "active"

            return [_U("usr_one"), _U("usr_two")]

    with pytest.raises(SystemExit) as exc:
        cli._resolve_user(_TwoMatches(), "owner@test.local")
    assert exc.value.code == cli.EXIT_AMBIGUOUS


def test_mismatched_confirmation_changes_nothing(monkeypatch, seeded, store):
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "owner@test.local", confirm="Different-Passw0rd!x")
    assert exc.value.code == cli.EXIT_POLICY
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True


def test_empty_password_is_rejected(monkeypatch, seeded, store):
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "owner@test.local", password="   ")
    assert exc.value.code == cli.EXIT_POLICY
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True


@pytest.mark.parametrize("weak", ["short1!", "password", "12345678901", "abcdefghijk"])
def test_weak_passwords_are_rejected_by_the_canonical_policy(monkeypatch, seeded, store, weak):
    rc = _run_reset(monkeypatch, "owner@test.local", password=weak)
    assert rc == cli.EXIT_POLICY
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True


def test_non_interactive_stdin_is_refused(monkeypatch, seeded, store):
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "owner@test.local", tty=False)
    assert exc.value.code == cli.EXIT_USAGE
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True


def test_refuses_when_production_is_authorized(monkeypatch, seeded, store):
    class _Cfg:
        production_authorized = True
        public_exposure_authorized = False

    monkeypatch.setattr(cli, "load_config", lambda *_a, **_k: _Cfg())
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "owner@test.local")
    assert exc.value.code == cli.EXIT_REFUSED
    assert _verify(store, seeded["owner"].user_id, OLD_PASSWORD) is True


def test_refuses_when_public_exposure_is_authorized(monkeypatch, seeded, store):
    class _Cfg:
        production_authorized = False
        public_exposure_authorized = True

    monkeypatch.setattr(cli, "load_config", lambda *_a, **_k: _Cfg())
    with pytest.raises(SystemExit) as exc:
        _run_reset(monkeypatch, "owner@test.local")
    assert exc.value.code == cli.EXIT_REFUSED


def test_email_is_required(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        cli.main(["reset-local-password"])
    assert exc.value.code == cli.EXIT_USAGE


def test_login_succeeds_with_the_new_password_after_reset(monkeypatch, seeded, store):
    """End to end: the whole point of the command."""
    _run_reset(monkeypatch, "owner@test.local")
    svc = PlatformService(store)

    result = svc.authenticate_login(email="owner@test.local", password=NEW_PASSWORD)
    assert result.get("token")

    with pytest.raises(Exception):
        svc.authenticate_login(email="owner@test.local", password=OLD_PASSWORD)
