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
from pathlib import Path

from saathi.connectors.catalog import PROVIDERS

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
            scopes: list | None = None, secret: dict | None = None, status: str = "connected") -> dict:
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
        with self._conn() as c:
            return c.execute("UPDATE account SET status=?, token_expiry=COALESCE(?, token_expiry) WHERE id=?",
                             (status, token_expiry, aid)).rowcount > 0

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
