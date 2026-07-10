"""Security Timeline — append-only event log for security-related activity.

Follows the same philosophy as Mission Timeline (saathi.missions.timeline):
- Never mutated, only appended
- Kinds define the vocabulary of security history
- Metadata stores structured details as JSON

Integrates with the Security Dashboard to show:
- Password changed
- Passkey added/removed
- Session created/revoked/rotated
- Login success/failure
- Token created/revoked
- OAuth connected/disconnected
"""
from __future__ import annotations

from saathi.security.store import SecurityStore, get_store


EVENT_KINDS = frozenset({
    "password_changed",
    "password_reset",
    "passkey_added",
    "passkey_removed",
    "passkey_renamed",
    "session_created",
    "session_revoked",
    "session_rotated",
    "login_success",
    "login_failed",
    "logout",
    "logout_everywhere",
    "token_created",
    "token_revoked",
    "token_used",
    "oauth_connected",
    "oauth_disconnected",
    "security_setting_changed",
    "risk_alert",
})


class SecurityTimeline:
    def __init__(self, store: SecurityStore | None = None):
        self.store = store or get_store()

    def record(self, user_id: str, kind: str, title: str, *, detail: str = "",
               meta: dict | None = None, ip: str = "", ua: str = "") -> str:
        kind = kind if kind in EVENT_KINDS else "security_setting_changed"
        return self.store.event_record(user_id, kind, title, detail=detail,
                                       meta=meta, ip=ip, ua=ua)

    def list(self, user_id: str, *, kind: str | None = None, limit: int = 100) -> list[dict]:
        return self.store.event_list(user_id, kind=kind, limit=limit)

    def recent_kinds(self, user_id: str, kinds: list[str], limit: int = 20) -> list[dict]:
        placeholders = ",".join("?" * len(kinds))
        rows = self.store.db.execute(
            f"SELECT * FROM security_events WHERE user_id=? AND kind IN ({placeholders})"
            " ORDER BY timestamp DESC LIMIT ?",
            (user_id, *kinds, limit),
        ).fetchall()
        out = []
        import json
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except Exception:
                d["meta"] = {}
            out.append(d)
        return out


_default_timeline: SecurityTimeline | None = None


def get_timeline() -> SecurityTimeline:
    global _default_timeline
    if _default_timeline is None:
        _default_timeline = SecurityTimeline()
    return _default_timeline


def close_timeline() -> None:
    global _default_timeline
    _default_timeline = None
