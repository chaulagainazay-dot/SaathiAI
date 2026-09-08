"""TRADING-HEALTH-PRODUCERS-1 — typed health for five safety-critical subsystems.

TRADING-OPS-1 built the snapshot; these fill it. Every field it could type but
nothing could populate — market data, provider, Guardian, ExecutionGateway,
approval — gets a producer here.

WHAT THIS IS NOT: a second source of truth. Each producer READS an authority that
already knows its own state and maps that state into the canonical `HealthClass`.
None of them decides what a subsystem's state is; none of them changes it.

  existing subsystem state -> producer -> HealthClass + reason codes + evidence
                                       -> trading_ops.build_snapshot

THREE RULES THAT SHAPE EVERY MAPPING BELOW:

  HEALTH IS NOT READINESS. An ExecutionGateway with live trading disabled by
  policy is HEALTHY — it is doing exactly what it was configured to do. A
  provider serving public market data with no private account is HEALTHY for the
  scope it claims. Intentional safety boundaries are capabilities, not faults.

  MISSING EVIDENCE IS NEVER HEALTHY. `HealthClass` has no UNKNOWN member and this
  module will not fork the vocabulary to add one, so insufficient evidence is
  WARNING plus `evidence_sufficient=False` and an explicit
  INSUFFICIENT_EVIDENCE state code — visible, actionable, and never mistaken for
  a clean bill of health.

  CONTAINMENT IS NOT COLLAPSE. A subsystem that refuses to operate because a
  required input is missing is FAILED_SAFE, which is a different fact from
  CRITICAL — the latter means operating in unsafe ambiguity.

READ-ONLY, AND TWO PLACES WHERE THAT NEEDED CARE. `ActivationApprovalCenter.get`
and `.list` lazily expire approvals (a state transition), and
`ProviderHealthTracker.get` inserts a record for an unseen provider. Neither is a
defect in those modules, but a health read must not be what triggers them, so
both are handled explicitly below rather than inherited.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.trading_ops import OperatorAction, Subsystem, authority_for

PRODUCER_VERSION = "trading-health-producers/v1.0.0"


class StateCode(str, Enum):
    """Typed state codes, above the source vocabularies and below HealthClass.

    They exist so an operator sees WHY a subsystem is DEGRADED without having to
    learn five source enums, and so a UI never has to infer a reason from prose.
    """

    # shared
    OK = "OK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    # market data
    FEED_FRESH = "FEED_FRESH"
    FEED_STALE = "FEED_STALE"
    FEED_FROZEN = "FEED_FROZEN"
    FEED_DISCONNECTED = "FEED_DISCONNECTED"
    FEED_RECONNECTING = "FEED_RECONNECTING"
    FEED_RECONNECT_EXHAUSTED = "FEED_RECONNECT_EXHAUSTED"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    RESYNC_PENDING = "RESYNC_PENDING"
    # provider
    PROVIDER_AVAILABLE = "PROVIDER_AVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_AUTH_REQUIRED = "PROVIDER_AUTH_REQUIRED"
    PROVIDER_MISCONFIGURED = "PROVIDER_MISCONFIGURED"
    PROVIDER_QUARANTINED = "PROVIDER_QUARANTINED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_DISABLED_BY_POLICY = "PROVIDER_DISABLED_BY_POLICY"
    EXTERNAL_LICENSE_REQUIRED = "EXTERNAL_LICENSE_REQUIRED"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    DNS_BLOCKED = "DNS_BLOCKED"
    # guardian
    POLICY_LOADED = "POLICY_LOADED"
    POLICY_MISSING = "POLICY_MISSING"
    POLICY_INVALID = "POLICY_INVALID"
    REQUIRED_INPUT_UNAVAILABLE = "REQUIRED_INPUT_UNAVAILABLE"
    GUARDIAN_BYPASS_DETECTED = "GUARDIAN_BYPASS_DETECTED"
    # execution gateway
    LIVE_EXECUTION_DISABLED = "LIVE_EXECUTION_DISABLED"
    PAPER_ONLY_READY = "PAPER_ONLY_READY"
    SHADOW_ONLY_READY = "SHADOW_ONLY_READY"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    UNKNOWN_EXECUTION_STATE = "UNKNOWN_EXECUTION_STATE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    KILL_SWITCH_ENGAGED = "KILL_SWITCH_ENGAGED"
    # approval
    APPROVAL_SERVICE_AVAILABLE = "APPROVAL_SERVICE_AVAILABLE"
    APPROVAL_STORE_UNAVAILABLE = "APPROVAL_STORE_UNAVAILABLE"
    DUPLICATE_CONSUMPTION_GUARD_BROKEN = "DUPLICATE_CONSUMPTION_GUARD_BROKEN"


class HealthMode(str, Enum):
    """Provenance carried with every result. NO_FALSE_LIVE_LABEL depends on it.

    A healthy replay feed is HEALTHY + REPLAY. It is never HEALTHY + LIVE, and
    LIVE_TRADING has no member here because this program does not have it.
    """

    REPLAY = "REPLAY"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE_PUBLIC_DATA = "LIVE_PUBLIC_DATA"
    PUBLIC_DATA_ONLY = "PUBLIC_DATA_ONLY"
    HISTORICAL = "HISTORICAL"
    FIXTURE = "FIXTURE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProducedHealth:
    """One subsystem's health, as evidence rather than as a conclusion."""

    subsystem: str
    health_class: str
    state_code: str
    reason_codes: tuple = ()
    observed_at: str | None = None
    source_ref: str | None = None
    mode: str = HealthMode.UNKNOWN.value
    #: What the subsystem CAN do — distinct from whether it is well. An
    #: intentionally disabled capability belongs here, never in health_class.
    capabilities: tuple = ()
    evidence_sufficient: bool = True
    failed_safe: bool = False
    operator_action_required: str | None = None
    detail: str | None = None
    data_quality: dict = field(default_factory=dict)
    producer_version: str = PRODUCER_VERSION
    #: Permanent for every producer in this module.
    authorizes_execution: bool = False

    @property
    def authority(self) -> str:
        return authority_for(self.subsystem)

    def to_ops_finding(self) -> dict:
        """The shape `trading_ops.build_snapshot` already consumes.

        The snapshot is NOT redesigned for these producers; they adapt to it.
        """
        out = {
            "subsystem": self.subsystem,
            "health": self.health_class,
            "cause": self.state_code,
            "summary": self.detail or self.state_code,
            "state": self.state_code,
            "affected_capabilities": tuple(self.capabilities),
        }
        if self.state_code == StateCode.EXTERNAL_LICENSE_REQUIRED.value:
            out["external_reason"] = "LICENSE_REQUIRED"
        elif self.state_code == StateCode.ENVIRONMENT_BLOCKED.value:
            out["external_reason"] = "ENVIRONMENT_BLOCKED"
        elif self.state_code == StateCode.DNS_BLOCKED.value:
            out["external_reason"] = "DNS_OUTAGE"
        if self.state_code == StateCode.PROVIDER_AUTH_REQUIRED.value:
            out["auth_required"] = True
        return out


class InvalidHealthCount(ValueError):
    """A count that cannot be trusted is refused rather than silently coerced."""


def _count(value, field_name: str):
    """Validate a countable health metric. FINANCIAL-NUMERIC-1's discipline, for counts.

    These are not money, so the financial parser is not the right tool — but the
    same three failures apply and each one is silent by default:

      * `True` is an int in Python, so a boolean passed where a count belongs is
        truthy and reads as "1 unknown approval state" — a fabricated fact.
      * a float NaN is truthy too, so `if unknown_state_count:` would fire on a
        value that means nothing.
      * a negative count is not a count.

    None stays None: absent is a real answer and must not become zero.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise InvalidHealthCount(f"{field_name}: bool is not a count: {value!r}")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidHealthCount(f"{field_name}: non-finite count: {value!r}")
        if value != int(value):
            raise InvalidHealthCount(f"{field_name}: fractional count: {value!r}")
        value = int(value)
    if not isinstance(value, int):
        raise InvalidHealthCount(f"{field_name}: not a count: {value!r}")
    if value < 0:
        raise InvalidHealthCount(f"{field_name}: negative count: {value!r}")
    return value


def _insufficient(subsystem: str, detail: str, *, observed_at=None, mode=None) -> ProducedHealth:
    """The one place missing evidence is turned into a health, so it is uniform.

    WARNING rather than DEGRADED: not knowing is a monitoring gap, not a proven
    fault. What makes it safe is that it is never HEALTHY and always carries an
    operator action — the operator is told to verify by hand, not reassured.
    """
    return ProducedHealth(
        subsystem=subsystem,
        health_class=HealthClass.WARNING.value,
        state_code=StateCode.INSUFFICIENT_EVIDENCE.value,
        reason_codes=("NO_EVIDENCE",),
        observed_at=observed_at,
        mode=(mode or HealthMode.UNKNOWN.value),
        evidence_sufficient=False,
        operator_action_required=OperatorAction.MANUAL_OPERATOR_VALIDATION.value,
        detail=detail,
    )


# ── 1. market data ──────────────────────────────────────────────────────────
#
# Reuses `market_observation.models.DataFreshness` and `ObservationSource` rather
# than inventing feed states. Source maps to MODE, freshness maps to HEALTH, and
# the two stay separate — which is the whole of NO_FALSE_LIVE_LABEL: a frozen
# local cache serving fresh-enough rows is HEALTHY for what it is, and saying so
# without saying LIVE requires both fields.
MODE_FOR_OBSERVATION_SOURCE = {
    "OFFLINE_FIXTURE": HealthMode.FIXTURE.value,
    "FROZEN_LOCAL_CACHE": HealthMode.HISTORICAL.value,
    "GOVERNED_DATASET": HealthMode.REPLAY.value,
    "AUTHENTICATED_LIVE_FORBIDDEN": HealthMode.PUBLIC_DATA_ONLY.value,
}


def market_data_health(
    *,
    connected: bool | None = None,
    freshness: str | None = None,
    source: str | None = None,
    observed_at: str | None = None,
    last_valid_observation: str | None = None,
    sequence_gap: bool = False,
    resync_pending: bool = False,
    reconnecting: bool = False,
    reconnect_exhausted: bool = False,
    contained: bool = True,
    mode: str | None = None,
    source_ref: str | None = None,
) -> ProducedHealth:
    """Health of the market-data feed. Replay is not a failure.

    `contained` records whether the feed's own supervision refuses to serve when
    it cannot reconnect. Exhausted reconnection under containment is FAILED_SAFE
    — stopped on purpose; without containment it is CRITICAL — still nominally
    live while unable to refresh, which is the dangerous case.
    """
    resolved_mode = mode or MODE_FOR_OBSERVATION_SOURCE.get(
        str(source or "").upper(), HealthMode.UNKNOWN.value,
    )
    if connected is None and freshness is None:
        return _insufficient(
            Subsystem.MARKET_DATA.value,
            "no feed connectivity or freshness reported",
            observed_at=observed_at, mode=resolved_mode,
        )

    reasons: list[str] = []
    fresh = str(freshness or "").upper()

    if reconnect_exhausted:
        reasons.append("RECONNECT_EXHAUSTED")
        health = HealthClass.FAILED_SAFE.value if contained else HealthClass.CRITICAL.value
        state = StateCode.FEED_RECONNECT_EXHAUSTED.value
    elif connected is False:
        reasons.append("TRANSPORT_DISCONNECTED")
        health, state = HealthClass.DEGRADED.value, StateCode.FEED_DISCONNECTED.value
    elif sequence_gap:
        # A gap means the book cannot be trusted until resynchronised. Serving
        # from it would be worse than admitting the hole.
        reasons.append("SEQUENCE_GAP")
        health, state = HealthClass.DEGRADED.value, StateCode.SEQUENCE_GAP.value
    elif fresh == "STALE":
        reasons.append("DATA_STALE")
        health, state = HealthClass.DEGRADED.value, StateCode.FEED_STALE.value
    elif fresh == "FROZEN":
        reasons.append("DATA_FROZEN")
        health, state = HealthClass.DEGRADED.value, StateCode.FEED_FROZEN.value
    elif resync_pending:
        reasons.append("RESYNC_PENDING")
        health, state = HealthClass.WARNING.value, StateCode.RESYNC_PENDING.value
    elif reconnecting:
        # Temporary: the transport is doing the right thing about a blip.
        reasons.append("RECONNECTING")
        health, state = HealthClass.WARNING.value, StateCode.FEED_RECONNECTING.value
    elif fresh in ("", "UNKNOWN"):
        # CONNECTIVITY IS NOT FRESHNESS. A socket that is up while no rows arrive
        # is the classic silent feed failure, so an unreported freshness can never
        # reach the HEALTHY branch below on the strength of `connected` alone.
        # The fault branches above still stand: a disconnect or a gap is positive
        # evidence of a problem and is reported as one.
        return _insufficient(
            Subsystem.MARKET_DATA.value,
            "connected but freshness not reported" if connected else "freshness unknown",
            observed_at=observed_at, mode=resolved_mode,
        )
    else:
        health, state = HealthClass.HEALTHY.value, StateCode.FEED_FRESH.value

    return ProducedHealth(
        subsystem=Subsystem.MARKET_DATA.value,
        health_class=health,
        state_code=state,
        reason_codes=tuple(reasons),
        observed_at=observed_at,
        source_ref=source_ref or source,
        mode=resolved_mode,
        capabilities=("MARKET_DATA_READ",),
        failed_safe=health == HealthClass.FAILED_SAFE.value,
        operator_action_required=(
            OperatorAction.RESTART_PUBLIC_FEED.value
            if health in (HealthClass.DEGRADED.value, HealthClass.CRITICAL.value,
                          HealthClass.FAILED_SAFE.value) else None
        ),
        detail=state.replace("_", " ").lower(),
        data_quality={
            "freshness": fresh or None,
            "last_valid_observation": last_valid_observation,
            "sequence_gap": bool(sequence_gap),
        },
    )


# ── 2. provider ─────────────────────────────────────────────────────────────
#
# `ProviderHealthState` already distinguishes nine conditions, and its own module
# already says a healthy provider does not imply authorised execution. This is the
# missing half: the mapping into HealthClass.
#
# DISABLED maps to HEALTHY deliberately. A provider switched off by policy is not
# broken, and reporting it as a fault would train an operator to ignore the field.
# The fact travels as a CAPABILITY instead.
HEALTH_FOR_PROVIDER_STATE = {
    "HEALTHY": (HealthClass.HEALTHY.value, StateCode.PROVIDER_AVAILABLE.value),
    "DEGRADED": (HealthClass.DEGRADED.value, StateCode.PROVIDER_UNAVAILABLE.value),
    "RATE_LIMITED": (HealthClass.WARNING.value, StateCode.PROVIDER_RATE_LIMITED.value),
    "AUTH_BLOCKED": (HealthClass.DEGRADED.value, StateCode.PROVIDER_AUTH_REQUIRED.value),
    "UNAVAILABLE": (HealthClass.DEGRADED.value, StateCode.PROVIDER_UNAVAILABLE.value),
    "MISCONFIGURED": (HealthClass.CRITICAL.value, StateCode.PROVIDER_MISCONFIGURED.value),
    "QUARANTINED": (HealthClass.DEGRADED.value, StateCode.PROVIDER_QUARANTINED.value),
    "DISABLED": (HealthClass.HEALTHY.value, StateCode.PROVIDER_DISABLED_BY_POLICY.value),
}

#: Blockers no amount of retrying resolves. Kept separate from transport failure
#: so the operator is never told to retry a licence.
EXTERNAL_BLOCKER_STATE = {
    "LICENSE_REQUIRED": StateCode.EXTERNAL_LICENSE_REQUIRED.value,
    "ENVIRONMENT_BLOCKED": StateCode.ENVIRONMENT_BLOCKED.value,
    "DNS_BLOCKED": StateCode.DNS_BLOCKED.value,
}


def provider_health(
    *,
    provider_id: str | None = None,
    state: str | None = None,
    external_blocker: str | None = None,
    scope: str = "PUBLIC_MARKET_DATA",
    observed_at: str | None = None,
    last_error: str | None = None,
    mode: str | None = None,
) -> ProducedHealth:
    """Health of one trading-relevant provider.

    `scope` is load-bearing. A healthy public market-data transport says nothing
    about private account access, so the scope travels as the capability and a
    public provider never implies a trading account.

    NOTE ON THE SOURCE: `ProviderHealthTracker.get()` inserts a record for an
    unseen provider, so this takes the STATE rather than the tracker. A health
    read must not be what creates provider records.
    """
    if external_blocker:
        code = EXTERNAL_BLOCKER_STATE.get(str(external_blocker).upper())
        if code:
            return ProducedHealth(
                subsystem=Subsystem.PROVIDER.value,
                health_class=HealthClass.DEGRADED.value,
                state_code=code,
                reason_codes=(str(external_blocker).upper(),),
                observed_at=observed_at,
                source_ref=provider_id,
                mode=mode or HealthMode.PUBLIC_DATA_ONLY.value,
                capabilities=(scope,),
                operator_action_required=OperatorAction.EXTERNAL_ACTION_REQUIRED.value,
                detail=f"{provider_id or 'provider'}: {code} — not resolvable by retry",
            )

    if state is None:
        return _insufficient(
            Subsystem.PROVIDER.value,
            f"no state reported for {provider_id or 'provider'}",
            observed_at=observed_at, mode=mode,
        )
    key = str(state).upper()
    if key == "UNKNOWN" or key not in HEALTH_FOR_PROVIDER_STATE:
        return _insufficient(
            Subsystem.PROVIDER.value,
            f"provider state {key} carries no health evidence",
            observed_at=observed_at, mode=mode,
        )

    health, code = HEALTH_FOR_PROVIDER_STATE[key]
    action = None
    if code == StateCode.PROVIDER_AUTH_REQUIRED.value:
        action = OperatorAction.REAUTHENTICATE_PROVIDER.value
    elif health in (HealthClass.DEGRADED.value, HealthClass.CRITICAL.value):
        action = OperatorAction.RESTART_PUBLIC_FEED.value

    return ProducedHealth(
        subsystem=Subsystem.PROVIDER.value,
        health_class=health,
        state_code=code,
        reason_codes=(key,),
        observed_at=observed_at,
        source_ref=provider_id,
        mode=mode or HealthMode.PUBLIC_DATA_ONLY.value,
        capabilities=(scope,),
        operator_action_required=action,
        detail=f"{provider_id or 'provider'} {key}",
        data_quality={"last_error": last_error},
    )


# ── 3. Guardian ─────────────────────────────────────────────────────────────
def guardian_health(
    *,
    policy_loaded: bool | None = None,
    policy_version: str | None = None,
    policy_valid: bool = True,
    evaluation_available: bool = True,
    required_inputs_available: bool = True,
    fail_closed: bool = True,
    bypass_detected: bool = False,
    blocked_count: int | None = None,
    authority_mode: str | None = None,
    observed_at: str | None = None,
    mode: str | None = None,
) -> ProducedHealth:
    """Health of the trading Guardian. The subtlest of the five.

    THE CENTRAL RULE: BLOCKING IS NOT FAILING. `blocked_count` is accepted and
    recorded, and it is deliberately NOT an input to the classification. A
    Guardian that refuses a hundred unsafe trades is a Guardian working perfectly,
    and any code path that let a block count drag health downward would teach an
    operator to want fewer refusals.

    What actually degrades Guardian is being unable to DECIDE: no policy, an
    invalid one, an evaluator that will not run, or a missing risk input. And a
    detected bypass is CRITICAL, because a Guardian that can be gone around is
    worse than one that is down — the system looks protected and is not.
    """
    blocked_count = _count(blocked_count, "blocked_count")
    if policy_loaded is None and not bypass_detected:
        return _insufficient(
            Subsystem.GUARDIAN.value, "guardian policy state not reported",
            observed_at=observed_at, mode=mode,
        )

    reasons: list[str] = []
    if bypass_detected:
        # Never FAILED_SAFE: nothing is contained if the gate can be walked around.
        return ProducedHealth(
            subsystem=Subsystem.GUARDIAN.value,
            health_class=HealthClass.CRITICAL.value,
            state_code=StateCode.GUARDIAN_BYPASS_DETECTED.value,
            reason_codes=("BYPASS_DETECTED",),
            observed_at=observed_at,
            mode=mode or HealthMode.PAPER.value,
            operator_action_required=OperatorAction.ENGAGE_EXISTING_KILL_SWITCH.value,
            detail="guardian bypass detected — protection cannot be assumed",
            data_quality={"policy_version": policy_version},
        )

    if not policy_loaded:
        reasons.append("POLICY_MISSING")
        health = HealthClass.FAILED_SAFE.value if fail_closed else HealthClass.CRITICAL.value
        state = StateCode.POLICY_MISSING.value
    elif not policy_valid:
        reasons.append("POLICY_INVALID")
        health = HealthClass.FAILED_SAFE.value if fail_closed else HealthClass.CRITICAL.value
        state = StateCode.POLICY_INVALID.value
    elif not evaluation_available:
        reasons.append("EVALUATION_UNAVAILABLE")
        health = HealthClass.FAILED_SAFE.value if fail_closed else HealthClass.CRITICAL.value
        state = StateCode.POLICY_INVALID.value
    elif not required_inputs_available:
        # Guardian cannot judge without its risk inputs. Refusing is correct, and
        # FAILED_SAFE names it as containment rather than malfunction.
        reasons.append("REQUIRED_INPUT_UNAVAILABLE")
        health = HealthClass.FAILED_SAFE.value if fail_closed else HealthClass.CRITICAL.value
        state = StateCode.REQUIRED_INPUT_UNAVAILABLE.value
    else:
        health, state = HealthClass.HEALTHY.value, StateCode.POLICY_LOADED.value

    return ProducedHealth(
        subsystem=Subsystem.GUARDIAN.value,
        health_class=health,
        state_code=state,
        reason_codes=tuple(reasons),
        observed_at=observed_at,
        mode=mode or HealthMode.PAPER.value,
        capabilities=("POLICY_ENFORCEMENT",),
        failed_safe=health == HealthClass.FAILED_SAFE.value,
        operator_action_required=(
            OperatorAction.MANUAL_OPERATOR_VALIDATION.value
            if health != HealthClass.HEALTHY.value else None
        ),
        detail=state.replace("_", " ").lower(),
        data_quality={
            "policy_version": policy_version,
            "authority_mode": authority_mode,
            # Recorded as CONTEXT for the operator, never as an input above.
            "blocked_count": blocked_count,
        },
    )


# ── 4. ExecutionGateway ─────────────────────────────────────────────────────
def execution_gateway_health(
    *,
    gateway_available: bool | None = None,
    live_execution_enabled: bool = False,
    paper_ready: bool = True,
    shadow_only: bool = False,
    unknown_execution_state: bool = False,
    reconciliation_required: bool = False,
    kill_switch_engaged: bool = False,
    approval_required: bool = True,
    contained: bool = True,
    observed_at: str | None = None,
    mode: str | None = None,
) -> ProducedHealth:
    """Health of the execution authority.

    DISABLED IS NOT BROKEN. `live_execution_enabled=False` is this program's
    intended posture, so it is HEALTHY with a LIVE_EXECUTION_DISABLED capability
    — not CRITICAL. Reporting the designed configuration as a fault would make
    the whole panel meaningless, since it would be red forever by construction.

    UNKNOWN EXECUTION STATE IS THE SEVERE ONE. A post-send ambiguity means an
    order may or may not exist. It is CRITICAL, it demands reconciliation, and
    NOTHING here retries it — that is NO_UNKNOWN_AUTO_RETRY, and this producer
    could not retry even if asked, because it calls nothing.
    """
    if gateway_available is None:
        return _insufficient(
            Subsystem.EXECUTION_GATEWAY.value, "gateway availability not reported",
            observed_at=observed_at, mode=mode,
        )

    caps: list[str] = []
    caps.append("LIVE_EXECUTION_ENABLED" if live_execution_enabled
                else StateCode.LIVE_EXECUTION_DISABLED.value)
    if approval_required:
        caps.append("APPROVAL_REQUIRED")
    if paper_ready:
        caps.append("PAPER_EXECUTION")
    if shadow_only:
        caps.append("SHADOW_ONLY")

    reasons: list[str] = []
    if unknown_execution_state:
        reasons.append("UNKNOWN_EXECUTION_STATE")
        health, state = HealthClass.CRITICAL.value, StateCode.UNKNOWN_EXECUTION_STATE.value
        action = OperatorAction.REVIEW_RECONCILIATION.value
    elif reconciliation_required:
        reasons.append("RECONCILIATION_REQUIRED")
        health, state = HealthClass.CRITICAL.value, StateCode.RECONCILIATION_REQUIRED.value
        action = OperatorAction.REVIEW_RECONCILIATION.value
    elif kill_switch_engaged:
        # Stopped on purpose by an operator — contained, not chaotic.
        reasons.append("KILL_SWITCH_ENGAGED")
        health, state = HealthClass.FAILED_SAFE.value, StateCode.KILL_SWITCH_ENGAGED.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    elif not gateway_available:
        reasons.append("GATEWAY_UNAVAILABLE")
        health = HealthClass.FAILED_SAFE.value if contained else HealthClass.CRITICAL.value
        state, action = (StateCode.GATEWAY_UNAVAILABLE.value,
                         OperatorAction.MANUAL_OPERATOR_VALIDATION.value)
    elif shadow_only:
        health, state, action = (HealthClass.HEALTHY.value,
                                 StateCode.SHADOW_ONLY_READY.value, None)
    elif paper_ready:
        health, state, action = (HealthClass.HEALTHY.value,
                                 StateCode.PAPER_ONLY_READY.value, None)
    else:
        # Available but nothing it can serve: not a fault, not a working path.
        reasons.append("NO_EXECUTION_PATH_READY")
        health, state = HealthClass.WARNING.value, StateCode.GATEWAY_UNAVAILABLE.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value

    return ProducedHealth(
        subsystem=Subsystem.EXECUTION_GATEWAY.value,
        health_class=health,
        state_code=state,
        reason_codes=tuple(reasons),
        observed_at=observed_at,
        mode=mode or (HealthMode.SHADOW.value if shadow_only else HealthMode.PAPER.value),
        capabilities=tuple(caps),
        failed_safe=health == HealthClass.FAILED_SAFE.value,
        operator_action_required=action,
        detail=state.replace("_", " ").lower(),
        data_quality={"live_execution_enabled": bool(live_execution_enabled)},
    )


# ── 5. approval ─────────────────────────────────────────────────────────────
def approval_health(
    *,
    service_available: bool | None = None,
    pending: int | None = None,
    expired: int | None = None,
    duplicate_guard_ok: bool = True,
    store_integrity_ok: bool = True,
    audit_available: bool = True,
    unknown_state_count: int = 0,
    contained: bool = True,
    observed_at: str | None = None,
    mode: str | None = None,
) -> ProducedHealth:
    """Health of the approval authority.

    A QUEUE IS NOT A FAULT. Pending approvals mean the system is correctly
    waiting for a human, and expired ones mean expiry worked. Neither moves
    health, and both are reported as counts so an operator can see the workload
    without the panel crying wolf.

    What actually matters is whether approval can still be TRUSTED: a broken
    duplicate-consumption guard is CRITICAL, because an approval that can be
    spent twice is indistinguishable from no approval at all.

    THIS FUNCTION CONSUMES NOTHING. It takes counts, not the approval centre,
    precisely because `ActivationApprovalCenter.get`/`.list` lazily expire
    approvals — a state transition that belongs to that authority and must not be
    triggered by a health read.
    """
    pending = _count(pending, "pending")
    expired = _count(expired, "expired")
    unknown_state_count = _count(unknown_state_count, "unknown_state_count") or 0
    if service_available is None:
        return _insufficient(
            Subsystem.APPROVAL.value, "approval service availability not reported",
            observed_at=observed_at, mode=mode,
        )

    reasons: list[str] = []
    if not duplicate_guard_ok:
        reasons.append("DUPLICATE_CONSUMPTION_GUARD_BROKEN")
        health = HealthClass.CRITICAL.value
        state = StateCode.DUPLICATE_CONSUMPTION_GUARD_BROKEN.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    elif not store_integrity_ok:
        reasons.append("STORE_INTEGRITY_FAILED")
        health = HealthClass.FAILED_SAFE.value if contained else HealthClass.CRITICAL.value
        state = StateCode.APPROVAL_STORE_UNAVAILABLE.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    elif not service_available:
        reasons.append("SERVICE_UNAVAILABLE")
        health = HealthClass.FAILED_SAFE.value if contained else HealthClass.CRITICAL.value
        state = StateCode.APPROVAL_STORE_UNAVAILABLE.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    elif unknown_state_count:
        # An approval whose state cannot be determined cannot be relied on.
        reasons.append("UNKNOWN_APPROVAL_STATE")
        health, state = HealthClass.DEGRADED.value, StateCode.INSUFFICIENT_EVIDENCE.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    elif not audit_available:
        reasons.append("AUDIT_UNAVAILABLE")
        health, state = HealthClass.WARNING.value, StateCode.APPROVAL_SERVICE_AVAILABLE.value
        action = OperatorAction.MANUAL_OPERATOR_VALIDATION.value
    else:
        health, state, action = (HealthClass.HEALTHY.value,
                                 StateCode.APPROVAL_SERVICE_AVAILABLE.value, None)

    return ProducedHealth(
        subsystem=Subsystem.APPROVAL.value,
        health_class=health,
        state_code=state,
        reason_codes=tuple(reasons),
        observed_at=observed_at,
        mode=mode or HealthMode.PAPER.value,
        capabilities=("APPROVAL_GRANT", "SINGLE_USE_CONSUMPTION"),
        failed_safe=health == HealthClass.FAILED_SAFE.value,
        operator_action_required=action,
        detail=state.replace("_", " ").lower(),
        # Workload, not health. Present so the operator sees it and the
        # classifier above provably does not.
        data_quality={"pending": pending, "expired": expired},
    )


ALL_PRODUCERS = (
    market_data_health, provider_health, guardian_health,
    execution_gateway_health, approval_health,
)


def snapshot_from_producers(
    healths,
    *,
    observed_at: str | None,
    mode: str,
    extra_findings=(),
    **snapshot_kwargs,
):
    """Feed produced health into the EXISTING ops snapshot, unchanged.

    TRADING-OPS-1's `build_snapshot` is not redesigned for these producers — they
    adapt to it, which is why `to_ops_finding` exists. `extra_findings` carries
    subsystems that already had producers (strategy, shadow, paper) so one
    snapshot can mix both without either side knowing about the other.
    """
    from saathi.platform.tg.trading_ops import build_snapshot

    findings = [h.to_ops_finding() for h in healths] + [dict(f) for f in extra_findings]
    return build_snapshot(
        observed_at=observed_at, mode=mode, subsystems=findings, **snapshot_kwargs,
    )


#: The five subsystems this milestone exists to populate. Used by the
#: UNKNOWN-reduction test to prove wiring rather than assert it.
PRODUCED_SUBSYSTEMS = (
    Subsystem.MARKET_DATA.value,
    Subsystem.PROVIDER.value,
    Subsystem.GUARDIAN.value,
    Subsystem.EXECUTION_GATEWAY.value,
    Subsystem.APPROVAL.value,
)
