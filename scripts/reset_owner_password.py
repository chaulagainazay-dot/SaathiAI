#!/usr/bin/env python3
"""Local owner password reset — LOCAL OPERATOR ONLY.

Runs on the machine, never listens on a network port, never echoes or stores the
password beyond the canonical credential sources the app already uses (the
security store's PBKDF2 hash + the .env BAADAR_PASSWORD line). Existing
PBKDF2-600k verification and the auth state machine are unchanged.

A reset intentionally replaces the owner credential, so it REVOKES all active
password/browser sessions (this doubles as the explicit, owner-invoked historical
session collapse) and flips the session-cap migration marker. Service / API
credentials (api_tokens table, SAATHI_TOKEN) are SEPARATE and untouched.

Usage:
  python scripts/reset_owner_password.py --report        # show impact, change nothing
  python scripts/reset_owner_password.py                 # interactive reset (getpass)

Env overrides (for isolated/temp verification only):
  SAATHI_SECURITY_DB=<path>   redirect the security store
  SAATHI_ENV_FILE=<path>      redirect the .env written to
"""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path

# Always import THIS repo's saathi package, not an installed/egg copy — a script
# run as `python scripts/...` puts scripts/ (not the repo root) on sys.path[0].
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _impact():
    from saathi import sessions
    c = sessions.counts()
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="Local owner password reset (local operator only).")
    ap.add_argument("--report", action="store_true", help="show session impact only; make no changes")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--password-stdin", action="store_true",
                    help="read the new password from stdin (isolated/automated verification only)")
    args = ap.parse_args()

    from saathi import config, authsec, sessions
    from saathi.security.store import get_store

    store = get_store()
    owner = store.get_or_create_owner()
    c = _impact()
    active = c["active"]
    print(f"[reset] owner={owner[:8]}...  active_sessions={active}  expired={c['expired']}  revoked={c['revoked']}")
    print(f"[reset] a reset will REVOKE all {active} active password/browser sessions (credential replaced).")
    print("[reset] service/API credentials (api_tokens, SAATHI_TOKEN) are SEPARATE and NOT affected.")
    print("[reset] this also serves as the explicit historical session collapse + cap-policy activation.")
    if args.report:
        print("[reset] --report only: NO changes made.")
        return 0

    if args.password_stdin:
        pw = sys.stdin.readline().rstrip("\n")
        pw2 = pw
    else:
        if not sys.stdin.isatty():
            print("[reset] ERROR: interactive terminal required (or use --password-stdin).", file=sys.stderr)
            return 2
        pw = getpass.getpass("New owner password: ")
        pw2 = getpass.getpass("Confirm new password: ")
    if not pw or pw != pw2:
        print("[reset] ERROR: passwords empty or do not match.", file=sys.stderr)
        return 2
    strength = authsec.password_strength(pw)
    if strength["score"] < 2:
        print("[reset] ERROR: password too weak — use 8+ chars with upper, lower, number, symbol.", file=sys.stderr)
        return 3

    if not args.yes:
        confirm = input(f"Type RESET to set a new password and revoke {active} sessions: ")
        if confirm.strip() != "RESET":
            print("[reset] aborted; no changes made.")
            return 1

    # 1. store credential — the live source of truth; the new password works immediately.
    store.save_password(owner, authsec.hash_password(pw), strength["score"])
    # 2. .env canonical source — persistence across restart; the old env-derived
    #    hash is dropped from server memory only on the next backend restart.
    env_file = Path(os.environ.get("SAATHI_ENV_FILE", str(config.ROOT / ".env")))
    text = env_file.read_text() if env_file.exists() else ""
    if re.search(r"^BAADAR_PASSWORD=", text, flags=re.M):
        text = re.sub(r"^BAADAR_PASSWORD=.*$", f"BAADAR_PASSWORD={pw}", text, flags=re.M)
    else:
        text = (text.rstrip("\n") + "\n" if text else "") + f"BAADAR_PASSWORD={pw}\n"
    env_file.write_text(text)
    # 3. revoke every session (credential replaced) + activate cap policy.
    revoked = sessions.revoke_all_including_current()
    sessions.mark_policy_migrated()
    pruned = sessions.prune()
    # 4. audit — never records the secret.
    try:
        authsec.audit("owner_password_reset", ok=True, ip="local-cli",
                      ua="reset_owner_password.py", detail=f"revoked_{revoked}")
    except Exception:
        pass
    # scrub locals holding the plaintext
    pw = pw2 = text = None
    del pw, pw2, text

    after = _impact()
    print(f"[reset] DONE. credential updated (store + .env). revoked {revoked} sessions; pruned {pruned}.")
    print(f"[reset] sessions now: active={after['active']} expired={after['expired']} revoked={after['revoked']}")
    print("[reset] RESTART the backend so the previous env-derived password leaves memory:")
    print("        launchctl kickstart -k gui/$(id -u)/com.saathi.local")
    print("[reset] then sign in at http://localhost:3100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
