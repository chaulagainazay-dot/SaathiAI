"""M31 — Account-link registry.

An account link binds an owner scope + provider + connector(s) to a governed
credential reference and a set of *granted* scopes. It is the durable, metadata-only
record of "this owner has (or is trying to establish) access to this provider for
these connectors, with these scopes". It holds no secret values and never links a
live account — OAuth is driven by the fake-provider lifecycle only.

Readiness answers the connector-runtime question: may this connector execute on
behalf of this owner right now? It fails closed on missing/expired/quarantined
credentials, prohibited providers/scopes, and any non-LINKED status.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.models import (
    AccountLinkReadiness,
    AccountLinkStatus,
    CredentialStatus,
    is_prohibited_provider,
    is_prohibited_scope,
)
from saathi.credentials.scopes import validate_granted_scopes, validate_requested_scopes

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LINKS_PATH = ROOT / "docs" / "evidence" / "m31" / "account_links.json"
SCHEMA = "m31.account_link.v1"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


class AccountLinkError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


# Terminal / non-executable statuses.
_LIVE_READY = AccountLinkStatus.LINKED.value


@dataclass
class AccountLink:
    account_link_id: str
    owner_scope: str
    provider_id: str
    connector_ids: tuple[str, ...] = ()
    auth_profile: str = "none"
    requested_scopes: tuple[str, ...] = ()
    granted_scopes: tuple[str, ...] = ()
    credential_ref_id: str = ""
    oauth_session_id: str = ""
    status: str = AccountLinkStatus.UNLINKED.value
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""
    reason: str = ""
    quarantine_reason: str = ""
    metadata_safe: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.connector_ids, list):
            self.connector_ids = tuple(self.connector_ids)
        if isinstance(self.requested_scopes, list):
            self.requested_scopes = tuple(self.requested_scopes)
        if isinstance(self.granted_scopes, list):
            self.granted_scopes = tuple(self.granted_scopes)

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["connector_ids"] = list(self.connector_ids)
        d["requested_scopes"] = list(self.requested_scopes)
        d["granted_scopes"] = list(self.granted_scopes)
        d["schema"] = SCHEMA
        d["contains_secret_values"] = False
        return d


# Valid link-status transitions (fail-closed).
_TRANSITIONS: dict[str, frozenset[str]] = {
    AccountLinkStatus.UNLINKED.value: frozenset({
        AccountLinkStatus.LINK_REQUESTED.value, AccountLinkStatus.CANCELLED.value,
    }),
    AccountLinkStatus.LINK_REQUESTED.value: frozenset({
        AccountLinkStatus.AUTHORIZATION_PENDING.value, AccountLinkStatus.SCOPE_BLOCKED.value,
        AccountLinkStatus.CANCELLED.value, AccountLinkStatus.FAILED.value,
    }),
    AccountLinkStatus.AUTHORIZATION_PENDING.value: frozenset({
        AccountLinkStatus.LINKED.value, AccountLinkStatus.SCOPE_BLOCKED.value,
        AccountLinkStatus.FAILED.value, AccountLinkStatus.CANCELLED.value,
    }),
    AccountLinkStatus.LINKED.value: frozenset({
        AccountLinkStatus.EXPIRED.value, AccountLinkStatus.REAUTH_REQUIRED.value,
        AccountLinkStatus.REVOKED.value, AccountLinkStatus.FAILED.value,
    }),
    AccountLinkStatus.EXPIRED.value: frozenset({
        AccountLinkStatus.REAUTH_REQUIRED.value, AccountLinkStatus.REVOKED.value,
        AccountLinkStatus.LINK_REQUESTED.value,
    }),
    AccountLinkStatus.REAUTH_REQUIRED.value: frozenset({
        AccountLinkStatus.AUTHORIZATION_PENDING.value, AccountLinkStatus.REVOKED.value,
        AccountLinkStatus.LINK_REQUESTED.value, AccountLinkStatus.CANCELLED.value,
    }),
    AccountLinkStatus.SCOPE_BLOCKED.value: frozenset({
        AccountLinkStatus.LINK_REQUESTED.value, AccountLinkStatus.CANCELLED.value,
        AccountLinkStatus.REVOKED.value,
    }),
    AccountLinkStatus.FAILED.value: frozenset({
        AccountLinkStatus.LINK_REQUESTED.value, AccountLinkStatus.CANCELLED.value,
        AccountLinkStatus.REVOKED.value,
    }),
    AccountLinkStatus.CANCELLED.value: frozenset({AccountLinkStatus.LINK_REQUESTED.value}),
    AccountLinkStatus.REVOKED.value: frozenset(),
}


class AccountLinkRegistry:
    def __init__(
        self,
        *,
        broker: Any = None,
        path: Optional[Path] = None,
        persist: bool = True,
        event_sink: Optional[Callable[[str, dict], None]] = None,
    ):
        self.broker = broker
        self.path = Path(path) if path else DEFAULT_LINKS_PATH
        self.persist = persist
        self.event_sink = event_sink
        self._links: dict[str, AccountLink] = {}
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        if persist and self.path.is_file():
            self._load()

    def _emit(self, event_type: str, payload: dict) -> None:
        self._events.append({
            "schema": "m31.account_link_event.v1",
            "event_type": event_type,
            "ts": _utc(),
            "payload": payload,
            "privacy_safe": True,
            "contains_secret_values": False,
        })
        if self.event_sink:
            try:
                self.event_sink(event_type, payload)
            except Exception:
                pass

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for lid, raw in (data.get("account_links") or {}).items():
                self._links[lid] = AccountLink(**{
                    k: raw[k] for k in AccountLink.__dataclass_fields__ if k in raw
                })
        except Exception:
            self._links = {}

    def _save(self) -> None:
        if not self.persist:
            return
        payload = {
            "schema": SCHEMA,
            "account_links": {k: v.to_safe_dict() for k, v in sorted(self._links.items())},
            "live_accounts_linked": 0,
            "real_oauth_flows_completed": 0,
            "privacy_safe": True,
            "contains_secret_values": False,
        }
        _atomic_write(self.path, payload)

    def _transition(self, link: AccountLink, target: str) -> None:
        cur = link.status
        if target == cur:
            return
        if target not in _TRANSITIONS.get(cur, frozenset()):
            raise AccountLinkError("illegal_link_transition", f"{cur}->{target}")
        link.status = target
        link.updated_at = _utc()

    def _require(self, account_link_id: str, *, owner_scope: str = "") -> AccountLink:
        link = self._links.get(account_link_id)
        if link is None:
            raise AccountLinkError("unknown_account_link")
        if owner_scope and link.owner_scope != owner_scope:
            self._emit("account_link.cross_owner_denied", {"account_link_id": account_link_id})
            raise AccountLinkError("cross_owner_denied")
        return link

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def request_link(
        self,
        *,
        owner_scope: str,
        provider_id: str,
        connector_ids: tuple[str, ...] = (),
        auth_profile: str = "none",
        requested_scopes: tuple[str, ...] = (),
        allowed_scopes: tuple[str, ...] = (),
    ) -> AccountLink:
        if is_prohibited_provider(provider_id):
            raise AccountLinkError("PROHIBITED_PROVIDER", provider_id)
        decision = validate_requested_scopes(
            tuple(requested_scopes), allowed_scopes=tuple(allowed_scopes)
        )
        lid = "alink_" + uuid.uuid4().hex[:16]
        link = AccountLink(
            account_link_id=lid,
            owner_scope=owner_scope,
            provider_id=provider_id,
            connector_ids=tuple(connector_ids),
            auth_profile=auth_profile,
            requested_scopes=tuple(requested_scopes),
            status=AccountLinkStatus.LINK_REQUESTED.value,
            created_at=_utc(),
            updated_at=_utc(),
        )
        if not decision.allowed:
            link.status = AccountLinkStatus.SCOPE_BLOCKED.value
            link.reason = decision.reason
        with self._lock:
            self._links[lid] = link
            self._save()
        self._emit("account_link.requested", {
            "account_link_id": lid, "owner_scope": owner_scope,
            "provider_id": provider_id, "status": link.status,
        })
        return link

    def mark_authorization_pending(self, account_link_id: str, *, oauth_session_id: str = "", owner_scope: str = "") -> AccountLink:
        link = self._require(account_link_id, owner_scope=owner_scope)
        self._transition(link, AccountLinkStatus.AUTHORIZATION_PENDING.value)
        if oauth_session_id:
            link.oauth_session_id = oauth_session_id
        with self._lock:
            self._save()
        return link

    def complete_link(
        self,
        account_link_id: str,
        *,
        granted_scopes: tuple[str, ...],
        credential_ref_id: str,
        expires_at: str = "",
        owner_scope: str = "",
    ) -> AccountLink:
        """Bind a governed credential + granted scopes to the link. Rejects scope
        expansion beyond the requested set and prohibited scopes (fail-closed)."""
        link = self._require(account_link_id, owner_scope=owner_scope)
        decision = validate_granted_scopes(link.requested_scopes, tuple(granted_scopes))
        if not decision.allowed:
            link.reason = decision.reason
            self._transition(link, AccountLinkStatus.SCOPE_BLOCKED.value)
            with self._lock:
                self._save()
            self._emit("account_link.scope_blocked", {
                "account_link_id": account_link_id, "reason": decision.reason,
            })
            raise AccountLinkError(decision.reason, ",".join(decision.expanded or decision.prohibited))
        link.granted_scopes = tuple(granted_scopes)
        link.credential_ref_id = credential_ref_id
        link.expires_at = expires_at
        self._transition(link, AccountLinkStatus.LINKED.value)
        with self._lock:
            self._save()
        self._emit("account_link.linked", {
            "account_link_id": account_link_id,
            "credential_ref_id": credential_ref_id,
            "granted_scopes": list(granted_scopes),
        })
        return link

    def mark_expired(self, account_link_id: str, *, owner_scope: str = "") -> AccountLink:
        link = self._require(account_link_id, owner_scope=owner_scope)
        self._transition(link, AccountLinkStatus.EXPIRED.value)
        with self._lock:
            self._save()
        return link

    def require_reauth(self, account_link_id: str, *, reason: str = "", owner_scope: str = "") -> AccountLink:
        link = self._require(account_link_id, owner_scope=owner_scope)
        self._transition(link, AccountLinkStatus.REAUTH_REQUIRED.value)
        link.reason = reason[:200]
        with self._lock:
            self._save()
        return link

    def revoke(self, account_link_id: str, *, reason: str, owner_scope: str = "") -> AccountLink:
        link = self._require(account_link_id, owner_scope=owner_scope)
        # Force-revoke is always permitted regardless of current state.
        link.status = AccountLinkStatus.REVOKED.value
        link.reason = reason[:200]
        link.updated_at = _utc()
        if self.broker and link.credential_ref_id:
            try:
                self.broker.revoke(link.credential_ref_id, reason=f"account_link_revoked:{reason}"[:200])
            except Exception:
                pass
        with self._lock:
            self._save()
        self._emit("account_link.revoked", {"account_link_id": account_link_id, "reason": reason[:200]})
        return link

    def quarantine(self, account_link_id: str, *, reason: str, owner_scope: str = "") -> AccountLink:
        """Quarantine the link and its credential (leak / anomaly response)."""
        link = self._require(account_link_id, owner_scope=owner_scope)
        link.quarantine_reason = reason[:200]
        link.reason = reason[:200]
        # Move to REAUTH_REQUIRED unless terminal; credential is quarantined via broker.
        if link.status not in (AccountLinkStatus.REVOKED.value,):
            link.status = AccountLinkStatus.REAUTH_REQUIRED.value
            link.updated_at = _utc()
        if self.broker and link.credential_ref_id:
            try:
                self.broker.quarantine(link.credential_ref_id, reason=f"account_link:{reason}"[:200])
            except Exception:
                pass
        with self._lock:
            self._save()
        self._emit("account_link.quarantined", {"account_link_id": account_link_id, "reason": reason[:200]})
        return link

    def cancel(self, account_link_id: str, *, owner_scope: str = "") -> AccountLink:
        link = self._require(account_link_id, owner_scope=owner_scope)
        self._transition(link, AccountLinkStatus.CANCELLED.value)
        with self._lock:
            self._save()
        return link

    # ── Reads / readiness ──────────────────────────────────────────────────

    def get(self, account_link_id: str) -> Optional[AccountLink]:
        return self._links.get(account_link_id)

    def inspect(self, account_link_id: str, *, owner_scope: str = "") -> dict[str, Any]:
        return self._require(account_link_id, owner_scope=owner_scope).to_safe_dict()

    def list_metadata(self, *, owner_scope: str = "") -> list[dict[str, Any]]:
        return [
            l.to_safe_dict() for l in self._links.values()
            if not owner_scope or l.owner_scope == owner_scope
        ]

    def readiness(self, account_link_id: str, *, connector_id: str = "", owner_scope: str = "") -> dict[str, Any]:
        """Fail-closed readiness for connector execution on this link."""
        link = self._links.get(account_link_id)
        if link is None:
            return {"ready": False, "readiness": AccountLinkReadiness.UNLINKED.value, "reason": "unknown_account_link"}
        if owner_scope and link.owner_scope != owner_scope:
            return {"ready": False, "readiness": AccountLinkReadiness.POLICY_BLOCKED.value, "reason": "cross_owner_denied"}
        if is_prohibited_provider(link.provider_id):
            return {"ready": False, "readiness": AccountLinkReadiness.POLICY_BLOCKED.value, "reason": "prohibited_provider"}
        if connector_id and link.connector_ids and connector_id not in link.connector_ids:
            return {"ready": False, "readiness": AccountLinkReadiness.POLICY_BLOCKED.value, "reason": "connector_not_bound"}
        if any(is_prohibited_scope(s) for s in link.granted_scopes):
            return {"ready": False, "readiness": AccountLinkReadiness.SCOPE_BLOCKED.value, "reason": "prohibited_scope"}

        status_map = {
            AccountLinkStatus.REVOKED.value: AccountLinkReadiness.REVOKED.value,
            AccountLinkStatus.EXPIRED.value: AccountLinkReadiness.CREDENTIAL_EXPIRED.value,
            AccountLinkStatus.REAUTH_REQUIRED.value: AccountLinkReadiness.REAUTH_REQUIRED.value,
            AccountLinkStatus.SCOPE_BLOCKED.value: AccountLinkReadiness.SCOPE_BLOCKED.value,
            AccountLinkStatus.UNLINKED.value: AccountLinkReadiness.UNLINKED.value,
            AccountLinkStatus.LINK_REQUESTED.value: AccountLinkReadiness.AUTHORIZATION_PENDING.value,
            AccountLinkStatus.AUTHORIZATION_PENDING.value: AccountLinkReadiness.AUTHORIZATION_PENDING.value,
            AccountLinkStatus.CANCELLED.value: AccountLinkReadiness.UNLINKED.value,
            AccountLinkStatus.FAILED.value: AccountLinkReadiness.REAUTH_REQUIRED.value,
        }
        if link.status != _LIVE_READY:
            r = status_map.get(link.status, AccountLinkReadiness.UNLINKED.value)
            return {"ready": False, "readiness": r, "reason": f"link_status:{link.status}"}

        # LINKED — confirm the bound credential is usable.
        if not link.credential_ref_id:
            return {"ready": False, "readiness": AccountLinkReadiness.UNLINKED.value, "reason": "no_credential_bound"}
        if self.broker is not None:
            ref = self.broker.get_ref(link.credential_ref_id)
            if ref is None:
                return {"ready": False, "readiness": AccountLinkReadiness.PROVIDER_UNAVAILABLE.value, "reason": "credential_missing"}
            cmap = {
                CredentialStatus.QUARANTINED.value: AccountLinkReadiness.CREDENTIAL_QUARANTINED.value,
                CredentialStatus.REVOKED.value: AccountLinkReadiness.REVOKED.value,
                CredentialStatus.DELETED.value: AccountLinkReadiness.REVOKED.value,
                CredentialStatus.EXPIRED.value: AccountLinkReadiness.CREDENTIAL_EXPIRED.value,
                CredentialStatus.ROTATION_REQUIRED.value: AccountLinkReadiness.REAUTH_REQUIRED.value,
            }
            if ref.status in cmap:
                return {"ready": False, "readiness": cmap[ref.status], "reason": f"credential_{ref.status.lower()}"}
        return {
            "ready": True,
            "readiness": AccountLinkReadiness.READY.value,
            "reason": "ok",
            "granted_scopes": list(link.granted_scopes),
        }

    def status_report(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "account_links": self.list_metadata(),
            "events_count": len(self._events),
            "live_accounts_linked": 0,
            "real_oauth_flows_completed": 0,
            "privacy_safe": True,
            "contains_secret_values": False,
        }
