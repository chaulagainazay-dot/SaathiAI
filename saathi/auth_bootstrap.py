"""First-owner bootstrap, and the authentication state machine around it.

Before this module, a freshly installed backend answered the question "who is
the owner?" with "whoever asked first". Two independent paths did it:

* ``POST /api/v1/auth/change-password`` sat on the middleware bypass list as a
  bare string compare, so with no password configured it required no session,
  minted an owner session, returned a bearer token, and wrote the plaintext
  credential into the checkout's ``.env``;
* ``_is_authed()`` fell through to ``_is_local()`` whenever no password was
  configured, so any loopback caller *was* the owner on every protected route.

Either one could then mint a durable credential -- an API token or a passkey --
and ``_is_authed`` checks the token registry *before* any freshness condition,
so that credential kept working after the real owner set a password. A transient
install window became permanent access.

The repair is a state machine with exactly one legitimate transition into an
owned system, and a rule that loopback is a transport condition, never an
identity.

  UNINITIALIZED              no owner, no credential, no marker
  BOOTSTRAP_ARMED            + operator explicitly armed bootstrap
  ACTIVE                     exactly one owner, scrypt credential, marker set
  CONTAMINATED_UNINITIALIZED marker absent but a credential already exists

``CONTAMINATED_UNINITIALIZED`` fails closed and is never silently cleaned:
deleting a planted credential would destroy the evidence of how it got there.
It requires an explicit operator recovery, which is deliberately not implemented
here.

Nothing in this module logs, returns or stores a token or a password. Callers
get states, bounded reason codes, and paths.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import pathlib
import secrets
import stat
import threading
import time
from enum import Enum

from saathi.platform.identity import (
    hash_password_scrypt,
    password_policy_check,
)

BOOTSTRAP_ENABLED_ENV = "SAATHI_BOOTSTRAP_ENABLED"
BOOTSTRAP_TOKEN_FILE_ENV = "SAATHI_BOOTSTRAP_TOKEN_FILE"
BOOTSTRAP_TOKEN_MAX_AGE_ENV = "SAATHI_BOOTSTRAP_TOKEN_MAX_AGE"

#: A bootstrap token is an operator artefact with a short life. The default is
#: deliberately short: the window exists to cover one deliberate setup, not to
#: sit armed on a machine indefinitely.
DEFAULT_TOKEN_MAX_AGE = 900.0

#: 32 bytes of entropy, hex or urlsafe-base64 encoded, is the floor. A short
#: token is refused rather than accepted-and-rate-limited: guessability is not
#: something a rate limiter can fix once the file is readable.
MIN_TOKEN_CHARS = 32

#: Attempts are counted against the real peer and the process, never against a
#: caller-supplied forwarding header -- the old change-password limiter keyed on
#: ``x-forwarded-for`` and was bypassable by varying one header.
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 900.0

_TRUE = {"1", "true", "yes", "on"}

_attempts: list[float] = []
_attempt_lock = threading.RLock()

#: Serialises bootstrap against credential minting *within this process*. The
#: authoritative guard is the database transaction below; this only narrows the
#: in-process race. See ``bootstrap_owner`` for the cross-process story.
initialization_lock = threading.RLock()


class AuthState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    BOOTSTRAP_ARMED = "BOOTSTRAP_ARMED"
    ACTIVE = "ACTIVE"
    CONTAMINATED_UNINITIALIZED = "CONTAMINATED_UNINITIALIZED"


class BootstrapError(Exception):
    """Refusal carrying a bounded machine code and no sensitive detail."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code
        self.message = message or code


def bootstrap_enabled() -> bool:
    return (os.getenv(BOOTSTRAP_ENABLED_ENV) or "").strip().lower() in _TRUE


def _token_max_age() -> float:
    raw = (os.getenv(BOOTSTRAP_TOKEN_MAX_AGE_ENV) or "").strip()
    if not raw:
        return DEFAULT_TOKEN_MAX_AGE
    try:
        value = float(raw)
    except ValueError:
        raise BootstrapError("BOOTSTRAP_TOKEN_MAX_AGE_INVALID")
    if value <= 0:
        raise BootstrapError("BOOTSTRAP_TOKEN_MAX_AGE_INVALID")
    return value


# ── state ───────────────────────────────────────────────────────────────────

def auth_state(store) -> AuthState:
    """Classify the store. Read-only; creates nothing.

    Order matters. ``ACTIVE`` is decided by the marker, so a system that has
    completed bootstrap can never be talked back into an initialisable state by
    deleting rows. Contamination is checked before ``UNINITIALIZED`` so a
    planted credential can never present as a clean install.
    """
    marker = store.bootstrap_completed()
    census = store.credential_census()
    if marker:
        return AuthState.ACTIVE

    planted = any(census[k] for k in
                  ("users", "passwords", "sessions", "api_tokens", "passkeys", "user_roles"))
    if planted:
        return AuthState.CONTAMINATED_UNINITIALIZED

    if bootstrap_enabled():
        return AuthState.BOOTSTRAP_ARMED
    return AuthState.UNINITIALIZED


def is_active(store) -> bool:
    """True only for a properly initialised system.

    Every credential-minting route asks this. A contaminated store answers
    False, so planting one credential does not unlock minting the next.
    """
    return auth_state(store) is AuthState.ACTIVE


def status(store) -> dict:
    """Bounded, non-secret status for the unlock UI."""
    state = auth_state(store)
    return {
        "state": state.value,
        "bootstrap_available": state is AuthState.BOOTSTRAP_ARMED,
        "bootstrap_enabled": bootstrap_enabled(),
        "requires_operator_token": True,
    }


# ── operator proof ──────────────────────────────────────────────────────────

def _read_token_file() -> tuple[str, pathlib.Path]:
    """Validate the operator token file and return its contents.

    Every check here is about the file being a deliberate operator artefact
    rather than something an attacker could drop or point at:

    * an absolute path, so it cannot be resolved against a working directory a
      caller influences;
    * a real regular file opened without following a symlink, so a link cannot
      aim the read at a file the operator never wrote (``O_NOFOLLOW`` on the
      open, not a ``lstat`` beforehand -- the check and the open must be the
      same operation or they race);
    * mode exactly ``0600`` and owned by this process's uid, so it is not
      readable by another account;
    * young enough to be part of the setup happening now.
    """
    raw_path = (os.getenv(BOOTSTRAP_TOKEN_FILE_ENV) or "").strip()
    if not raw_path:
        raise BootstrapError("BOOTSTRAP_TOKEN_FILE_UNSET")
    path = pathlib.Path(raw_path)
    if not path.is_absolute():
        raise BootstrapError("BOOTSTRAP_TOKEN_FILE_NOT_ABSOLUTE")

    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise BootstrapError("BOOTSTRAP_TOKEN_FILE_MISSING")
    except OSError as exc:
        # ELOOP is what O_NOFOLLOW raises for a symlink.
        raise BootstrapError("BOOTSTRAP_TOKEN_FILE_UNREADABLE", type(exc).__name__)

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise BootstrapError("BOOTSTRAP_TOKEN_FILE_NOT_REGULAR")
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise BootstrapError("BOOTSTRAP_TOKEN_FILE_INSECURE_MODE")
        if st.st_uid != os.getuid():
            raise BootstrapError("BOOTSTRAP_TOKEN_FILE_WRONG_OWNER")
        age = time.time() - st.st_mtime
        if age > _token_max_age():
            raise BootstrapError("BOOTSTRAP_TOKEN_EXPIRED")
        with os.fdopen(os.dup(fd), "r") as fh:
            token = fh.read().strip()
    finally:
        os.close(fd)

    if len(token) < MIN_TOKEN_CHARS:
        raise BootstrapError("BOOTSTRAP_TOKEN_TOO_WEAK")
    return token, path


def _rate_check() -> None:
    """Count attempts against this process, not against anything a caller sends."""
    now = time.time()
    with _attempt_lock:
        _attempts[:] = [t for t in _attempts if now - t < ATTEMPT_WINDOW]
        if len(_attempts) >= MAX_ATTEMPTS:
            raise BootstrapError("BOOTSTRAP_RATE_LIMITED")
        _attempts.append(now)


def reset_rate_limit_for_tests() -> None:
    with _attempt_lock:
        _attempts.clear()


def verify_operator_proof(presented: str) -> pathlib.Path:
    """Constant-time check of the presented token against the file's."""
    expected, path = _read_token_file()
    presented = (presented or "").strip()
    if not presented:
        raise BootstrapError("BOOTSTRAP_TOKEN_MISSING")
    # Compare digests so the comparison is fixed-length regardless of input.
    a = hashlib.sha256(presented.encode()).digest()
    b = hashlib.sha256(expected.encode()).digest()
    if not hmac.compare_digest(a, b):
        raise BootstrapError("BOOTSTRAP_TOKEN_INVALID")
    return path


def quarantine_token_file(path: pathlib.Path) -> pathlib.Path | None:
    """Consume the token file after a successful bootstrap.

    Renamed rather than deleted: the operator should be able to see that it was
    used, and a failed unlink must not leave a live token behind quietly. The
    value is never read again.
    """
    try:
        used = path.with_name(path.name + ".used")
        os.replace(str(path), str(used))
        os.chmod(str(used), 0o600)
        return used
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        return None


# ── the transition ──────────────────────────────────────────────────────────

def bootstrap_owner(store, *, password: str, operator_token: str,
                    email: str = "", name: str = "Owner") -> str:
    """Create the one first owner atomically. Returns the owner id.

    Concurrency: the whole thing runs inside ``BEGIN IMMEDIATE``, which takes
    SQLite's write lock before the state is re-read. Two racing callers
    therefore serialise at the database, and the loser re-reads a store that
    already has the marker and is refused -- so "exactly one winner" holds
    across processes, not merely across threads in one process.

    No session is minted here. The caller issues one only after this returns,
    which is what keeps a failed transaction from leaving a usable credential
    behind.
    """
    # The whole decision, preflight included, runs under one process lock. The
    # database transaction below is the cross-process guard, but the preflight
    # reads share the store's single connection, and two threads interleaving
    # cursors on one sqlite3 connection is undefined behaviour rather than a
    # race the transaction can settle.
    with initialization_lock:
        return _bootstrap_locked(store, password=password,
                                 operator_token=operator_token,
                                 email=email, name=name)


def _bootstrap_locked(store, *, password: str, operator_token: str,
                      email: str, name: str) -> str:
    _rate_check()

    if not bootstrap_enabled():
        raise BootstrapError("BOOTSTRAP_DISABLED")

    state = auth_state(store)
    if state is AuthState.ACTIVE:
        raise BootstrapError("BOOTSTRAP_ALREADY_COMPLETE")
    if state is AuthState.CONTAMINATED_UNINITIALIZED:
        raise BootstrapError("BOOTSTRAP_CONTAMINATED_STATE")

    ok, reason = password_policy_check(password)
    if not ok:
        raise BootstrapError("BOOTSTRAP_PASSWORD_POLICY", reason)

    token_path = verify_operator_proof(operator_token)

    # Hash before opening the transaction: scrypt is deliberately slow and must
    # not be done while holding the database write lock.
    pw_hash = hash_password_scrypt(password)
    owner_id = secrets.token_hex(16)
    now = time.time()

    db = store.db
    if True:
        db.execute("BEGIN IMMEDIATE")
        try:
            # Re-read under the write lock. Anything that appeared between the
            # preflight above and this point loses here.
            if db.execute("SELECT 1 FROM bootstrap_marker WHERE id=1").fetchone():
                raise BootstrapError("BOOTSTRAP_ALREADY_COMPLETE")
            for table in ("users", "passwords", "sessions", "api_tokens", "passkeys"):
                if db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise BootstrapError("BOOTSTRAP_CONTAMINATED_STATE")

            db.execute(
                "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?,?,?,?,?)",
                (owner_id, email or None, name or None, now, now),
            )
            db.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
                (owner_id, "role-owner", now),
            )
            db.execute(
                "INSERT INTO passwords (user_id, hash, strength_score, created_at) VALUES (?,?,?,?)",
                (owner_id, pw_hash, 4, now),
            )
            db.execute(
                "INSERT INTO bootstrap_marker (id, completed_at, owner_id, method) "
                "VALUES (1,?,?,?)",
                (now, owner_id, "operator_token"),
            )
            db.execute(
                "INSERT INTO audit_log (timestamp, event, ok, user_id, ip_address, "
                "user_agent, detail, session_id) VALUES (?,?,?,?,?,?,?,?)",
                (now, "bootstrap_owner_created", 1, owner_id, "loopback", "",
                 "first owner created via operator token", ""),
            )
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    # Only now that the owner is durably committed is the operator token spent.
    quarantine_token_file(token_path)
    return owner_id
