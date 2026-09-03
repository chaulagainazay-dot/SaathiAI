"""Running deferred work under the identity that authorized it.

The worker boundary Phase 18 exists for. A route records a delegation while it
still knows who is calling; the worker — running later, in a thread the request
does not outlive — loads that record and rebuilds the actor from it.

Rebuilt, not carried. Copying the request's context into the thread would take a
snapshot of authority the user may since have lost: it would survive a role
being removed, an account being disabled, and the delegation itself being
revoked. Re-resolving from the store means every one of those takes effect on
the next attempt.

This is a substrate, not a scheduler. It runs a callable under a reconstructed
identity and records what happened; deciding *when* work runs belongs to
whatever schedules it.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from saathi.agent_runtime.contracts import AuthorityClass
from saathi.execution.delegation import (
    DEFAULT_TTL_SEC,
    DelegationRequest,
    audit,
    delegated_actor,
    resolve,
)

logger = logging.getLogger(__name__)

#: Scope kind for a named background job, as opposed to an agent run.
SCOPE_JOB = "job"
SCOPE_RUN = "run"


def create_job_delegation(*, user_id: str, job_name: str,
                          authority_ceiling: str = AuthorityClass.READ_ONLY.value,
                          ttl_sec: float = DEFAULT_TTL_SEC,
                          max_uses: int = 1, store=None) -> str:
    """Record that `user_id` authorized one run of `job_name`. Returns its id.

    One use by default. A delegation that authorizes an unbounded number of
    future executions is a standing grant wearing a delegation's name, and the
    caller has to ask for that explicitly.

    Returns "" when there is no user to attribute the work to. That is not an
    error and not a fallback identity -- it means the work stays anonymous and
    therefore stays capped at the system actor, which is the honest outcome.
    """
    if not user_id:
        return ""
    if store is None:
        from saathi.security.store import get_store

        store = get_store()
    try:
        return store.create_delegation(
            user_id=user_id, scope_kind=SCOPE_JOB, scope_ref=job_name,
            action=job_name, authority_ceiling=authority_ceiling,
            ttl_sec=ttl_sec, max_uses=max_uses)
    except Exception:
        # Failing to record a delegation must not silently promote the work to
        # running under an identity nobody stored.
        logger.warning("could not record delegation for job %s", job_name)
        return ""


def execute_delegated(delegation_id: str, request: DelegationRequest,
                      fn: Callable[[], object], *, store=None):
    """Run `fn` under the delegation's originating user, or refuse.

    The single claim of a use happens *before* the work, atomically, so two
    workers racing for the last use of a one-shot delegation cannot both run it.
    A refusal runs nothing and binds nobody.
    """
    if store is None:
        from saathi.security.store import get_store

        store = get_store()

    # Validate and claim as one critical section. Splitting them lets two
    # workers both read a live record before either claims it -- and because the
    # store shares one sqlite connection across threads, the interleaved reads
    # were not merely racy but wrong, one worker seeing another's half-applied
    # state. The claim itself is still guarded in SQL; this makes the decision
    # the claim is based on trustworthy.
    with store.delegation_lock():
        decision = resolve(delegation_id, request, store=store)
        if not decision.valid:
            audit(store, decision, "denied", detail=request.action)
            return decision, None

        # Claim before running. Claiming afterwards would let a crash or a race
        # hand the same one-shot delegation to a second worker.
        if not store.consume_delegation(delegation_id):
            from saathi.execution.delegation import DelegationDecision, R_EXHAUSTED

            lost = DelegationDecision(False, R_EXHAUSTED, user_id=decision.user_id,
                                      delegation_id=delegation_id)
            audit(store, lost, "denied", detail=request.action)
            return lost, None

    audit(store, decision, "used", detail=request.action)
    try:
        with delegated_actor(decision):
            return decision, fn()
    except Exception:
        # The binding unwinds through the context manager whatever happens, so
        # nothing leaks into the next thing this thread does. Recorded, then
        # re-raised for the caller to handle as its own failure.
        audit(store, decision, "failed", detail=request.action)
        raise


def run_delegated_job(*, job_name: str, fn: Callable[[], object], user_id: str | None,
                      authority_ceiling: str = AuthorityClass.READ_ONLY.value,
                      ttl_sec: float = DEFAULT_TTL_SEC, store=None) -> str:
    """Record a delegation, then run `job_name` in a thread under it.

    Returns the delegation id, or "" when the work is running anonymously
    because no user could be attributed. The thread deliberately resolves the
    delegation itself rather than receiving a bound identity: that is the
    property under test, and the same path a future out-of-process worker would
    take.
    """
    delegation_id = create_job_delegation(
        user_id=user_id or "", job_name=job_name,
        authority_ceiling=authority_ceiling, ttl_sec=ttl_sec, store=store)

    request = DelegationRequest(
        delegation_id=delegation_id, scope_kind=SCOPE_JOB,
        scope_ref=job_name, action=job_name, authority_class=authority_ceiling)

    def _worker():
        if not delegation_id:
            # Anonymous: no delegation to reconstruct, so the job runs under the
            # constrained system actor exactly as it did before.
            fn()
            return
        try:
            execute_delegated(delegation_id, request, fn, store=store)
        except Exception:
            logger.exception("delegated job %s failed", job_name)

    threading.Thread(target=_worker, daemon=True).start()
    return delegation_id
