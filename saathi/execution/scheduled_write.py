"""The reference path for a scheduled external write.

Phase 19 proved no external write escapes authority. This proves the other half:
that a legitimate one can pass *through* it — and, critically, that passing
through once does not make it replayable.

Every scheduled external mutation should reuse this. It composes existing
milestones rather than adding a parallel authority system:

    Phase 18  durable delegation carries the originating user across time
    Phase 17  the actor is rebound from that record inside the worker
    Phase 16  ExecutionGateway decides RBAC, approval, connector, kill switch
    Phase 19  the side-effect guard admits the adapter only under a grant

The one thing not already present was a *durable, deterministic identity for one
scheduled occurrence*, and that turns out to be the whole replay problem.

**Why the delegation is the claim.** The obvious design is a job table with a
`claimed` column. It is unnecessary: a Phase 18 delegation is already durable,
already scoped, already expiring, already revocable, and its consumption is
already atomic (`UPDATE ... WHERE used < max_uses`, decided by rowcount). Giving
it an id derived from the occurrence makes "has this run?" and "may this run?"
the same question, answered once, by code that is already certified.

So the sequence is:

    occurrence identity  ->  delegation id (deterministic)
    INSERT OR IGNORE     ->  second ask finds the same row, not a new grant
    consume (atomic)     ->  exactly one caller proceeds
    resolve              ->  live RBAC, expiry, revocation, user still active
    bind actor           ->  the originating user, rebuilt from durable truth
    ToolIntent           ->  deterministic idempotency key from the occurrence
    connector engine     ->  approval binding, connector authority, gateway
    boundary handler     ->  opens the Phase 19 grant
    adapter              ->  the side effect

**What is guaranteed.** At most one external attempt per occurrence, per
`consume_delegation`. Beyond the point where the adapter's request leaves the
process the outcome is the provider's to decide, and `telegram.send_message` is
registered `idempotent=False, mutation=IRREVERSIBLE` — honest metadata this
module does not override. A crash between the provider accepting and the result
persisting therefore leaves an *ambiguous* delivery, not a success and not a
retryable failure. Exactly-once is not claimed and cannot be, and the ambiguity
is reported rather than resolved by guessing.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from saathi.agent_runtime.contracts import AuthorityClass

logger = logging.getLogger(__name__)

#: Scope kind for a scheduled occurrence, distinct from a plain job or a run.
SCOPE_SCHEDULED = "scheduled"

#: How long a scheduled occurrence's authority stays usable. Long enough to
#: absorb a restart and the scheduler's own catch-up window, short enough that a
#: missed occurrence stops being executable rather than firing hours later.
OCCURRENCE_TTL_SEC = 2 * 3600.0


#: Outcome vocabulary. Plain constants rather than an Enum: every value is
#: already a machine-safe reason code, carried through the same fields the rest
#: of the authority stack uses, and a parallel enum would be a second spelling
#: of strings that have to match those anyway.
CLAIMED_BY_OTHER = "scheduled.already_claimed"
DELEGATION_INVALID = "scheduled.delegation_invalid"
NO_ORIGINATING_USER = "scheduled.no_originating_user"
EXECUTED = "scheduled.executed"
REFUSED = "scheduled.refused"
AMBIGUOUS = "scheduled.ambiguous"


def occurrence_id(job: str, *, at: datetime | None = None,
                  granularity: str = "day") -> str:
    """A stable name for one scheduled run of one job.

    Deterministic, so every worker and every restart derives the same value; and
    distinct per occurrence, so tomorrow's run of a daily job is different work
    rather than a replay of today's. Granularity is the scheduling period: a
    daily job that fires twice in a day is the *same* occurrence and must not
    send twice, which is exactly the catch-up-window bug this defends against.
    """
    at = at or datetime.now(timezone.utc)
    stamp = {"day": "%Y-%m-%d", "hour": "%Y-%m-%dT%H",
             "minute": "%Y-%m-%dT%H:%M"}[granularity]
    return f"{job}@{at.strftime(stamp)}"


def delegation_id_for(user_id: str, occurrence: str) -> str:
    """The delegation id for one user's one occurrence.

    Derived rather than random: a random id would make a restart create a second
    grant, and two grants for one occurrence is two sends.
    """
    digest = hashlib.sha256(f"{user_id}|{occurrence}".encode()).hexdigest()
    return f"dlg_{digest[:24]}"


def idempotency_key_for(occurrence: str, action: str) -> str:
    """The execution boundary's idempotency key for this occurrence.

    64 hex characters, which is what `ToolIntent` validation requires. Bound to
    the occurrence and the action, so the boundary's own replay protection --
    terminal replay on a matching key, and its in-flight guard -- keys on the
    same thing the delegation does. Two layers, one identity.
    """
    return hashlib.sha256(f"{occurrence}|{action}".encode()).hexdigest()


@dataclass(frozen=True)
class ScheduledWriteResult:
    """What happened, in terms an operator and an audit log can both use."""

    outcome: str
    reason_code: str
    occurrence: str
    delegation_id: str = ""
    actor: str = ""
    detail: str = ""
    result: dict | None = None

    @property
    def executed(self) -> bool:
        return self.outcome == EXECUTED

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "reason_code": self.reason_code,
                "occurrence": self.occurrence,
                "delegation_id": self.delegation_id or None,
                "actor": self.actor or None, "detail": self.detail or None}


def schedule_occurrence(*, user_id: str, job: str, action: str,
                        at: datetime | None = None, granularity: str = "day",
                        authority_ceiling: str = AuthorityClass.EXTERNAL_MUTATION.value,
                        store=None) -> str:
    """Record that `user_id` authorized one occurrence of `job`. Idempotent.

    Called while the authenticated request still knows who is asking. Returns
    the delegation id, or "" when there is no user to attribute the work to --
    which leaves the occurrence unauthorized rather than attributing it to
    nobody in particular.
    """
    if not user_id:
        return ""
    if store is None:
        from saathi.security.store import get_store

        store = get_store()
    occurrence = occurrence_id(job, at=at, granularity=granularity)
    did = delegation_id_for(user_id, occurrence)
    import time as _time

    store.ensure_scheduled_delegation(
        delegation_id=did, user_id=user_id, scope_kind=SCOPE_SCHEDULED,
        scope_ref=occurrence, action=action, authority_ceiling=authority_ceiling,
        expires_at=_time.time() + OCCURRENCE_TTL_SEC)
    return did


def execute_scheduled_write(*, job: str, action: str, send,
                            at: datetime | None = None, granularity: str = "day",
                            user_id: str = "", store=None) -> ScheduledWriteResult:
    """Run one scheduled occurrence's external write, or refuse.

    `send` is invoked only after the claim is won and the actor is bound, and it
    is expected to route through the governed connector path -- it receives no
    authority of its own and cannot open a Phase 19 grant.

    The claim happens before authorization deliberately. Authorizing first and
    claiming afterwards leaves a window where two workers both authorize and
    both send; claiming first costs a delegation use on a refusal, which is the
    cheap direction to be wrong in.
    """
    from saathi.execution.delegated_work import execute_delegated  # noqa: F401
    from saathi.execution.delegation import DelegationRequest, audit, resolve

    if store is None:
        from saathi.security.store import get_store

        store = get_store()

    occurrence = occurrence_id(job, at=at, granularity=granularity)

    # Look up, validate and claim as one critical section. Phase 18 documented
    # why: the reads run on the same shared sqlite connection as the write that
    # claims. Leaving the *lookup* outside was measurably wrong -- under 32-way
    # concurrency a loser's read came back empty and the attempt was reported
    # `no_originating_user`, which says nobody scheduled the work when somebody
    # had. Safe, but a security path must not file a misleading reason.
    with store.delegation_lock():
        if not user_id:
            # Recover the originating user from the durable record rather than
            # assuming one: the scheduler has no session, and inventing an actor
            # here is the exact failure Phases 17 and 18 exist to prevent.
            record = _find_occurrence(store, occurrence, action)
            if record is None:
                return ScheduledWriteResult(REFUSED, NO_ORIGINATING_USER, occurrence)
            resolved_user = str(record.get("user_id") or "")
            did = str(record.get("delegation_id") or "")
        else:
            resolved_user = user_id
            did = delegation_id_for(resolved_user, occurrence)

        request = DelegationRequest(
            delegation_id=did, scope_kind=SCOPE_SCHEDULED, scope_ref=occurrence,
            action=action, authority_class=AuthorityClass.EXTERNAL_MUTATION.value)

        decision = resolve(did, request, store=store)
        if not decision.valid:
            audit(store, decision, "denied", detail=f"{occurrence}:{action}")
            return ScheduledWriteResult(REFUSED, decision.reason_code, occurrence,
                                        delegation_id=did)
        if not store.consume_delegation(did):
            # Another worker or an earlier run already took this occurrence.
            return ScheduledWriteResult(REFUSED, CLAIMED_BY_OTHER, occurrence,
                                        delegation_id=did, actor=decision.user_id)

    audit(store, decision, "used", detail=f"{occurrence}:{action}")

    from saathi.execution.delegation import delegated_actor

    try:
        with delegated_actor(decision):
            result = send(idempotency_key_for(occurrence, action))
    except Exception as exc:  # noqa: BLE001 - classified below, never swallowed
        # The claim is spent. Whether the provider saw the request is unknown,
        # and `telegram.send_message` is registered non-idempotent and
        # irreversible, so retrying could duplicate a real message. Reported as
        # ambiguous rather than resolved by guessing.
        audit(store, decision, "failed", detail=f"{occurrence}:{action}")
        from saathi.execution.sanitization import sanitize

        safe, report = sanitize(repr(exc))
        return ScheduledWriteResult(
            AMBIGUOUS, AMBIGUOUS, occurrence, delegation_id=did,
            actor=decision.user_id,
            detail=("[withheld]" if report.failed else str(safe))[:200])

    return ScheduledWriteResult(EXECUTED, EXECUTED, occurrence, delegation_id=did,
                                actor=decision.user_id, result=result)


def _find_occurrence(store, occurrence: str, action: str) -> dict | None:
    """The delegation recorded for this occurrence, whoever created it."""
    try:
        rows = store.db.execute(
            "SELECT * FROM authority_delegation WHERE scope_kind=? AND scope_ref=?"
            " AND action=? ORDER BY created_at DESC LIMIT 1",
            (SCOPE_SCHEDULED, occurrence, action)).fetchall()
        return dict(rows[0]) if rows else None
    except Exception:
        return None
