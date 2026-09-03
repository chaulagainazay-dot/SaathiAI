"""Execution authority snapshot — read-only, backend-owned, fail-closed.

Answers one question about one action: *what is the strongest truthful thing
SaathiOS can say about whether this may proceed?* It never executes, never
grants, and is not a capability token — `ExecutionGateway`/`gateway_exec` still
enforce independently when execution actually happens.

The vocabulary below is deliberately smaller than the obvious one, because it was
written after auditing what this repository can actually know rather than before:

* **Trading Guardian** (`saathi.platform.tg`) is real and substantial, but it is
  *trading*-scoped: it evaluates strategies, portfolios, instruments and market
  regimes. It has no verdict about whether an agent run's task may proceed, so
  for an agent-runtime action it is NOT_APPLICABLE. Reporting "Guardian allowed"
  here would invent a verdict from a subsystem that never evaluated the action.

* **`saathi.execution.gateway.ExecutionGateway.authorize`** is an unimplemented
  scaffold: it carries a `# TODO: Implement authorization` and transitions every
  intent to AUTHORIZED unconditionally. It therefore contributes UNAVAILABLE and
  can never contribute a pass -- treating a stub's unconditional yes as authority
  is exactly the unknown-becomes-allowed path this module exists to prevent.

* The **real** enforcement for agent tool execution is
  `agent_runtime.gateway_exec`, which fails closed: with no platform runtime
  bound, every tool request is rejected `PLATFORM_RUNTIME_REQUIRED`. That is a
  genuine precondition and is reported as one.

Consequently the positive state is named AUTHORITY_CHECKS_PASSED, not
EXECUTION_ALLOWED: it says the checks this system can perform found nothing
blocking, which is weaker than a promise that execution would succeed. Nothing
here should ever be read as "safe to execute".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from saathi.agent_runtime.models import RunState, is_terminal


class AuthorityStatus(str, Enum):
    """Every state a real distinction in this repository can produce."""

    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    ACTION_UNKNOWN = "ACTION_UNKNOWN"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    RUN_STATE_BLOCKS = "RUN_STATE_BLOCKS"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    PLATFORM_RUNTIME_UNAVAILABLE = "PLATFORM_RUNTIME_UNAVAILABLE"
    #: The weakest truthful positive: the checks this system can perform found
    #: nothing blocking. Not a promise that execution will succeed.
    AUTHORITY_CHECKS_PASSED = "AUTHORITY_CHECKS_PASSED"
    #: A required input could not be established. Never positive.
    UNKNOWN = "UNKNOWN"


#: Machine-safe reason codes. The frontend renders from these, never from prose.
REASON = {
    AuthorityStatus.NOT_AUTHENTICATED: "auth.no_session",
    AuthorityStatus.NOT_AUTHORIZED: "rbac.permission_missing",
    AuthorityStatus.ACTION_UNKNOWN: "action.unknown",
    AuthorityStatus.KILL_SWITCH_ACTIVE: "kill_switch.active",
    AuthorityStatus.RUN_STATE_BLOCKS: "run_state.blocks",
    AuthorityStatus.WAITING_APPROVAL: "approval.pending",
    AuthorityStatus.APPROVAL_DENIED: "approval.denied",
    AuthorityStatus.APPROVAL_EXPIRED: "approval.expired",
    AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE: "platform_runtime.unavailable",
    AuthorityStatus.AUTHORITY_CHECKS_PASSED: "authority.checks_passed",
    AuthorityStatus.UNKNOWN: "authority.unknown",
}

#: Which system asserted each finding. Never inferred from wording.
class Provenance(str, Enum):
    SESSION_STORE = "AUTHORITATIVE_SESSION_STORE"
    RBAC_STORE = "AUTHORITATIVE_RBAC_STORE"
    RUN_STATE = "AUTHORITATIVE_RUN_STATE"
    APPROVAL_STORE = "AUTHORITATIVE_APPROVAL_STORE"
    KILL_SWITCH = "AUTHORITATIVE_KILL_SWITCH"
    PLATFORM_RUNTIME = "TRUSTED_RUNTIME_PLATFORM"
    COMPOSER = "COMPOSER"


#: Subsystems that exist but cannot speak about an agent-runtime action, and why.
#: Recorded in the snapshot so their silence is visible rather than implied.
NOT_APPLICABLE_SOURCES = {
    "trading_guardian": "trading-scoped: evaluates strategies, portfolios and "
                        "market regimes, not agent run tasks",
    "execution_gateway": "unimplemented: authorize() is a stub that grants "
                         "unconditionally, so it cannot contribute a pass",
}


#: Blocking precedence, strongest first. Each dominates everything below it.
#:
#: KILL_SWITCH first because it is a deliberate global stop and must not be
#: explained away by a subsequent check. NOT_AUTHORIZED next because who is
#: asking outranks what they are asking about, and because a caller who may not
#: act should not learn the action's state. Run lifecycle precedes approval: a
#: terminal run cannot proceed no matter how its approvals resolved. Approval
#: precedes the platform precondition because a decision the owner owes is more
#: informative than an environmental gap. UNKNOWN sits directly above the
#: positive state so any unestablished input denies it.
PRECEDENCE: tuple[AuthorityStatus, ...] = (
    AuthorityStatus.KILL_SWITCH_ACTIVE,
    AuthorityStatus.NOT_AUTHENTICATED,
    AuthorityStatus.NOT_AUTHORIZED,
    AuthorityStatus.ACTION_UNKNOWN,
    AuthorityStatus.RUN_STATE_BLOCKS,
    AuthorityStatus.APPROVAL_DENIED,
    AuthorityStatus.APPROVAL_EXPIRED,
    AuthorityStatus.WAITING_APPROVAL,
    AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE,
    AuthorityStatus.UNKNOWN,
    AuthorityStatus.AUTHORITY_CHECKS_PASSED,
)

_RANK = {status: i for i, status in enumerate(PRECEDENCE)}


@dataclass(frozen=True)
class Finding:
    """One gate's answer, with the system that produced it."""

    status: AuthorityStatus
    provenance: Provenance
    detail: str = ""


@dataclass
class AuthorityInputs:
    """Everything the composer is allowed to consider.

    Passed in rather than fetched, so the composer is pure and testable and so
    no gate can be silently skipped: an input that was not established arrives
    as None and denies the positive state.
    """

    actor_user_id: str | None = None
    has_permission: bool | None = None
    run: dict | None = None
    pending_approvals: list[dict] = field(default_factory=list)
    resolved_approvals: list[dict] = field(default_factory=list)
    kill_switch_blocked: bool | None = None
    platform_runtime_bound: bool | None = None
    now: float | None = None


def _kill_switch(inputs: AuthorityInputs) -> Finding | None:
    if inputs.kill_switch_blocked is None:
        return Finding(AuthorityStatus.UNKNOWN, Provenance.KILL_SWITCH,
                       "kill switch state could not be established")
    if inputs.kill_switch_blocked:
        return Finding(AuthorityStatus.KILL_SWITCH_ACTIVE, Provenance.KILL_SWITCH)
    return None


def _identity(inputs: AuthorityInputs) -> Finding | None:
    if not inputs.actor_user_id:
        return Finding(AuthorityStatus.NOT_AUTHENTICATED, Provenance.SESSION_STORE)
    if inputs.has_permission is None:
        return Finding(AuthorityStatus.UNKNOWN, Provenance.RBAC_STORE,
                       "permissions could not be established")
    if not inputs.has_permission:
        return Finding(AuthorityStatus.NOT_AUTHORIZED, Provenance.RBAC_STORE)
    return None


def _run_state(inputs: AuthorityInputs) -> Finding | None:
    if inputs.run is None:
        return Finding(AuthorityStatus.ACTION_UNKNOWN, Provenance.RUN_STATE)
    state = str(inputs.run.get("state") or "")
    try:
        rs = RunState(state)
    except ValueError:
        return Finding(AuthorityStatus.UNKNOWN, Provenance.RUN_STATE,
                       f"unrecognised state {state!r}")
    if is_terminal(rs):
        return Finding(AuthorityStatus.RUN_STATE_BLOCKS, Provenance.RUN_STATE, state)
    if rs is RunState.BLOCKED:
        return Finding(AuthorityStatus.RUN_STATE_BLOCKS, Provenance.RUN_STATE, state)
    return None


def _approval(inputs: AuthorityInputs) -> Finding | None:
    now = inputs.now if inputs.now is not None else time.time()

    if inputs.pending_approvals:
        # An expired pending approval is expired, not merely waiting.
        for appr in inputs.pending_approvals:
            expires = appr.get("expires_at")
            if expires is not None and float(expires) < now:
                return Finding(AuthorityStatus.APPROVAL_EXPIRED,
                               Provenance.APPROVAL_STORE, str(appr.get("id", ""))[:32])
        return Finding(AuthorityStatus.WAITING_APPROVAL, Provenance.APPROVAL_STORE,
                       str(inputs.pending_approvals[0].get("id", ""))[:32])

    for appr in inputs.resolved_approvals:
        status = str(appr.get("status") or "")
        if status == "denied":
            return Finding(AuthorityStatus.APPROVAL_DENIED, Provenance.APPROVAL_STORE,
                           str(appr.get("id", ""))[:32])
        if status == "expired":
            return Finding(AuthorityStatus.APPROVAL_EXPIRED, Provenance.APPROVAL_STORE,
                           str(appr.get("id", ""))[:32])

    # An approved approval is not a pass; it merely stops blocking here.
    return None


def _platform_runtime(inputs: AuthorityInputs) -> Finding | None:
    if inputs.platform_runtime_bound is None:
        return Finding(AuthorityStatus.UNKNOWN, Provenance.PLATFORM_RUNTIME,
                       "platform runtime binding could not be established")
    if not inputs.platform_runtime_bound:
        return Finding(AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE,
                       Provenance.PLATFORM_RUNTIME, "PLATFORM_RUNTIME_REQUIRED")
    return None


_GATES = (_kill_switch, _identity, _run_state, _approval, _platform_runtime)


def compose(inputs: AuthorityInputs, *, run_id: str = "", task_id: str = "") -> dict:
    """Compose one action's authority snapshot. Pure: reads nothing, writes nothing.

    Every gate runs, so the snapshot can list everything that is blocking rather
    than only the first thing; the reported status is the strongest of them.
    """
    findings = [f for gate in _GATES if (f := gate(inputs)) is not None]

    if findings:
        status_finding = min(findings, key=lambda f: _RANK[f.status])
    else:
        status_finding = Finding(AuthorityStatus.AUTHORITY_CHECKS_PASSED,
                                 Provenance.COMPOSER)

    return {
        "status": status_finding.status.value,
        "reason_code": REASON[status_finding.status],
        "provenance": status_finding.provenance.value,
        "detail": status_finding.detail or None,
        # Contextual, never a global "SaathiOS can execute" boolean.
        "run_id": run_id or None,
        "task_id": task_id or None,
        "actor_user_id": inputs.actor_user_id or None,
        "evaluated_at": inputs.now if inputs.now is not None else time.time(),
        # Everything blocking, so a caller sees the whole picture, not just the
        # strongest item.
        "blocking": [
            {"status": f.status.value, "reason_code": REASON[f.status],
             "provenance": f.provenance.value, "detail": f.detail or None}
            for f in sorted(findings, key=lambda f: _RANK[f.status])
        ],
        # Silence made visible: subsystems that exist but cannot speak here.
        "not_applicable": dict(NOT_APPLICABLE_SOURCES),
        # This is an observation, not a grant. ExecutionGateway/gateway_exec
        # re-evaluate independently at action time; nothing here may be replayed
        # as permission.
        "is_capability_token": False,
        "read_only": True,
    }


def positive(snapshot: dict) -> bool:
    """Whether a snapshot reached the positive state. One place, so no caller
    reinvents the comparison."""
    return snapshot.get("status") == AuthorityStatus.AUTHORITY_CHECKS_PASSED.value
