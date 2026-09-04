"""The external-write boundary: no observable outside mutation without authority.

Phase 18's inventory surfaced a larger gap than the one it set out to close.
Scheduler jobs reach Facebook, Instagram, Gmail and MailerLite through direct
`httpx.post` calls in `saathi/tools/*`, and not one of those modules mentions
`ExecutionGateway`. Every authority gate built in Phases 16-18 -- RBAC, approval,
Guardian, connector authority, the kill switch, intent correlation -- sits beside
that path rather than in front of it.

It was inert in one checkout because `data/connections.json` happened to be
missing. That is a property of the data, not of the architecture: the code posts
the moment credentials appear. Containment cannot rest on a file being absent.

**What counts as an external write.** An observable mutation of state outside
SaathiOS's own persistence domain: publishing a post, sending a message, creating
a remote record, uploading to remote storage. Deliberately *not* included --
local reads, metrics, logging, state-root persistence, caches, and RPC-shaped
POSTs that mutate nothing outside (an LLM completion, an embedding, a search).
Method alone cannot tell those apart, which is why the classification here is by
*call site intent* rather than by HTTP verb: a caller declares that it is about
to mutate the outside world, and the guard decides whether it may.

**Why a guard rather than a rewrite.** Putting gateway logic inside every posting
function would scatter the same security rule across a dozen modules, and the one
that drifts is the one that leaks. This is a single choke point at the side
effect itself -- so authorization and execution stay bound, and an authorized
intent followed by an unrelated direct API call is not a thing that can happen.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Set only by the governed execution path. Its presence is what distinguishes
#: "this mutation was authorized" from "this code merely ran".
_GOVERNED: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "saathi_governed_egress", default=None)


class EgressDenied(RuntimeError):
    """An external mutation was attempted outside governed execution.

    Raised rather than returned so it cannot be ignored by a caller that does
    not check a status field -- which is how the current posting functions are
    written, every one of them returning a dict nobody inspects for authority.
    """

    def __init__(self, reason_code: str, target: str = ""):
        self.reason_code = reason_code
        self.target = target
        super().__init__(f"{reason_code}: external write to {target or 'unknown'}"
                         " outside governed execution")


@dataclass(frozen=True)
class EgressGrant:
    """What the governed path authorized, recorded for correlation."""

    intent_id: str
    intent_digest: str
    actor: str
    operation: str


R_NOT_GOVERNED = "egress.not_governed"
R_TARGET_MISMATCH = "egress.target_mismatch"


@contextlib.contextmanager
def governed_egress(grant: EgressGrant):
    """Mark the enclosing block as authorized to perform one external mutation.

    Entered by the governed execution path *after* `ExecutionGateway` has
    authorized the intent, and left when the operation ends however it ends. A
    contextvar rather than a parameter because the mutation happens several
    frames below, inside a connector or tool function that must not have to
    thread an authorization token through its own signature -- and because a
    parameter can be forged by a caller while an unset contextvar cannot.
    """
    token = _GOVERNED.set({"grant": grant})
    try:
        yield grant
    finally:
        _GOVERNED.reset(token)


def current_grant() -> EgressGrant | None:
    state = _GOVERNED.get()
    return state["grant"] if state else None


def guard(target: str, *, operation: str = "") -> EgressGrant:
    """Refuse an external mutation that is not inside governed execution.

    Called immediately before the side effect, by the function performing it.
    Returns the grant so the caller can correlate; raises `EgressDenied`
    otherwise. There is no permissive branch: an unset context means nobody
    authorized this, and "nobody authorized it" is the case this exists to stop.
    """
    grant = current_grant()
    if grant is None:
        logger.warning("blocked ungoverned external write to %s (%s)",
                       target, operation or "unspecified")
        _record_denial(target, operation)
        raise EgressDenied(R_NOT_GOVERNED, target)
    return grant


def _record_denial(target: str, operation: str) -> None:
    """Durable evidence that an ungoverned write was attempted and refused.

    Identifiers only. A blocked attempt is exactly the thing an operator needs
    to see -- silently failing closed teaches nobody what tried to run.
    """
    try:
        from saathi.security.store import get_store

        get_store().audit("egress.denied", ok=False,
                          detail=f"{R_NOT_GOVERNED} target={target[:80]}"
                                 f" op={operation[:40]}"[:200])
    except Exception:
        pass  # audit must never decide the decision
