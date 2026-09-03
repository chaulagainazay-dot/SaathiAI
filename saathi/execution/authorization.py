"""Execution authorization — one decision, about one execution intent.

`ExecutionGateway.authorize` used to carry `# TODO: Implement authorization` and
transitioned *every* intent to AUTHORIZED. This module replaces that with a
composer that can only reach a positive decision when every gate the action
actually requires returned a current, correlated, positive result.

Three things stay separate, deliberately:

* **The Phase 14 snapshot** (`agent_runtime.execution_authority`) explains the
  authority state of a *run* for display. It grants nothing.
* **This module** decides one specific `ToolIntent`. It still executes nothing.
* **`gateway_exec` / the connector substrate** enforce at execution time, and
  re-evaluate the gates that can change underneath a decision.

The vocabulary is small on purpose. `AUTHORIZED` refers to this intent, at this
instant, under these inputs -- never to a user, a run, or a session. It is not a
bearer token: the decision records the intent's canonical digest, so replaying it
against any other action fails correlation.

Fail-closed is structural rather than remembered. `AuthorizationInputs` fields
are `None` when a source could not be established, every gate maps `None` to a
non-positive finding, and the composer reaches AUTHORIZED only when *no* gate
returned anything else. There is no default-allow branch to forget to guard.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from saathi.agent_runtime.contracts import (
    ApprovalRequirement,
    AuthorityClass,
    PROHIBITED_CAPABILITIES,
    approval_requirement_for,
)
from saathi.agent_runtime.models import RiskClass, RunState, is_terminal
from saathi.execution.record import tool_intent_digest


class Decision(str, Enum):
    """The whole result vocabulary. Reason codes carry the specificity."""

    #: Every required gate returned a current, correlated positive result.
    #: Says nothing about whether execution will succeed.
    AUTHORIZED = "AUTHORIZED"
    #: A gate positively refused.
    DENIED = "DENIED"
    #: A required input could not be established. Never permits execution;
    #: distinct from DENIED so an operator can tell a refusal from a blind spot.
    UNKNOWN = "UNKNOWN"


class GateResult(str, Enum):
    """One gate's answer. Only PASSED and NOT_APPLICABLE are positive."""

    PASSED = "PASSED"
    #: The gate's subsystem has no verdict about this action *and is not
    #: supposed to*. Never the same as allowed -- see `Guardian` below.
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    #: Required, but no verdict exists at all.
    MISSING = "MISSING"
    #: A verdict exists but is too old to rely on.
    STALE = "STALE"
    #: The gate could not be evaluated.
    UNKNOWN = "UNKNOWN"


_POSITIVE = (GateResult.PASSED, GateResult.NOT_APPLICABLE)


class Provenance(str, Enum):
    """Which system asserted a finding. Never inferred from wording."""

    KILL_SWITCH = "AUTHORITATIVE_KILL_SWITCH"
    INTENT = "AUTHORITATIVE_INTENT"
    SESSION_STORE = "AUTHORITATIVE_SESSION_STORE"
    RBAC_STORE = "AUTHORITATIVE_RBAC_STORE"
    ACTION_REGISTRY = "AUTHORITATIVE_ACTION_REGISTRY"
    RUN_STATE = "AUTHORITATIVE_RUN_STATE"
    APPROVAL_STORE = "AUTHORITATIVE_APPROVAL_STORE"
    TRADING_GUARDIAN = "AUTHORITATIVE_TRADING_GUARDIAN"
    CONNECTOR_STATE = "AUTHORITATIVE_CONNECTOR_STATE"
    COMPOSER = "COMPOSER"


# ── reason codes ────────────────────────────────────────────────────────────
# Machine-safe and closed. Callers and the UI render from these; no model text
# and no free-form prose ever reaches a decision.

R_KILL_SWITCH_ACTIVE = "kill_switch.active"
R_KILL_SWITCH_UNKNOWN = "kill_switch.unknown"

R_INTENT_MALFORMED = "intent.malformed"
R_INTENT_STALE = "intent.stale"
R_ACTOR_MISMATCH = "intent.actor_mismatch"

R_ACTOR_UNKNOWN = "actor.unknown"
R_RBAC_DENIED = "rbac.denied"
R_RBAC_UNKNOWN = "rbac.unknown"

R_ACTION_UNKNOWN = "action.unknown"
R_ACTION_PROHIBITED = "action.prohibited"
R_RISK_UNKNOWN = "risk.unknown"

R_RUN_STATE_INVALID = "run_state.invalid"
R_RUN_STATE_UNKNOWN = "run_state.unknown"
R_RUN_NOT_OWNED = "run_state.not_owned"

R_APPROVAL_PENDING = "approval.pending"
R_APPROVAL_DENIED = "approval.denied"
R_APPROVAL_EXPIRED = "approval.expired"
R_APPROVAL_MISSING = "approval.missing"
R_APPROVAL_UNCORRELATED = "approval.uncorrelated"
R_APPROVAL_UNKNOWN = "approval.unknown"

R_GUARDIAN_BLOCKED = "guardian.blocked"
R_GUARDIAN_MISSING = "guardian.missing"
R_GUARDIAN_STALE = "guardian.stale"
R_GUARDIAN_UNCORRELATED = "guardian.uncorrelated"

R_CONNECTOR_UNAVAILABLE = "connector.unavailable"
R_CONNECTOR_UNAUTHORIZED = "connector.unauthorized"
R_CONNECTOR_ENV_BLOCKED = "connector.environment_blocked"
R_CONNECTOR_UNKNOWN = "connector.unknown"

R_OK = "authorization.granted"


#: How old a Trading Guardian verdict may be and still count. Trading verdicts
#: describe a market state that moves, so an old one is not a verdict about now.
#: Deliberately short, and only consulted where a Guardian verdict is required
#: at all -- this is not a general-purpose TTL applied to unrelated gates.
GUARDIAN_MAX_AGE_SEC = 300.0


# ── action resolution ───────────────────────────────────────────────────────
#: Non-connector operations this gateway knows how to classify, and the class
#: each one genuinely has. An operation absent from here and from the connector
#: registry is `action.unknown` and cannot be authorized: guessing a class for an
#: unrecognised action is precisely how an unknown becomes an allow.
#:
#: `local-llm-inference` is READ_ONLY because it reads a local model and returns
#: text -- it mutates nothing and reaches nothing external. `video-generation`
#: writes artifacts to disk, so it is LOCAL_MUTATION and inherits that class's
#: approval requirement rather than a convenient weaker one.
LOCAL_ACTIONS: dict[str, tuple[AuthorityClass, RiskClass]] = {
    "local-llm-inference": (AuthorityClass.READ_ONLY, RiskClass.READ_ONLY),
    "video-generation": (AuthorityClass.LOCAL_MUTATION, RiskClass.LOCAL_MUTATION),
}

@dataclass(frozen=True)
class ResolvedAction:
    """What the action *is*, from real registry metadata rather than a default."""

    authority_class: AuthorityClass
    risk: RiskClass
    source: str
    requires_connector: bool = False

    @property
    def is_financial(self) -> bool:
        return self.authority_class in (
            AuthorityClass.FINANCIAL_ADVISORY,
            AuthorityClass.FINANCIAL_EXECUTION,
        )


def resolve_action(
    operation: str,
    connector_id: str = "",
    capability: str = "",
    *,
    connector_action: ResolvedAction | None = None,
) -> ResolvedAction | None:
    """Classify one action deterministically, or return None if unclassifiable.

    Order matters. A connector tool's registered class is authoritative and
    outranks the local table, because that is the metadata the connector platform
    itself enforces against; it is resolved in `authorization_sources` because
    only that layer may read the registry.
    """
    if connector_action is not None:
        return connector_action
    if capability in PROHIBITED_CAPABILITIES or operation in PROHIBITED_CAPABILITIES:
        # Named live-money capabilities classify as financial execution so the
        # prohibition gate refuses them by class, not by string matching later.
        return ResolvedAction(
            authority_class=AuthorityClass.FINANCIAL_EXECUTION,
            risk=RiskClass.HIGH_IMPACT,
            source="prohibited_capability",
            requires_connector=bool(connector_id),
        )
    entry = LOCAL_ACTIONS.get(operation)
    if entry is not None:
        authority, risk = entry
        return ResolvedAction(
            authority_class=authority,
            risk=risk,
            source="local_action_registry",
            requires_connector=bool(connector_id),
        )
    return None


# ── inputs ──────────────────────────────────────────────────────────────────


#: The most authority an unattributed in-process caller may ever hold.
#:
#: Some gateway entry points run inside an already-authenticated backend
#: boundary that does not plumb the session through to the gateway -- chat and
#: agent inference call `execute_intent` with no request in scope. Treating that
#: as an unknown actor would deny local inference; treating it as the operator
#: would be trusting an identity nobody asserted. It is neither: it is the
#: backend process acting as itself, which is a real actor with a *fixed, small*
#: grant. It may perform READ_ONLY, connector-free, approval-free actions and
#: nothing else -- so the missing plumbing blocks exactly the actions where
#: identity carries weight, instead of being waved through or breaking the
#: product. Raising this constant would silently widen that grant; the intended
#: fix is to plumb a session, not to raise it.
SYSTEM_ACTOR_MAX_AUTHORITY = AuthorityClass.READ_ONLY

#: Identity recorded for that caller. Named, so audit never shows a blank actor.
SYSTEM_ACTOR = "system:saathi-backend"

R_ACTOR_SYSTEM_INSUFFICIENT = "actor.system_insufficient_authority"


@dataclass
class AuthorizationInputs:
    """Everything the composer may consider, passed in rather than fetched.

    Every optional field means the same thing when it is None: *this could not
    be established*. No gate is allowed to read None as satisfied, so a source
    that failed to resolve denies the positive decision instead of vanishing.
    """

    #: Server-trusted identity. Never taken from a request body or an intent.
    actor_user_id: str | None = None
    has_permission: bool | None = None
    #: True when the caller is the backend process itself rather than a human
    #: session. Only ever set by the gateway's own resolver, never by a request.
    actor_is_system: bool = False
    kill_switch_blocked: bool | None = None

    #: The connector tool's registered class, resolved from the connector
    #: registry by `authorization_sources`. None means "not a connector tool",
    #: never "no risk" -- an intent that names a connector whose tool is
    #: unregistered resolves to no action at all, and is refused.
    connector_action: "ResolvedAction | None" = None
    #: Canonical connector lifecycle state, when the action requires a connector.
    connector_state: str | None = None

    #: The run this intent executes within, when it declares one. `run_declared`
    #: distinguishes "no run in scope" (NOT_APPLICABLE) from "a run was named but
    #: could not be read" (UNKNOWN).
    run_declared: bool = False
    run: dict | None = None

    #: Approval records already correlated to this intent's digest by the caller.
    #: None means the approval store could not be consulted.
    approvals: list[dict] | None = None

    #: A Trading Guardian verdict, when the action is financial. Shape:
    #: {"decision": "allow"|"block", "at": <unix seconds>, "digest": <intent digest>}
    guardian_verdict: dict | None = None

    now: float | None = None


@dataclass(frozen=True)
class GateFinding:
    gate: str
    result: GateResult
    reason_code: str
    provenance: Provenance
    detail: str = ""

    @property
    def positive(self) -> bool:
        return self.result in _POSITIVE

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "result": self.result.value,
            "reason_code": self.reason_code,
            "provenance": self.provenance.value,
            "detail": self.detail or None,
        }


# ── gates ───────────────────────────────────────────────────────────────────
# Each returns exactly one finding. A gate never returns None: a gate that did
# not apply says NOT_APPLICABLE out loud, so the decision record shows every
# gate that ran and what each one said.


def _gate_kill_switch(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """Dominates everything. A deliberate global stop is not explained away by a
    later positive gate, so it sits first in `_GATES` and, being a gate like any
    other, a BLOCKED here can never be outvoted."""
    if inputs.kill_switch_blocked is None:
        return GateFinding("kill_switch", GateResult.UNKNOWN, R_KILL_SWITCH_UNKNOWN,
                           Provenance.KILL_SWITCH)
    if inputs.kill_switch_blocked:
        return GateFinding("kill_switch", GateResult.BLOCKED, R_KILL_SWITCH_ACTIVE,
                           Provenance.KILL_SWITCH)
    return GateFinding("kill_switch", GateResult.PASSED, R_OK, Provenance.KILL_SWITCH)


def _gate_intent(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """The intent must be well-formed enough to *be* authorized, and current.

    This is not schema validation -- it is the minimum needed for the decision to
    mean anything: an action to decide about, an actor to decide for, and a
    lifetime that has not run out.
    """
    now = inputs.now if inputs.now is not None else time.time()
    if not getattr(intent, "operation", ""):
        return GateFinding("intent", GateResult.BLOCKED, R_INTENT_MALFORMED,
                           Provenance.INTENT, "operation missing")
    if not getattr(intent, "actor_id", ""):
        return GateFinding("intent", GateResult.BLOCKED, R_INTENT_MALFORMED,
                           Provenance.INTENT, "actor_id missing")
    expires = getattr(intent, "expires_at", None)
    if expires is not None and float(expires) <= now:
        return GateFinding("intent", GateResult.STALE, R_INTENT_STALE,
                           Provenance.INTENT)
    return GateFinding("intent", GateResult.PASSED, R_OK, Provenance.INTENT)


def _gate_actor(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """Identity is server-resolved, and must be the identity the intent names.

    Without the correlation check a caller authenticated as themselves could
    submit an intent attributed to someone else and have it authorized under
    their own permissions while auditing as the other actor.
    """
    if inputs.actor_is_system:
        # The backend acting as itself: a real actor with a fixed, minimal grant.
        # Anything above it needs a human identity this call did not carry.
        if action is None:
            return GateFinding("actor", GateResult.UNKNOWN, R_ACTOR_UNKNOWN,
                               Provenance.SESSION_STORE, "action unresolved")
        if (action.authority_class is not SYSTEM_ACTOR_MAX_AUTHORITY
                or action.requires_connector):
            return GateFinding("actor", GateResult.BLOCKED,
                               R_ACTOR_SYSTEM_INSUFFICIENT,
                               Provenance.SESSION_STORE,
                               action.authority_class.value)
        return GateFinding("actor", GateResult.PASSED, R_OK,
                           Provenance.SESSION_STORE, SYSTEM_ACTOR)
    if not inputs.actor_user_id:
        return GateFinding("actor", GateResult.UNKNOWN, R_ACTOR_UNKNOWN,
                           Provenance.SESSION_STORE)
    claimed = str(getattr(intent, "actor_id", "") or "")
    if not _actor_matches(inputs.actor_user_id, claimed):
        return GateFinding("actor", GateResult.BLOCKED, R_ACTOR_MISMATCH,
                           Provenance.SESSION_STORE)
    return GateFinding("actor", GateResult.PASSED, R_OK, Provenance.SESSION_STORE)


def _actor_matches(resolved: str, claimed: str) -> bool:
    """Whether a server-resolved identity owns an intent's declared actor.

    Intents are attributed with a namespaced form (``user:ajay``, ``agent:builder``)
    while sessions resolve a bare user id. An agent-attributed intent belongs to
    the user whose session is driving the run, so the namespace is compared
    rather than required to match verbatim -- but a *user*-attributed intent must
    name this exact user.
    """
    if not resolved or not claimed:
        return False
    if claimed == resolved:
        return True
    prefix, _, rest = claimed.partition(":")
    if prefix == "user":
        return rest == resolved
    # agent:/system: intents act on behalf of the resolved session's user; the
    # user's own permissions still gate them at the rbac gate.
    return prefix in ("agent", "system")


def _gate_rbac(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    if inputs.actor_is_system:
        # A system actor holds exactly SYSTEM_ACTOR_MAX_AUTHORITY, enforced at
        # the actor gate. There is no role to consult, and inventing a
        # permission lookup for it would only make the grant look larger.
        return GateFinding("rbac", GateResult.NOT_APPLICABLE, R_OK,
                           Provenance.RBAC_STORE,
                           f"system actor: fixed {SYSTEM_ACTOR_MAX_AUTHORITY.value} grant")
    if inputs.has_permission is None:
        return GateFinding("rbac", GateResult.UNKNOWN, R_RBAC_UNKNOWN,
                           Provenance.RBAC_STORE)
    if not inputs.has_permission:
        return GateFinding("rbac", GateResult.BLOCKED, R_RBAC_DENIED,
                           Provenance.RBAC_STORE)
    return GateFinding("rbac", GateResult.PASSED, R_OK, Provenance.RBAC_STORE)


def _gate_action(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """An unclassifiable action is refused, and a prohibited class always is.

    FINANCIAL_EXECUTION and the named live-money capabilities are refused here
    unconditionally: no approval, role or Guardian verdict makes them authorizable
    through this gateway.
    """
    if action is None:
        return GateFinding("action", GateResult.BLOCKED, R_ACTION_UNKNOWN,
                           Provenance.ACTION_REGISTRY,
                           str(getattr(intent, "operation", ""))[:64])
    requirement = approval_requirement_for(
        action.authority_class, capability=getattr(intent, "capability", "") or "")
    if requirement is ApprovalRequirement.PROHIBITED:
        return GateFinding("action", GateResult.BLOCKED, R_ACTION_PROHIBITED,
                           Provenance.ACTION_REGISTRY, action.authority_class.value)
    return GateFinding("action", GateResult.PASSED, R_OK, Provenance.ACTION_REGISTRY,
                       f"{action.authority_class.value}/{action.risk.name}")


def _gate_run_state(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """A terminal or blocked run cannot host an execution, however its approvals
    resolved. An intent that declares no run is not run-scoped; one that declares
    a run we cannot read is UNKNOWN, not unrestricted."""
    if not inputs.run_declared:
        return GateFinding("run_state", GateResult.NOT_APPLICABLE, R_OK,
                           Provenance.RUN_STATE, "intent is not run-scoped")
    if inputs.run is None:
        return GateFinding("run_state", GateResult.UNKNOWN, R_RUN_STATE_UNKNOWN,
                           Provenance.RUN_STATE)
    raw = str(inputs.run.get("state") or "")
    try:
        state = RunState(raw)
    except ValueError:
        return GateFinding("run_state", GateResult.UNKNOWN, R_RUN_STATE_UNKNOWN,
                           Provenance.RUN_STATE, raw[:32])
    if is_terminal(state) or state in (RunState.BLOCKED, RunState.AWAITING_APPROVAL,
                                       RunState.PAUSED):
        return GateFinding("run_state", GateResult.BLOCKED, R_RUN_STATE_INVALID,
                           Provenance.RUN_STATE, state.value)

    # Ownership, not just liveness. A run being healthy says nothing about whose
    # run it is, and without this a caller with `write` could act inside anyone
    # else's run. Runs record their creator as `user:<id>` (Phase 12), so the
    # comparison is against real recorded ownership rather than an inference.
    owner = str(inputs.run.get("actor") or "")
    if not owner:
        return GateFinding("run_state", GateResult.UNKNOWN, R_RUN_STATE_UNKNOWN,
                           Provenance.RUN_STATE, "run records no owner")
    if not _actor_matches(inputs.actor_user_id or "", owner):
        return GateFinding("run_state", GateResult.BLOCKED, R_RUN_NOT_OWNED,
                           Provenance.RUN_STATE)
    return GateFinding("run_state", GateResult.PASSED, R_OK, Provenance.RUN_STATE,
                       state.value)


def _gate_approval(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """Approval is required by the action's class, and satisfied only by a
    granted, unexpired approval correlated to *this* intent's digest.

    A granted approval makes this gate stop blocking. It is not itself
    authorization -- the other gates still have to pass.
    """
    if action is None:
        return GateFinding("approval", GateResult.UNKNOWN, R_APPROVAL_UNKNOWN,
                           Provenance.APPROVAL_STORE, "action unresolved")
    requirement = approval_requirement_for(
        action.authority_class, capability=getattr(intent, "capability", "") or "")
    if requirement is ApprovalRequirement.NO_APPROVAL_REQUIRED:
        return GateFinding("approval", GateResult.NOT_APPLICABLE, R_OK,
                           Provenance.APPROVAL_STORE,
                           f"{action.authority_class.value} requires no approval")
    if inputs.approvals is None:
        return GateFinding("approval", GateResult.UNKNOWN, R_APPROVAL_UNKNOWN,
                           Provenance.APPROVAL_STORE)

    now = inputs.now if inputs.now is not None else time.time()
    digest = tool_intent_digest(intent)
    granted = None
    for appr in inputs.approvals:
        # Correlation first: an approval for another action is not evidence
        # about this one, whatever its status says.
        appr_digest = str(appr.get("tool_intent_digest") or appr.get("digest") or "")
        if appr_digest and appr_digest != digest:
            continue
        if not appr_digest:
            return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_UNCORRELATED,
                               Provenance.APPROVAL_STORE,
                               str(appr.get("approval_id", ""))[:32])
        status = str(appr.get("status") or "").lower()
        aid = str(appr.get("approval_id") or appr.get("id") or "")[:32]
        if status in ("denied", "rejected", "revoked"):
            return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_DENIED,
                               Provenance.APPROVAL_STORE, aid)
        if status == "expired":
            return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_EXPIRED,
                               Provenance.APPROVAL_STORE, aid)
        if status == "pending":
            return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_PENDING,
                               Provenance.APPROVAL_STORE, aid)
        if status in ("approved", "granted"):
            expires = appr.get("expires_at")
            if expires is not None and float(expires) <= now:
                return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_EXPIRED,
                                   Provenance.APPROVAL_STORE, aid)
            used = int(appr.get("used", 0) or 0)
            max_uses = int(appr.get("max_uses", 1) or 1)
            if used >= max_uses:
                return GateFinding("approval", GateResult.BLOCKED, R_APPROVAL_EXPIRED,
                                   Provenance.APPROVAL_STORE, f"{aid}:exhausted")
            granted = aid
    if granted is None:
        return GateFinding("approval", GateResult.MISSING, R_APPROVAL_MISSING,
                           Provenance.APPROVAL_STORE, requirement.value)
    return GateFinding("approval", GateResult.PASSED, R_OK,
                       Provenance.APPROVAL_STORE, granted)


def _gate_guardian(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    """Trading Guardian is trading-scoped, and stays that way.

    For a non-financial action Guardian is NOT_APPLICABLE -- it never evaluated
    this action and reporting "allowed" would invent a verdict. For a financial
    action a fresh, correlated verdict is *required*, and its absence is MISSING,
    not silence to be waved through.
    """
    if action is None:
        return GateFinding("guardian", GateResult.UNKNOWN, R_GUARDIAN_MISSING,
                           Provenance.TRADING_GUARDIAN, "action unresolved")
    if not action.is_financial:
        return GateFinding("guardian", GateResult.NOT_APPLICABLE, R_OK,
                           Provenance.TRADING_GUARDIAN,
                           "trading-scoped: did not evaluate this action")
    verdict = inputs.guardian_verdict
    if not verdict:
        return GateFinding("guardian", GateResult.MISSING, R_GUARDIAN_MISSING,
                           Provenance.TRADING_GUARDIAN)
    digest = tool_intent_digest(intent)
    if str(verdict.get("digest") or "") != digest:
        return GateFinding("guardian", GateResult.BLOCKED, R_GUARDIAN_UNCORRELATED,
                           Provenance.TRADING_GUARDIAN)
    at = verdict.get("at")
    if at is None:
        return GateFinding("guardian", GateResult.STALE, R_GUARDIAN_STALE,
                           Provenance.TRADING_GUARDIAN, "verdict carries no timestamp")
    now = inputs.now if inputs.now is not None else time.time()
    if now - float(at) > GUARDIAN_MAX_AGE_SEC:
        return GateFinding("guardian", GateResult.STALE, R_GUARDIAN_STALE,
                           Provenance.TRADING_GUARDIAN)
    if str(verdict.get("decision") or "").lower() not in ("allow", "pass", "allowed"):
        return GateFinding("guardian", GateResult.BLOCKED, R_GUARDIAN_BLOCKED,
                           Provenance.TRADING_GUARDIAN)
    return GateFinding("guardian", GateResult.PASSED, R_OK, Provenance.TRADING_GUARDIAN)


#: Connector lifecycle states that are executable, and the reason each
#: non-executable one denies. Presence is never permission: a configured but
#: unauthorized connector exists and still cannot act.
_CONNECTOR_REASON = {
    "unauthorized": R_CONNECTOR_UNAUTHORIZED,
    "expired": R_CONNECTOR_UNAUTHORIZED,
    "authorization_pending": R_CONNECTOR_UNAUTHORIZED,
    "unconfigured": R_CONNECTOR_ENV_BLOCKED,
    "configured": R_CONNECTOR_ENV_BLOCKED,
    "disabled": R_CONNECTOR_ENV_BLOCKED,
}


def _gate_connector(intent, action, inputs: AuthorizationInputs) -> GateFinding:
    if action is None or not action.requires_connector:
        return GateFinding("connector", GateResult.NOT_APPLICABLE, R_OK,
                           Provenance.CONNECTOR_STATE, "no connector required")
    if inputs.connector_state is None:
        return GateFinding("connector", GateResult.UNKNOWN, R_CONNECTOR_UNKNOWN,
                           Provenance.CONNECTOR_STATE)
    state = str(inputs.connector_state).lower()
    if state in ("connected", "healthy", "degraded"):
        return GateFinding("connector", GateResult.PASSED, R_OK,
                           Provenance.CONNECTOR_STATE, state)
    return GateFinding("connector", GateResult.BLOCKED,
                       _CONNECTOR_REASON.get(state, R_CONNECTOR_UNAVAILABLE),
                       Provenance.CONNECTOR_STATE, state)


#: Evaluation order. Kill switch is first so a global stop is the reported
#: reason rather than a detail behind some other refusal; identity precedes the
#: action so a caller who may not act does not learn about the action's state.
_GATES = (
    _gate_kill_switch,
    _gate_intent,
    _gate_actor,
    _gate_rbac,
    _gate_action,
    _gate_run_state,
    _gate_approval,
    _gate_guardian,
    _gate_connector,
)

#: Which blocking finding gets *reported* as the decision's reason. Separate
#: from `_GATES` because evaluation order and disclosure order are different
#: questions: every gate always runs, but only one reason is returned.
#:
#: The rule is what the reason reveals. `kill_switch` is a deliberate global stop
#: and must not be explained away by something narrower. `intent` and `action`
#: describe the caller's *own* input -- a malformed intent, an unrecognised
#: operation, a class this gateway prohibits for everyone -- so reporting them
#: leaks nothing and is far more useful than a generic refusal. Identity comes
#: next. Everything after it describes the state of a resource (a run, an
#: approval, a connector), so it is disclosed only to a caller who has already
#: cleared identity and RBAC; otherwise varying identifiers would let an
#: unauthorised caller enumerate what exists.
_REPORT_ORDER = (
    "kill_switch",
    "intent",
    "action",
    "actor",
    "rbac",
    "run_state",
    "approval",
    "guardian",
    "connector",
)

_REPORT_RANK = {name: i for i, name in enumerate(_REPORT_ORDER)}

#: Only a gate that could not be *evaluated* reports UNKNOWN. MISSING is not in
#: this set: "this action requires an approval and none exists" is a definite
#: fact and a refusal, whereas "the approval store could not be read" is a blind
#: spot. Collapsing the two would hide which of them an operator is looking at.
#: Both are equally non-permitting either way.
_UNKNOWN_RESULTS = (GateResult.UNKNOWN,)


@dataclass(frozen=True)
class AuthorizationDecision:
    """One decision about one intent. Not a capability: see `is_capability_token`."""

    decision: Decision
    reason_code: str
    intent_id: str
    #: Canonical digest of the *action* -- actor, capability, connector, operation,
    #: parameters, risk, target. Replaying this decision against a different
    #: action fails correlation because the digest will not match.
    intent_digest: str
    actor_user_id: str
    authority_class: str | None
    risk: str | None
    evaluated_at: float
    gates: tuple[GateFinding, ...] = ()

    @property
    def authorized(self) -> bool:
        return self.decision is Decision.AUTHORIZED

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "intent_id": self.intent_id,
            "intent_digest": self.intent_digest,
            "actor_user_id": self.actor_user_id or None,
            "authority_class": self.authority_class,
            "risk": self.risk,
            "evaluated_at": self.evaluated_at,
            "gates": [g.to_dict() for g in self.gates],
            "blocking": [g.to_dict() for g in self.gates if not g.positive],
            # Only the reported reason is disclosure-ordered; `blocking` is the
            # full picture and is meant for operators and audit, not for a
            # refused caller.
            # A decision is evidence that gates passed at one instant, not a
            # permission that can be presented later. Enforcement re-reads
            # canonical state; nothing here may be replayed as authority.
            "is_capability_token": False,
        }


def authorize_intent(intent, inputs: AuthorizationInputs) -> AuthorizationDecision:
    """Decide one intent. Pure: reads no store, writes nothing, executes nothing.

    Positive only when *every* gate is positive. There is no branch that reaches
    AUTHORIZED any other way, which is what makes the fail-closed property
    structural instead of a rule each gate has to remember.
    """
    now = inputs.now if inputs.now is not None else time.time()
    action = resolve_action(
        str(getattr(intent, "operation", "") or ""),
        str(getattr(intent, "connector_id", "") or ""),
        str(getattr(intent, "capability", "") or ""),
        connector_action=inputs.connector_action,
    )
    findings = tuple(gate(intent, action, inputs) for gate in _GATES)
    blocking = [f for f in findings if not f.positive]

    if not blocking:
        decision, reason = Decision.AUTHORIZED, R_OK
    else:
        reported = min(blocking, key=lambda f: _REPORT_RANK[f.gate])
        reason = reported.reason_code
        decision = (Decision.UNKNOWN if reported.result in _UNKNOWN_RESULTS
                    else Decision.DENIED)

    return AuthorizationDecision(
        decision=decision,
        reason_code=reason,
        intent_id=str(getattr(intent, "intent_id", "") or ""),
        intent_digest=tool_intent_digest(intent),
        actor_user_id=inputs.actor_user_id or "",
        authority_class=action.authority_class.value if action else None,
        risk=action.risk.name if action else None,
        evaluated_at=now,
        gates=findings,
    )
