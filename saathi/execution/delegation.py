"""Durable authority delegation — who authorized work that outlives the request.

Phase 17 bound the authenticated user into a contextvar for the life of a
request. That is correct and sufficient while the work happens inside the
request, which today it does. It cannot survive the request ending, so anything
deferred — a job started from a route and finished in a thread, a scheduled run,
a future worker — reaches the gateway with no identity and falls back to the
constrained system actor. Nothing is *wrong* about that fallback; it is simply
anonymous, and anonymous work cannot be attributed, revoked, or held to the
permissions its originator actually has.

A delegation is the durable answer to the questions a contextvar cannot answer
later: who authorized this, what exactly, bound to which work, until when, and
up to what authority.

Four things it deliberately is not:

* **Not a session.** No token, cookie or header is stored. Re-presenting a
  session later is impersonation; a delegation carries identity and scope, and
  nothing that can be replayed as a login.
* **Not a bearer token.** Knowing a `delegation_id` authorizes nothing. The
  record is loaded from the store and every field is re-checked, including the
  originating user's *current* permissions.
* **Not a permission snapshot.** Authority is re-derived at execution from live
  RBAC. A user who loses a role loses it for their scheduled work too -- the
  alternative is a job that quietly outranks the person who created it.
* **Not agent delegation.** `agent_runtime.store.delegation` hands operational
  work from one agent to another. This carries a *user's* authority across time.
  Same word, different thing, and conflating them is how an agent would appear
  to hold authority no user granted.

A delegation proves origin and scope. Everything else -- RBAC, approval,
Guardian, connector authority, the kill switch, run lifecycle, intent
correlation -- is still decided by `ExecutionGateway`, unchanged.
"""
from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from enum import Enum

from saathi.agent_runtime.contracts import AuthorityClass


class DelegationStatus(str, Enum):
    """Small on purpose. Each value is a distinct fact, not a shade of one."""

    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


#: Machine-safe refusal codes. Rendered from, never described in prose.
R_OK = "delegation.valid"
R_MISSING = "delegation.missing"
R_UNKNOWN = "delegation.unknown"
R_EXPIRED = "delegation.expired"
R_REVOKED = "delegation.revoked"
R_EXHAUSTED = "delegation.exhausted"
R_SCOPE_MISMATCH = "delegation.scope_mismatch"
R_ACTION_MISMATCH = "delegation.action_mismatch"
R_CEILING_EXCEEDED = "delegation.ceiling_exceeded"
R_USER_UNAVAILABLE = "delegation.user_unavailable"
R_RBAC_REVOKED = "delegation.rbac_revoked"

#: Ordered weakest-to-strongest, so a ceiling can be compared without inventing
#: a second opinion about what outranks what. Financial execution is absent: it
#: is prohibited outright at the gateway and must never become a ceiling a
#: delegation can carry.
_CEILING_ORDER = (
    AuthorityClass.READ_ONLY,
    AuthorityClass.LOCAL_MUTATION,
    AuthorityClass.EXTERNAL_MUTATION,
    AuthorityClass.ADMINISTRATIVE,
)
_CEILING_RANK = {c.value: i for i, c in enumerate(_CEILING_ORDER)}

#: The default lifetime for delegated work whose parent has no deadline of its
#: own. Short enough that a forgotten delegation stops mattering within a
#: working day, long enough that ordinary deferred work finishes. Where the
#: parent work *does* have a canonical end -- a run deadline, a scheduled window
#: -- pass that instead of relying on this.
DEFAULT_TTL_SEC = 6 * 3600.0


@dataclass(frozen=True)
class DelegationRequest:
    """What a worker claims it is about to do. Checked against the record."""

    delegation_id: str
    scope_kind: str
    scope_ref: str
    action: str
    #: The authority the action needs. Compared against the record's ceiling;
    #: a delegation can never authorize more than it was created with.
    authority_class: str = AuthorityClass.READ_ONLY.value


@dataclass(frozen=True)
class DelegationDecision:
    """Whether this delegation authorizes this action, and who for."""

    valid: bool
    reason_code: str
    user_id: str = ""
    authority_ceiling: str = ""
    delegation_id: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "reason_code": self.reason_code,
            "user_id": self.user_id or None,
            "authority_ceiling": self.authority_ceiling or None,
            "delegation_id": self.delegation_id or None,
            # Never replayable: the record is re-read and re-checked every time.
            "is_capability_token": False,
        }


def status_of(record: dict, *, now: float | None = None) -> DelegationStatus:
    """The record's own lifecycle state, ignoring what is being asked of it."""
    now = time.time() if now is None else now
    if record.get("revoked_at") is not None:
        return DelegationStatus.REVOKED
    if float(record.get("expires_at") or 0) <= now:
        return DelegationStatus.EXPIRED
    if int(record.get("used") or 0) >= int(record.get("max_uses") or 1):
        return DelegationStatus.EXHAUSTED
    return DelegationStatus.ACTIVE


def evaluate(record: dict | None, request: DelegationRequest, *,
             user: dict | None, has_permission: bool | None,
             now: float | None = None) -> DelegationDecision:
    """Decide whether one delegation authorizes one action. Pure.

    Every input that could not be established arrives as None and produces a
    refusal, so there is no branch that reaches `valid=True` without the record,
    the user and the permission check all having answered.

    Order matters only for which reason is reported; every check runs against a
    record that must satisfy all of them.
    """
    if not request.delegation_id:
        return DelegationDecision(False, R_MISSING)
    if record is None:
        return DelegationDecision(False, R_UNKNOWN, delegation_id=request.delegation_id)

    ident = str(record.get("delegation_id") or "")
    state = status_of(record, now=now)
    if state is DelegationStatus.REVOKED:
        return DelegationDecision(False, R_REVOKED, delegation_id=ident)
    if state is DelegationStatus.EXPIRED:
        return DelegationDecision(False, R_EXPIRED, delegation_id=ident)
    if state is DelegationStatus.EXHAUSTED:
        return DelegationDecision(False, R_EXHAUSTED, delegation_id=ident)

    # Correlation. A delegation authorizes the work it was created for, not
    # whatever is presented alongside its id.
    if (str(record.get("scope_kind") or "") != request.scope_kind
            or str(record.get("scope_ref") or "") != request.scope_ref):
        return DelegationDecision(False, R_SCOPE_MISMATCH, delegation_id=ident)
    if str(record.get("action") or "") != request.action:
        return DelegationDecision(False, R_ACTION_MISMATCH, delegation_id=ident)

    ceiling = str(record.get("authority_ceiling") or "")
    wanted = _CEILING_RANK.get(request.authority_class)
    allowed = _CEILING_RANK.get(ceiling)
    if wanted is None or allowed is None or wanted > allowed:
        # An unrecognised class on either side is refused rather than ranked.
        return DelegationDecision(False, R_CEILING_EXCEEDED, delegation_id=ident,
                                  authority_ceiling=ceiling)

    # The originating user must still exist and still be active. A durable job
    # must not become ownerless authority.
    user_id = str(record.get("user_id") or "")
    if not user or str(user.get("status") or "") != "active":
        return DelegationDecision(False, R_USER_UNAVAILABLE, delegation_id=ident)

    # Live RBAC, not a snapshot taken at creation. A user who loses a role loses
    # it for their scheduled work too; the alternative is a job that quietly
    # outranks the person who created it.
    if has_permission is not True:
        return DelegationDecision(False, R_RBAC_REVOKED, user_id=user_id,
                                  delegation_id=ident)

    return DelegationDecision(True, R_OK, user_id=user_id,
                              authority_ceiling=ceiling, delegation_id=ident)


# ── the worker boundary ─────────────────────────────────────────────────────

#: The permission a delegated action's originating user must still hold. Same
#: constant the run-control routes use, so delegation cannot become a way to act
#: with permissions the interactive path would refuse.
DELEGATION_PERMISSION = "write"


def resolve(delegation_id: str, request: DelegationRequest, *, store=None,
            now: float | None = None) -> DelegationDecision:
    """Load a delegation and decide it against live identity and RBAC.

    This is the only place a worker learns who it is acting for. It reads the
    canonical record rather than trusting anything handed to it, which is what
    keeps a delegation id from behaving as a bearer token.
    """
    if store is None:
        from saathi.security.store import get_store

        try:
            store = get_store()
        except Exception:
            return DelegationDecision(False, R_UNKNOWN, delegation_id=delegation_id)

    try:
        record = store.get_delegation(delegation_id)
    except Exception:
        return DelegationDecision(False, R_UNKNOWN, delegation_id=delegation_id)

    user = None
    has_permission = None
    if record:
        user_id = str(record.get("user_id") or "")
        try:
            user = store.get_user(user_id)
            has_permission = store.has_permission(user_id, DELEGATION_PERMISSION)
        except Exception:
            # Unreadable identity is not absent identity, and neither authorizes.
            user, has_permission = None, None

    return evaluate(record, request, user=user, has_permission=has_permission,
                    now=now)


@contextlib.contextmanager
def delegated_actor(decision: DelegationDecision):
    """Bind the originating user for the duration of one delegated operation.

    Reconstructed from the durable record at the worker boundary, never carried
    across from the request that created the delegation: a copied context is a
    snapshot of authority the user may since have lost, and it would survive
    revocation.

    A refused decision binds nobody, which leaves the constrained system actor
    in place rather than silently proceeding as someone. The binding unwinds on
    the way out however the operation ends, so a worker cannot leak an identity
    into whatever the thread does next.
    """
    from saathi.execution.authorization_sources import actor_context

    with actor_context(decision.user_id if decision.valid else None):
        yield decision


def audit(store, decision: DelegationDecision, event: str, *, detail: str = "") -> None:
    """Durable evidence for one delegation event. Identifiers only, no payload."""
    try:
        store.audit(
            f"delegation.{event}",
            ok=decision.valid,
            user_id=decision.user_id,
            detail=(f"{decision.reason_code} id={decision.delegation_id[:32]}"
                    f" {detail}").strip()[:200],
        )
    except Exception:  # audit must never decide the decision
        pass
