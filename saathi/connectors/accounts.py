"""Account Manager — the universal, provider-independent account registry.

One account (a Gmail login, a YouTube channel, a Stripe key) can be shared across
many Missions; one Mission can use many accounts. Credentials are ENCRYPTED at rest
(Fernet, key in ~/.saathi, gitignored) and never returned by the API or stored in
Git. Everything above (Connectors, Directors) references an account by id and asks
the manager to use it — they never see the raw secret.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from enum import Enum
from pathlib import Path

from saathi.connectors.catalog import PROVIDERS


class AccountStatus(str, Enum):
    """What is actually known about an account — not what was hoped.

    PERSISTENCE IS NOT VERIFICATION. A row in this table proves that
    CONFIGURATION EXISTS. It says nothing about whether the provider accepted
    the credential, so creation cannot mint CONNECTED.
    """

    #: Configuration stored, provider has not confirmed anything. The default.
    AUTH_REQUIRED = "auth_required"
    #: A provider verification actually succeeded. Only `mark_verified` sets it.
    CONNECTED = "connected"
    #: The provider has no live adapter, so nothing can be confirmed against it.
    #: Simulated capabilities may dispatch; a real external call may not.
    SIMULATED = "simulated"
    #: Previously verified, credential has aged out.
    EXPIRED = "expired"
    #: Provider actively rejected the credential.
    REVOKED = "revoked"
    #: The record cannot be used as written (missing field, wrong shape).
    MISCONFIGURED = "misconfigured"
    #: Switched off by an operator.
    DISABLED = "disabled"


#: Statuses a caller may set directly. CONNECTED is absent on purpose: it is
#: reachable only through `mark_verified`, which demands provider evidence.
CALLER_SETTABLE_STATUSES = frozenset({
    AccountStatus.AUTH_REQUIRED.value,
    AccountStatus.SIMULATED.value,
    AccountStatus.EXPIRED.value,
    AccountStatus.REVOKED.value,
    AccountStatus.MISCONFIGURED.value,
    AccountStatus.DISABLED.value,
})

_DB = Path.home() / ".saathi" / "accounts.db"
_KEY = Path.home() / ".saathi" / ".connector_key"

_COLUMNS = ["id", "provider", "display_name", "email", "owner", "auth_type", "scopes",
            "missions", "status", "created", "last_sync", "last_used", "token_expiry", "refresh_status"]
_JSON = {"scopes", "missions"}


def _fernet():
    from cryptography.fernet import Fernet
    _KEY.parent.mkdir(parents=True, exist_ok=True)
    if not _KEY.exists():
        _KEY.write_bytes(Fernet.generate_key())
        try:
            _KEY.chmod(0o600)
        except Exception:
            pass
    return Fernet(_KEY.read_bytes())


class AccountStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else _DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            cols = ", ".join(f"{col} {'REAL' if col in ('created','last_sync','last_used','token_expiry') else 'TEXT'}"
                             for col in _COLUMNS)
            c.execute(f"CREATE TABLE IF NOT EXISTS account({cols}, secret_enc BLOB, PRIMARY KEY(id))")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def add(self, *, provider: str, display_name: str = "", email: str = "", owner: str = "ajay",
            scopes: list | None = None, secret: dict | None = None,
            status: str | None = None) -> dict:
        """Register an account. It is NOT connected until a provider says so.

        This used to default to ``status="connected"``, so storing a credential
        was enough to claim the provider had accepted it — a green light that no
        external system had ever agreed to. Creation now lands in AUTH_REQUIRED,
        and CONNECTED is unreachable from here: it is minted only by
        `mark_verified`, which requires evidence from an adapter.
        """
        status = AccountStatus.AUTH_REQUIRED.value if status is None else str(status)
        if status == AccountStatus.CONNECTED.value:
            raise ValueError(
                "CONNECTED cannot be claimed at creation — call mark_verified() "
                "with the provider's verification result, or restore_verified() "
                "for a record that was already verified elsewhere"
            )
        if status not in CALLER_SETTABLE_STATUSES:
            raise ValueError(
                f"unknown account status {status!r}; expected one of "
                f"{sorted(CALLER_SETTABLE_STATUSES)}"
            )
        provider = provider if provider in PROVIDERS else provider
        auth_type = PROVIDERS.get(provider, ("", "none"))[1]
        aid = uuid.uuid4().hex[:16]
        enc = _fernet().encrypt(json.dumps(secret or {}).encode()) if secret else None
        now = time.time()
        row = (aid, provider, display_name or provider, email, owner, auth_type,
               json.dumps(scopes or []), json.dumps([]), status, now, None, None, None, "n/a", enc)
        with self._conn() as c:
            c.execute(f"INSERT INTO account({','.join(_COLUMNS)}, secret_enc) "
                      f"VALUES({','.join('?'*(len(_COLUMNS)+1))})", row)
        return self.get(aid)

    def get(self, aid: str, *, with_secret: bool = False) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + ", secret_enc FROM account WHERE id=?", (aid,)).fetchone()
        if not r:
            return None
        d = _row(r[:-1])
        d["has_secret"] = r[-1] is not None
        if with_secret and r[-1]:
            try:
                d["secret"] = json.loads(_fernet().decrypt(r[-1]).decode())
            except Exception:
                d["secret"] = {}
        return d

    def list(self, *, provider: str = "", mission: str = "") -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT " + ",".join(_COLUMNS) + ", secret_enc FROM account ORDER BY created DESC").fetchall()
        out = []
        for r in rows:
            d = _row(r[:-1]); d["has_secret"] = r[-1] is not None
            if provider and d["provider"] != provider:
                continue
            if mission and mission not in d["missions"]:
                continue
            out.append(d)
        return out

    def link_mission(self, aid: str, mission_key: str, on: bool = True) -> bool:
        a = self.get(aid)
        if not a:
            return False
        m = set(a["missions"])
        m.add(mission_key) if on else m.discard(mission_key)
        with self._conn() as c:
            return c.execute("UPDATE account SET missions=? WHERE id=?",
                             (json.dumps(sorted(m)), aid)).rowcount > 0

    def set_status(self, aid: str, status: str, *, token_expiry: float | None = None) -> bool:
        """Move an account to a NON-connected state.

        Downgrades need no evidence — a provider saying "revoked" is itself the
        evidence, and failing closed never needs justifying. Reaching CONNECTED
        goes through `mark_verified`.
        """
        if status == AccountStatus.CONNECTED.value:
            raise ValueError("use mark_verified() to reach CONNECTED — it requires provider evidence")
        return self._write_status(aid, status, token_expiry=token_expiry)

    def _write_status(self, aid: str, status: str, *, token_expiry: float | None = None) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE account SET status=?, last_sync=?, "
                             "token_expiry=COALESCE(?, token_expiry) WHERE id=?",
                             (status, time.time(), token_expiry, aid)).rowcount > 0

    def mark_verified(self, aid: str, *, evidence: dict,
                      token_expiry: float | None = None) -> bool:
        """The ONLY route to CONNECTED. Requires a provider's own answer.

        `evidence` is whatever the adapter got back — Meta's page name, Telegram's
        getMe username. It is not inspected for content beyond being a non-empty
        mapping that reports success, because each provider answers differently;
        what matters is that SOMETHING came back from the provider and the caller
        is willing to record it.

        Fail-closed by construction: no response, a timeout, or a malformed reply
        gives the caller nothing truthy to pass, so the account cannot advance.
        """
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("provider evidence required to mark an account connected")
        if evidence.get("ok") is not True:
            raise ValueError(
                f"provider evidence does not report success: {evidence.get('error', 'ok!=True')}"
            )
        return self._write_status(aid, AccountStatus.CONNECTED.value, token_expiry=token_expiry)

    def mark_simulated(self, aid: str) -> bool:
        """The provider has no live adapter, so nothing can be verified against it.

        Distinct from CONNECTED on purpose. A simulated account may dispatch
        simulated capabilities, which have no external side effect; it must never
        read as a provider-verified connection.
        """
        return self._write_status(aid, AccountStatus.SIMULATED.value)

    def restore_verified(self, aid: str, *, reason: str) -> bool:
        """Re-assert CONNECTED for a record verified somewhere this process cannot see.

        The narrow, NAMED escape hatch: a migration or a restore of state that a
        provider really did verify. It exists so such callers announce themselves
        instead of reaching for the generic path, and `reason` is mandatory so the
        justification is written down at the call site.
        """
        if not reason or not str(reason).strip():
            raise ValueError("restore_verified() requires a reason naming the prior verification")
        return self._write_status(aid, AccountStatus.CONNECTED.value)

    def touch(self, aid: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE account SET last_used=? WHERE id=?", (time.time(), aid))

    def delete(self, aid: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM account WHERE id=?", (aid,)).rowcount > 0

    def health(self) -> dict:
        accts = self.list()
        now = time.time()
        expired = [a for a in accts if a["token_expiry"] and a["token_expiry"] < now]
        return {"total": len(accts), "connected": sum(1 for a in accts if a["status"] == "connected"),
                "expired": len(expired), "by_provider": _count(a["provider"] for a in accts)}


def _row(r) -> dict:
    d = dict(zip(_COLUMNS, r))
    for c in _JSON:
        try:
            d[c] = json.loads(d[c]) if d[c] else []
        except Exception:
            d[c] = []
    return d


def _count(it) -> dict:
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


_default = None
def default_store() -> AccountStore:
    global _default
    if _default is None:
        _default = AccountStore()
    return _default
