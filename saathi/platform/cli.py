"""Local owner-recovery CLI for the SaathiOS private alpha.

Deliberately thin. Every security decision already lives in
``PlatformService.set_password``: the password policy, the canonical scrypt
hash, the single-user credential write, revocation of that user's sessions, and
the audit event. This module adds only the three things a CLI must own —

  * a private-alpha gate, so recovery cannot run against an authorized
    production or publicly-exposed deployment;
  * unambiguous resolution of one target user from an explicit email;
  * collecting the new password twice without echoing it.

It must never print, log, return or persist a password or a password hash.
Nothing here changes a role, organization, workspace, membership or permission.

Usage:
    python -m saathi.platform.cli reset-local-password --email owner@e2e.local
"""

from __future__ import annotations

import argparse
import getpass
import sys

import saathi.platform.alpha  # noqa: F401  (patches set_password onto PlatformService)
from saathi.platform.context import PlatformContextError
from saathi.platform.private_alpha.config import load_config
from saathi.platform.service import PlatformService
from saathi.platform.store import PlatformStore

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_NOT_FOUND = 4
EXIT_AMBIGUOUS = 5
EXIT_POLICY = 6

# Reasons returned by password_policy_check, rendered without echoing the input.
_POLICY_HELP = {
    "password_too_short": "too short",
    "password_trivial": "too common",
    "password_complexity": "needs at least 3 of: lowercase, uppercase, digit, symbol",
}


def _err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _require_private_alpha() -> None:
    """Refuse to run anywhere that has been authorized beyond private alpha."""
    cfg = load_config()
    if getattr(cfg, "production_authorized", False):
        raise SystemExit(_refuse("production_authorized is true; local recovery is refused"))
    if getattr(cfg, "public_exposure_authorized", False):
        raise SystemExit(_refuse("public_exposure_authorized is true; local recovery is refused"))


def _refuse(message: str) -> int:
    _err(message)
    return EXIT_REFUSED


def _resolve_user(store: PlatformStore, email: str):
    """Resolve exactly one user, or fail loudly.

    An email is expected to be unique. If the table ever holds more than one row
    for it, refuse rather than silently picking the first — guessing which
    account to re-credential is exactly the wrong move.
    """
    matches = [u for u in store.list_users() if (u.email or "").lower() == email.lower()]
    if not matches:
        _err(f"no user with email {email!r}")
        known = sorted((u.email or "") for u in store.list_users())
        if known:
            _err("known emails: " + ", ".join(known))
        raise SystemExit(EXIT_NOT_FOUND)
    if len(matches) > 1:
        _err(f"{len(matches)} users match {email!r}; refusing to guess which to reset")
        raise SystemExit(EXIT_AMBIGUOUS)
    return matches[0]


def _prompt_new_password() -> str:
    """Read the new password twice, invisibly. Never echoed, never logged."""
    if not sys.stdin.isatty():
        _err("refusing to read a password from a non-interactive stdin")
        raise SystemExit(EXIT_USAGE)
    first = getpass.getpass("New password: ")
    if not first.strip():
        _err("empty password rejected")
        raise SystemExit(EXIT_POLICY)
    second = getpass.getpass("Confirm new password: ")
    if first != second:
        _err("passwords did not match; nothing was changed")
        raise SystemExit(EXIT_POLICY)
    return first


def cmd_reset_local_password(args: argparse.Namespace) -> int:
    _require_private_alpha()

    store = PlatformStore()
    user = _resolve_user(store, args.email)

    # Non-secret identity summary only. Never the hash, never a token.
    role = store.membership_role(args.org_id, user.user_id) if args.org_id else None
    if role is None:
        for m in _memberships_for(store, user.user_id):
            role = m
            break
    print(f"user id : {user.user_id}")
    print(f"email   : {user.email}")
    print(f"role    : {role or 'unknown'}")
    print(f"state   : {user.status}")

    password = _prompt_new_password()
    try:
        # Canonical path: policy check, scrypt hash, single-user write, session
        # revocation and audit all happen inside set_password.
        service = PlatformService(store)
        service.set_password(user.user_id, password, actor_id=user.user_id)
    except PlatformContextError as exc:
        if exc.code == "PASSWORD_POLICY":
            _err(f"password rejected: {_POLICY_HELP.get(exc.message, exc.message)}")
            return EXIT_POLICY
        _err(f"password not changed: {exc.code}")
        return EXIT_REFUSED
    finally:
        del password

    print("password updated; all sessions for this user were revoked")
    print("role, organization, workspace, membership and permissions unchanged")
    return EXIT_OK


def _memberships_for(store: PlatformStore, user_id: str):
    """Best-effort role lookup across orgs, for display only."""
    try:
        rows = store._conn.execute(  # noqa: SLF001 - read-only display lookup
            "SELECT role FROM memberships WHERE user_id=?", (user_id,)
        ).fetchall()
        return [r["role"] for r in rows]
    except Exception:
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m saathi.platform.cli",
        description="Local private-alpha platform maintenance commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    reset = sub.add_parser(
        "reset-local-password",
        help="Reset one local user's password (private alpha only).",
    )
    reset.add_argument(
        "--email",
        required=True,
        help="Exact email of the user to reset. Required; never inferred.",
    )
    reset.add_argument(
        "--org-id",
        default="",
        help="Optional org id, used only to display the user's role.",
    )
    reset.set_defaults(func=cmd_reset_local_password)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
