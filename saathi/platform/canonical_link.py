"""The one bridge from the canonical D14 owner to the platform identity.

Two identity systems exist in this codebase. D14 secured the canonical one: an
owner in the security store, created only by a bootstrap that demands an
explicit one-time operator proof. The platform namespace (M50) kept its own
users, organisations, workspaces and sessions in a separate database, and its
own way in:

    POST /api/v1/platform/bootstrap

which took no token, no session and no operator proof, defaulted every field of
its request body, and — when no password was supplied — fell through to a
"M50 compatibility: passwordless bootstrap" path. The auth middleware exempted
the whole ``/api/v1/platform/*`` prefix on the stated assumption that each route
under it enforces ``X-Platform-Token``. That route enforced nothing.

The consequence was not theoretical. During R2.1 validation an empty ``{}`` POST
from an unauthenticated loopback caller created ``owner@local`` plus an
organisation, workspace and owner membership. Worse than a one-off write:
``bootstrap_owner`` returns early once any user exists, so the *first* anonymous
caller permanently fixes who the platform owner is, and a legitimate operator
can no longer claim it. That is D14's first attack class — unauthenticated
fresh-install owner provisioning — surviving in the namespace D14 did not audit.

The repair is this module. Platform identity is no longer something a caller can
assert; it is *derived* from an authenticated canonical principal:

  * the installation must be canonically ACTIVE (D14 state machine);
  * the request must carry a live canonical session;
  * the identity provisioned is the canonical owner's, read from the security
    store — never from the request body;
  * the resulting platform session is bounded by the canonical session's own
    expiry, so the exchanged credential cannot outlive the authority it came
    from.

No second password and no second operator token: a duplicate credential to
protect a duplicate identity system would double the attack surface to preserve
an accident of history.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

#: Serialises provisioning inside this process. The platform store's own
#: uniqueness checks remain authoritative across processes; this narrows the
#: window in which two requests both observe an empty store.
_provision_lock = threading.RLock()

#: A derived platform session may never outlive the canonical session it was
#: exchanged from, and never exceeds this ceiling even if the canonical session
#: is long-lived.
MAX_DERIVED_TTL = 24 * 3600.0


class CanonicalLinkError(Exception):
    """Bounded refusal. Carries a machine code and no sensitive detail."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code
        self.message = message or code


@dataclass(frozen=True)
class CanonicalPrincipal:
    """Who the canonical session says is calling, and for how much longer."""

    user_id: str
    email: str
    name: str
    session_id: str
    expires_at: float

    def remaining(self, now: float | None = None) -> float:
        return max(0.0, self.expires_at - (now if now is not None else time.time()))


def canonical_session_token(request) -> str:
    """The canonical session presented by this request, if any.

    Same contract as the canonical gate: a cookie set by the unlock screen, or
    the header used by clients that cannot rely on cookies cross-origin.
    """
    cookies = getattr(request, "cookies", None) or {}
    headers = getattr(request, "headers", None) or {}
    return (cookies.get("baadar_session")
            or headers.get("x-baadar-session", "")
            or "").strip()


def require_canonical_owner(request) -> CanonicalPrincipal:
    """Resolve the authenticated canonical owner, or refuse with a bounded code.

    Every failure here is a refusal to provision. There is deliberately no
    branch that treats a loopback peer, an empty store or a missing password as
    permission — those were exactly the conditions the old route provisioned
    under.
    """
    from saathi import auth_bootstrap, sessions
    from saathi.security.store import get_store

    store = get_store()

    # D14 state first. An installation that has no canonical owner cannot lend
    # its identity to anything, and a contaminated one must not be built upon.
    state = auth_bootstrap.auth_state(store)
    if state is not auth_bootstrap.AuthState.ACTIVE:
        raise CanonicalLinkError("CANONICAL_NOT_ACTIVE", f"canonical state {state.value}")

    token = canonical_session_token(request)
    if not token:
        raise CanonicalLinkError("CANONICAL_SESSION_REQUIRED")
    if not sessions.validate(token):
        # Covers unknown, expired and revoked alike: a canonical session that
        # has been logged out cannot mint a new platform session.
        raise CanonicalLinkError("CANONICAL_SESSION_INVALID")

    sid = sessions.session_id(token)
    record = store.session_by_hash(sessions._hash(token)) or {}
    owner_id = store.owner_id()
    if not owner_id:
        raise CanonicalLinkError("CANONICAL_OWNER_MISSING")

    # The session must belong to the owner. The platform identity being
    # provisioned is the owner's, so a session for anybody else is not
    # authority to create it.
    if record.get("user_id") and record["user_id"] != owner_id:
        raise CanonicalLinkError("CANONICAL_NOT_OWNER")

    user = store.get_user(owner_id) or {}
    return CanonicalPrincipal(
        user_id=owner_id,
        email=(user.get("email") or "") or f"owner+{owner_id[:8]}@localhost",
        name=(user.get("name") or "Owner"),
        session_id=sid,
        expires_at=float(record.get("expires_at") or 0.0),
    )


def derived_ttl(principal: CanonicalPrincipal) -> float:
    """How long an exchanged platform session may live.

    Bounded by the canonical session's own remaining life, so revoking or
    expiring the canonical session cannot leave a longer-lived platform
    credential behind it.
    """
    remaining = principal.remaining()
    if remaining <= 0:
        raise CanonicalLinkError("CANONICAL_SESSION_INVALID")
    return min(remaining, MAX_DERIVED_TTL)


def provision_for_request(svc, request) -> dict:
    """Resolve the canonical principal and provision under one process lock.

    Resolving and provisioning must not interleave. Both read the canonical
    security store, which is a single sqlite connection shared across threads
    (``check_same_thread=False``); two requests stepping through cursors on it
    concurrently is undefined behaviour rather than a race the database will
    settle, and it showed up as spurious refusals under concurrent provisioning.
    The same lock also makes "is the platform store empty?" and "create the
    owner" one decision, so concurrent callers cannot both observe emptiness.
    """
    with _provision_lock:
        principal = require_canonical_owner(request)
        return _provision_locked(svc, principal)


def provision_from_canonical(svc, principal: CanonicalPrincipal) -> dict:
    """Create-or-return the platform identity belonging to the canonical owner.

    Idempotent: a second call returns the same identity with a fresh session
    rather than creating a second owner. Fails closed on a platform store whose
    existing owner did not come from this canonical identity — that is the
    fingerprint of the anonymous bootstrap, and it is refused rather than
    adopted or deleted, because those rows are the evidence of how they got
    there.
    """
    with _provision_lock:
        return _provision_locked(svc, principal)


def _provision_locked(svc, principal: CanonicalPrincipal) -> dict:
    """Provisioning proper. Callers must already hold ``_provision_lock``."""
    from saathi.platform.models import PlatformRole

    if True:
        store = svc.store
        users = store.list_users()

        if users:
            existing = users[0]
            link = (store.get_config("canonical_link", {}) or {})
            if link.get("canonical_user_id") != principal.user_id:
                # Either something provisioned without a canonical principal, or
                # a different canonical owner did. Neither may be silently
                # inherited.
                raise CanonicalLinkError(
                    "PLATFORM_STATE_CONTAMINATED",
                    "existing platform owner is not derived from this canonical owner",
                )
            user = existing
            created = False
        else:
            # Identity comes from the canonical store, never from the caller.
            boot = svc.bootstrap_owner(
                email=principal.email,
                name=principal.name,
                org_name="Default Org",
                workspace_name="Default Workspace",
            )
            user = store.get_user(boot["user"]["user_id"])
            store.set_config("canonical_link", {
                "canonical_user_id": principal.user_id,
                "linked_at": time.time(),
            })
            created = True

        orgs = store.list_orgs_for_user(user.user_id)
        if not orgs:
            raise CanonicalLinkError("PLATFORM_STATE_INCOMPLETE", "no organisation")
        org = orgs[0]
        workspaces = store.list_workspaces(org.org_id)
        if not workspaces:
            raise CanonicalLinkError("PLATFORM_STATE_INCOMPLETE", "no workspace")
        ws = workspaces[0]

        role = store.membership_role(org.org_id, user.user_id) or PlatformRole.OWNER.value
        raw = secrets.token_urlsafe(32)
        store.create_session(
            user.user_id,
            raw,
            org_id=org.org_id,
            workspace_id=ws.workspace_id,
            role=role,
            ttl_sec=derived_ttl(principal),
            idle_sec=min(3600.0, derived_ttl(principal)),
            label=f"derived:{principal.session_id[:12]}",
            auth_method="CANONICAL_SESSION_EXCHANGE",
        )
        return {
            "provisioned": created,
            "token": raw,
            "user": user.to_public(),
            "org": org.to_public(),
            "workspace": ws.to_public(),
        }
