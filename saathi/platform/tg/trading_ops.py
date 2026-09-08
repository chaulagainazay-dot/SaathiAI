"""TRADING-OPS-1 — one operator-facing view over the trading stack.

The trading program already has a dense operational substrate: a health
vocabulary, a degradation policy, a kill switch, incident stores, recovery
suites, runbooks and per-subsystem monitors. NONE of it is rebuilt here.

What did not exist is the binding. `CommandSurface` renders five panels but every
input is a caller-supplied keyword — thirteen of them — so nothing in the
repository could assemble the answer to "is trading safe right now?" without
already knowing it. `OperationalMonitor` answers that question authoritatively
for the paper store and has no view of market data, Guardian, shadow sessions or
the kill switch. This module is the join, and nothing more.

WHAT IT REUSES, RATHER THAN RESTATES:
  HealthClass          paper_activation/ops/models   the canonical vocabulary
  _worst               paper_activation/ops/monitoring the canonical aggregator
  resilience.degrade   tg/resilience                 failure -> required response
  KillSwitchStore      tg/kill_switch                kill-switch truth
  strategy_monitor     tg/strategy_monitor           strategy health
  shadow_session       tg/shadow_session             shadow reconciliation

OPERATIONS SUPERVISION IS NOT EXECUTION AUTHORITY. This module observes,
aggregates, classifies and RECOMMENDS. It creates no order, consumes no approval,
touches no ledger, and changes no policy. Every operator action it emits names
the authority that owns it, because an action with no owner is a button that
lies.

READINESS IS NOT HEALTH. A stack can be perfectly healthy in SHADOW mode and
still not be authorised to trade. The snapshot reports both, separately, and
`live_trading_authorized` is permanently False.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum

from saathi.platform.tg.paper_activation.ops.models import HealthClass

# The canonical aggregator, imported rather than reimplemented. Underscore-named
# in its own module, but forking it would create a second precedence policy that
# could silently drift from the one the paper monitor already certifies against.
# A test pins that this module's aggregation IS that function.
from saathi.platform.tg.paper_activation.ops.monitoring import _worst as _canonical_worst
from saathi.platform.tg.resilience import FailureMode, Response, degrade

OPS_VERSION = "trading-ops/v1.0.0"

#: Permanently false for this program. Stated as data so a test can assert it.
LIVE_TRADING_AUTHORIZED = False


class OpsMode(str, Enum):
    """How the stack is running. LIVE is deliberately absent, not merely unused."""

    REPLAY = "REPLAY"
    SHADOW = "SHADOW"
    PAPER = "PAPER"


class Subsystem(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    PROVIDER = "PROVIDER"
    STRATEGY = "STRATEGY"
    PORTFOLIO = "PORTFOLIO"
    RISK = "RISK"
    GUARDIAN = "GUARDIAN"
    EXECUTION_GATEWAY = "EXECUTION_GATEWAY"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    RECONCILIATION = "RECONCILIATION"
    APPROVAL = "APPROVAL"
    KILL_SWITCH = "KILL_SWITCH"


#: Which module owns each subsystem's truth. Emitted with every operator action so
#: the operator is never told to "fix" something without being told who fixes it.
AUTHORITY_OF = {
    Subsystem.MARKET_DATA: "saathi.platform.tg.market_data.service",
    Subsystem.PROVIDER: "saathi.platform.tg.market_data.service",
    Subsystem.STRATEGY: "saathi.platform.tg.strategy_monitor",
    Subsystem.PORTFOLIO: "saathi.platform.tg.paper_activation.ops.monitoring",
    Subsystem.RISK: "saathi.platform.tg.portfolio_risk",
    Subsystem.GUARDIAN: "saathi.platform.tg.service.TradingGuardianService",
    Subsystem.EXECUTION_GATEWAY: "saathi.connectors.platform.execution",
    Subsystem.SHADOW: "saathi.platform.tg.shadow_session",
    Subsystem.PAPER: "saathi.platform.tg.paper_activation.ops.monitoring",
    Subsystem.RECONCILIATION: "saathi.platform.tg.reconciliation_v2",
    Subsystem.APPROVAL: "saathi.platform.tg.paper_activation.approvals",
    Subsystem.KILL_SWITCH: "saathi.platform.tg.kill_switch.KillSwitchStore",
}


def _known(value: str) -> bool:
    return value in {s.value for s in Subsystem}


def _subsystem(value: str) -> "Subsystem":
    return Subsystem(value)


def authority_for(subsystem: str) -> str:
    """The module that owns a subsystem's truth, or UNKNOWN for a foreign name.

    UNKNOWN is deliberate rather than a raise: an unrecognised subsystem must
    still be reportable, because dropping it would hide a real condition.
    """
    if not _known(subsystem):
        return "UNKNOWN"
    return AUTHORITY_OF.get(Subsystem(subsystem), "UNKNOWN")


class OperatorAction(str, Enum):
    """Typed actions. Every one is owned by an authority; none is a generic 'Fix'."""

    ACKNOWLEDGE_INCIDENT = "ACKNOWLEDGE_INCIDENT"
    REVIEW_RECONCILIATION = "REVIEW_RECONCILIATION"
    ENGAGE_EXISTING_KILL_SWITCH = "ENGAGE_EXISTING_KILL_SWITCH"
    RESTART_PUBLIC_FEED = "RESTART_PUBLIC_FEED"
    REVIEW_STRATEGY_DEGRADATION = "REVIEW_STRATEGY_DEGRADATION"
    REAUTHENTICATE_PROVIDER = "REAUTHENTICATE_PROVIDER"
    MANUAL_OPERATOR_VALIDATION = "MANUAL_OPERATOR_VALIDATION"
    #: For conditions SaathiOS cannot resolve at all — a commercial feed licence,
    #: say. Emitting RETRY for these would be a lie about what is possible.
    EXTERNAL_ACTION_REQUIRED = "EXTERNAL_ACTION_REQUIRED"


class RecoveryState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    AUTOMATIC_SAFE_RECOVERY = "AUTOMATIC_SAFE_RECOVERY"
    OPERATOR_ACTION_REQUIRED = "OPERATOR_ACTION_REQUIRED"
    EXTERNAL_DEPENDENCY_BLOCKED = "EXTERNAL_DEPENDENCY_BLOCKED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FAILED_SAFE = "FAILED_SAFE"


class ReconciliationState(str, Enum):
    HEALTHY = "HEALTHY"
    REQUIRED = "REQUIRED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


def worst_health(*classes: str) -> str:
    """Overall health by explicit precedence — never an average.

    Delegates to the paper monitor's own aggregator so one CRITICAL safety
    subsystem cannot be diluted to WARNING by seven healthy ones, and so this
    module cannot drift from the ordering already certified there.
    """
    return _canonical_worst(*classes)


@dataclass(frozen=True)
class SubsystemHealth:
    subsystem: str
    health: str
    authority: str
    detail: str | None = None
    #: True when this subsystem is a symptom of another's failure. Symptoms still
    #: report their health honestly; they simply do not raise their own incident.
    caused_by: str | None = None


@dataclass(frozen=True)
class OpsIncident:
    """One incident. Deduplicated by cause, not by observation count."""

    incident_id: str
    dedup_key: str
    subsystem: str
    severity: str
    state: str
    opened_at: str | None
    last_updated_at: str | None
    summary: str
    authority: str
    affected_capabilities: tuple = ()
    #: Symptoms of THIS incident, by subsystem. The convergence guarantee: a market
    #: data disconnect that blocks a strategy is one incident with a symptom, not
    #: two unrelated alerts competing for the operator's attention.
    symptoms: tuple = ()
    caused_by: str | None = None
    containment: str | None = None
    recommended_action: str | None = None
    runbook_ref: str | None = None
    acknowledged: bool = False


@dataclass(frozen=True)
class RequiredAction:
    action: str
    subsystem: str
    authority: str
    detail: str
    incident_id: str | None = None
    #: False means SaathiOS cannot perform this itself. Never present such an
    #: action as a retry.
    automatable: bool = False


@dataclass(frozen=True)
class TradingOperationsSnapshot:
    """Derived, read-only. Persisted nowhere; recomputed from its sources."""

    snapshot_id: str
    observed_at: str | None
    mode: str
    overall_health: str
    subsystems: tuple = ()
    incidents: tuple = ()
    kill_switch_state: dict = field(default_factory=dict)
    recovery_state: str = RecoveryState.NOT_REQUIRED.value
    reconciliation_state: str = ReconciliationState.HEALTHY.value
    operator_actions_required: tuple = ()
    source_versions: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)
    ops_version: str = OPS_VERSION
    #: Readiness is NOT health. A healthy SHADOW stack is still not live-authorised.
    live_trading_authorized: bool = LIVE_TRADING_AUTHORIZED
    authorizes_execution: bool = False

    def to_public(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at,
            "mode": self.mode,
            "overall_health": self.overall_health,
            "subsystems": [vars(s) for s in self.subsystems],
            "incidents": [vars(i) for i in self.incidents],
            "kill_switch_state": dict(self.kill_switch_state),
            "recovery_state": self.recovery_state,
            "reconciliation_state": self.reconciliation_state,
            "operator_actions_required": [vars(a) for a in self.operator_actions_required],
            "source_versions": dict(self.source_versions),
            "data_quality": dict(self.data_quality),
            "ops_version": self.ops_version,
            "live_trading_authorized": self.live_trading_authorized,
            "authorizes_execution": self.authorizes_execution,
            "health_classes": [h.value for h in HealthClass],
        }


def dedup_key(subsystem: str, cause: str, scope: str = "") -> str:
    """Stable key for one CAUSE, so re-observing it does not spam the operator.

    Deliberately excludes any observation time or counter: the same unchanged
    condition seen a hundred times is one incident, and only a change in cause or
    scope makes it a different one.
    """
    blob = json.dumps({"s": subsystem, "c": cause, "k": scope}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def snapshot_id(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return "ops_" + hashlib.sha256(blob.encode()).hexdigest()[:16]


#: Failure modes SaathiOS genuinely cannot resolve on its own. These map to
#: EXTERNAL_ACTION_REQUIRED rather than to any retry.
EXTERNAL_BLOCKERS = frozenset({"LICENSE_REQUIRED", "ENVIRONMENT_BLOCKED", "DNS_OUTAGE"})

#: Failure -> the operator action its owning authority supports. A failure absent
#: from this table gets MANUAL_OPERATOR_VALIDATION, never an invented remedy.
ACTION_FOR_FAILURE = {
    FailureMode.WEBSOCKET_DISCONNECT: OperatorAction.RESTART_PUBLIC_FEED,
    FailureMode.PROVIDER_OUTAGE: OperatorAction.RESTART_PUBLIC_FEED,
    FailureMode.STALE_MARKET_DATA: OperatorAction.RESTART_PUBLIC_FEED,
    FailureMode.SEQUENCE_GAP: OperatorAction.RESTART_PUBLIC_FEED,
    FailureMode.DNS_OUTAGE: OperatorAction.EXTERNAL_ACTION_REQUIRED,
    FailureMode.OMS_AMBIGUITY: OperatorAction.REVIEW_RECONCILIATION,
    FailureMode.RECONCILIATION_MISMATCH: OperatorAction.REVIEW_RECONCILIATION,
    FailureMode.PROCESS_RESTART: OperatorAction.REVIEW_RECONCILIATION,
    FailureMode.DB_RESTART: OperatorAction.REVIEW_RECONCILIATION,
    FailureMode.SCHEMA_DRIFT: OperatorAction.MANUAL_OPERATOR_VALIDATION,
    FailureMode.PARTIAL_WRITE: OperatorAction.MANUAL_OPERATOR_VALIDATION,
    FailureMode.DISK_PRESSURE: OperatorAction.MANUAL_OPERATOR_VALIDATION,
    FailureMode.KILL_SWITCH: OperatorAction.MANUAL_OPERATOR_VALIDATION,
}

#: Which subsystem owns each failure mode, so an action is addressed to the
#: authority that can actually act on it. Routing disk pressure to reconciliation,
#: say, would hand the operator the wrong owner.
SUBSYSTEM_FOR_FAILURE = {
    FailureMode.PROVIDER_OUTAGE: Subsystem.PROVIDER,
    FailureMode.DNS_OUTAGE: Subsystem.PROVIDER,
    FailureMode.WEBSOCKET_DISCONNECT: Subsystem.MARKET_DATA,
    FailureMode.STALE_MARKET_DATA: Subsystem.MARKET_DATA,
    FailureMode.SEQUENCE_GAP: Subsystem.MARKET_DATA,
    FailureMode.SCHEMA_DRIFT: Subsystem.MARKET_DATA,
    FailureMode.OMS_AMBIGUITY: Subsystem.RECONCILIATION,
    FailureMode.RECONCILIATION_MISMATCH: Subsystem.RECONCILIATION,
    FailureMode.PROCESS_RESTART: Subsystem.RECONCILIATION,
    FailureMode.DB_RESTART: Subsystem.PAPER,
    FailureMode.PARTIAL_WRITE: Subsystem.PAPER,
    FailureMode.DISK_PRESSURE: Subsystem.PAPER,
    FailureMode.DUPLICATE_EVENT: Subsystem.PAPER,
    FailureMode.KILL_SWITCH: Subsystem.KILL_SWITCH,
}

#: Degradation response -> the health it represents. Reuses both existing
#: vocabularies instead of inventing a bridge severity.
HEALTH_FOR_RESPONSE = {
    Response.CONTINUE_DEGRADED: HealthClass.WARNING.value,
    Response.HALT_NEW_ORDERS: HealthClass.DEGRADED.value,
    Response.RECONCILE_FIRST: HealthClass.CRITICAL.value,
    Response.FAIL_CLOSED: HealthClass.FAILED_SAFE.value,
}

#: Recovery classification per response. `auto_retry` is structurally False for
#: every mapped failure in resilience.py, which is what keeps an ambiguous
#: financial operation from being retried here.
RECOVERY_FOR_RESPONSE = {
    Response.CONTINUE_DEGRADED: RecoveryState.AUTOMATIC_SAFE_RECOVERY,
    Response.HALT_NEW_ORDERS: RecoveryState.OPERATOR_ACTION_REQUIRED,
    Response.RECONCILE_FIRST: RecoveryState.RECONCILIATION_REQUIRED,
    Response.FAIL_CLOSED: RecoveryState.FAILED_SAFE,
}


def health_for_failure(failure: FailureMode) -> str:
    """Map a failure onto the canonical health vocabulary via its required response."""
    return HEALTH_FOR_RESPONSE[degrade(failure).response]


def action_for_failure(failure: FailureMode, *, external_reason: str = "") -> OperatorAction:
    if external_reason in EXTERNAL_BLOCKERS:
        return OperatorAction.EXTERNAL_ACTION_REQUIRED
    return ACTION_FOR_FAILURE.get(failure, OperatorAction.MANUAL_OPERATOR_VALIDATION)


def recovery_for_failures(failures) -> str:
    """Worst required recovery across concurrent failures.

    Uses `resilience.degrade` per failure and the response precedence the policy
    table already defines, so recovery classification cannot disagree with the
    degradation decision that produced it.
    """
    failures = list(failures)
    if not failures:
        return RecoveryState.NOT_REQUIRED.value
    order = {
        Response.CONTINUE_DEGRADED: 0,
        Response.HALT_NEW_ORDERS: 1,
        Response.RECONCILE_FIRST: 2,
        Response.FAIL_CLOSED: 3,
    }
    resp = max((degrade(f).response for f in failures), key=lambda r: order[r])
    return RECOVERY_FOR_RESPONSE[resp].value


# ── incident convergence ────────────────────────────────────────────────────
#
# One root cause must produce ONE incident. A market-data disconnect that goes on
# to stale the prices, block a strategy on data quality and starve attribution is
# a single failure with three symptoms — not four alerts of equal weight racing
# for the operator's attention. This table says which subsystem's failure is
# allowed to EXPLAIN another's, so a symptom links to its cause rather than
# raising a rival incident.
CAUSAL_PARENTS = {
    # A provider outage is upstream of the market data it feeds, so the two must
    # not both raise primary incidents for one failure.
    Subsystem.MARKET_DATA: (Subsystem.PROVIDER,),
    Subsystem.STRATEGY: (Subsystem.MARKET_DATA, Subsystem.PROVIDER),
    Subsystem.PORTFOLIO: (Subsystem.MARKET_DATA, Subsystem.PROVIDER),
    Subsystem.RISK: (Subsystem.MARKET_DATA, Subsystem.PROVIDER),
    Subsystem.SHADOW: (Subsystem.MARKET_DATA, Subsystem.PROVIDER),
    Subsystem.PAPER: (Subsystem.MARKET_DATA, Subsystem.PROVIDER),
}

#: Health at or above which a subsystem is worth an incident at all.
_INCIDENT_FROM = {
    HealthClass.DEGRADED.value,
    HealthClass.CRITICAL.value,
    HealthClass.FAILED_SAFE.value,
}

#: Strategy states that are DATA failures wearing a strategy's name. Classifying
#: these as strategy degradation would blame a strategy for a feed outage.
DATA_BLOCKED_STRATEGY_STATES = frozenset({"DATA_QUALITY_BLOCKED"})


def _root_cause(subsystem: str, failing) -> str | None:
    """Walk up the causal chain to the subsystem that explains this one.

    Resolving only ONE level would attach a symptom to another symptom, and a
    symptom whose parent is not itself a primary incident disappears from the
    tree entirely — the operator stops seeing a condition that is genuinely
    present. So this climbs until it reaches a failing subsystem that nothing
    else explains, and returns None when this subsystem IS that root.
    """
    seen = {subsystem}
    current = subsystem
    root = None
    while True:
        if not _known(current):
            return root
        parents = CAUSAL_PARENTS.get(_subsystem(current), ())
        nxt = next((p.value for p in parents if p.value in failing and p.value not in seen), None)
        if nxt is None:
            return root
        seen.add(nxt)
        root = nxt
        current = nxt


def _severity_of(health: str) -> str:
    return {
        HealthClass.WARNING.value: "LOW",
        HealthClass.DEGRADED.value: "MEDIUM",
        HealthClass.CRITICAL.value: "HIGH",
        HealthClass.FAILED_SAFE.value: "HIGH",
    }.get(health, "INFO")


def converge_incidents(findings, *, observed_at=None, acknowledged=()):
    """Turn subsystem findings into deduplicated, causally-linked incidents.

    `findings` are dicts: subsystem, health, cause, and optionally scope, summary,
    runbook_ref, affected_capabilities, containment, action.

    Two guarantees:
      * DEDUPLICATION — the same (subsystem, cause, scope) is one incident however
        many times it is observed, because the key excludes observation time.
      * CONVERGENCE — a finding whose subsystem has a failing causal parent becomes
        a SYMPTOM of that parent's incident instead of its own incident.
    """
    findings = [f for f in findings if f.get("health") in _INCIDENT_FROM]
    failing = {f["subsystem"] for f in findings}
    ack = set(acknowledged)

    primaries: dict[str, dict] = {}
    symptoms: list[dict] = []
    for f in findings:
        sub = f["subsystem"]
        parent = _root_cause(sub, failing)
        if parent is not None:
            symptoms.append({**f, "parent": parent})
            continue
        key = dedup_key(sub, f["cause"], f.get("scope", ""))
        # First writer wins on a repeated key: re-observing an unchanged condition
        # must not restate it as a new incident.
        primaries.setdefault(key, f)

    by_subsystem = {f["subsystem"]: k for k, f in primaries.items()}
    out = []
    for key, f in primaries.items():
        sub = f["subsystem"]
        mine = tuple(
            {"subsystem": s["subsystem"], "health": s["health"], "cause": s["cause"]}
            for s in symptoms if s["parent"] == sub
        )
        out.append(OpsIncident(
            incident_id=f"inc_{key}",
            dedup_key=key,
            subsystem=sub,
            severity=_severity_of(f["health"]),
            state="ACKNOWLEDGED" if key in ack else "OPEN",
            opened_at=f.get("opened_at") or observed_at,
            last_updated_at=observed_at,
            summary=f.get("summary") or f["cause"],
            authority=authority_for(sub),
            affected_capabilities=tuple(f.get("affected_capabilities") or ()),
            symptoms=mine,
            containment=f.get("containment"),
            recommended_action=f.get("action"),
            runbook_ref=f.get("runbook_ref"),
            acknowledged=key in ack,
        ))
    # Stable order: worst first, then by subsystem, so the operator's eye lands on
    # the thing that matters rather than on insertion order.
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    out.sort(key=lambda i: (rank.get(i.severity, 9), i.subsystem))
    return tuple(out), tuple(by_subsystem.items())


def build_snapshot(
    *,
    observed_at: str | None,
    mode: str,
    subsystems,
    failures=(),
    kill_switch_state=None,
    reconciliation_state=ReconciliationState.HEALTHY.value,
    acknowledged=(),
    source_versions=None,
    data_quality=None,
) -> TradingOperationsSnapshot:
    """Assemble one snapshot from already-classified subsystem findings.

    NO CLOCK. `observed_at` is supplied by the caller — a polling loop may own a
    clock, but this aggregation must be reproducible from its inputs alone, so the
    same inputs always produce the same snapshot_id.

    Callers pass findings that the OWNING authority classified. This function does
    not decide whether a strategy is degraded or a feed is stale; it decides only
    how those verdicts combine.
    """
    findings = [dict(s) for s in subsystems]

    # A strategy blocked on data quality is a DATA failure. Recording it as
    # strategy degradation would blame the strategy for the feed, which is the
    # single most misleading thing an ops view can do.
    for f in findings:
        if f.get("subsystem") == Subsystem.STRATEGY.value and \
                f.get("state") in DATA_BLOCKED_STRATEGY_STATES:
            f["cause"] = f.get("cause") or "STRATEGY_DATA_QUALITY_BLOCKED"
            f["data_caused"] = True

    incidents, _ = converge_incidents(
        findings, observed_at=observed_at, acknowledged=acknowledged,
    )

    ks = dict(kill_switch_state or {})
    ks_engaged = bool(ks.get("engaged"))

    healths = [f["health"] for f in findings if f.get("health")]
    if ks_engaged:
        # An engaged kill switch is a CONTAINED state, not an uncontrolled one.
        # FAILED_SAFE says exactly that: the system is stopped on purpose.
        healths.append(HealthClass.FAILED_SAFE.value)
    if reconciliation_state in (ReconciliationState.REQUIRED.value,
                               ReconciliationState.FAILED.value,
                               ReconciliationState.BLOCKED.value):
        healths.append(HealthClass.CRITICAL.value)
    overall = worst_health(*healths) if healths else HealthClass.HEALTHY.value

    fails = list(failures)
    if ks_engaged:
        fails.append(FailureMode.KILL_SWITCH)
    recovery = recovery_for_failures(fails)
    if reconciliation_state in (ReconciliationState.REQUIRED.value,
                                ReconciliationState.FAILED.value) and \
            recovery not in (RecoveryState.FAILED_SAFE.value,):
        recovery = RecoveryState.RECONCILIATION_REQUIRED.value

    actions = _actions_for(findings, incidents, fails, reconciliation_state, ks_engaged)

    subsystem_rows = tuple(
        SubsystemHealth(
            subsystem=f["subsystem"],
            health=f.get("health", HealthClass.HEALTHY.value),
            authority=authority_for(f["subsystem"]),
            detail=f.get("summary") or f.get("cause"),
            caused_by=f.get("caused_by"),
        )
        for f in findings
    )

    body = {
        "observed_at": observed_at,
        "mode": mode,
        "overall_health": overall,
        "subsystems": [vars(s) for s in subsystem_rows],
        "incidents": [i.dedup_key for i in incidents],
        "recovery": recovery,
        "reconciliation": reconciliation_state,
        "kill_switch": ks,
    }
    return TradingOperationsSnapshot(
        snapshot_id=snapshot_id(body),
        observed_at=observed_at,
        mode=mode,
        overall_health=overall,
        subsystems=subsystem_rows,
        incidents=incidents,
        kill_switch_state=ks,
        recovery_state=recovery,
        reconciliation_state=reconciliation_state,
        operator_actions_required=actions,
        source_versions=dict(source_versions or {}),
        data_quality=dict(data_quality or {}),
    )


def _actions_for(findings, incidents, failures, reconciliation_state, ks_engaged):
    """One typed action per real need, each naming its owning authority."""
    actions: list[RequiredAction] = []
    seen: set[tuple] = set()

    def add(action, subsystem, detail, incident_id=None, automatable=False):
        key = (action.value, subsystem)
        if key in seen:
            return
        seen.add(key)
        actions.append(RequiredAction(
            action=action.value, subsystem=subsystem,
            authority=authority_for(subsystem),
            detail=detail, incident_id=incident_id, automatable=automatable,
        ))

    if reconciliation_state in (ReconciliationState.REQUIRED.value,
                                ReconciliationState.FAILED.value,
                                ReconciliationState.BLOCKED.value):
        add(OperatorAction.REVIEW_RECONCILIATION, Subsystem.RECONCILIATION.value,
            f"reconciliation is {reconciliation_state}; trading readiness cannot be healthy")

    for f in failures:
        sub = SUBSYSTEM_FOR_FAILURE.get(f, Subsystem.RECONCILIATION).value
        add(action_for_failure(f), sub, f"{f.value}: {degrade(f).detail}")

    for inc in incidents:
        if inc.acknowledged:
            continue
        add(OperatorAction.ACKNOWLEDGE_INCIDENT, inc.subsystem,
            inc.summary, incident_id=inc.incident_id)

    for f in findings:
        if f.get("subsystem") == Subsystem.STRATEGY.value and \
                not f.get("data_caused") and \
                f.get("health") in (HealthClass.DEGRADED.value, HealthClass.CRITICAL.value):
            add(OperatorAction.REVIEW_STRATEGY_DEGRADATION, Subsystem.STRATEGY.value,
                f.get("summary") or "strategy degradation observed")
        if f.get("external_reason") in EXTERNAL_BLOCKERS:
            add(OperatorAction.EXTERNAL_ACTION_REQUIRED, f["subsystem"],
                f"{f['external_reason']}: SaathiOS cannot resolve this itself")
        if f.get("auth_required"):
            add(OperatorAction.REAUTHENTICATE_PROVIDER, f["subsystem"],
                "provider authentication required")

    if ks_engaged:
        add(OperatorAction.MANUAL_OPERATOR_VALIDATION, Subsystem.KILL_SWITCH.value,
            "kill switch engaged; release is an operator decision through its own authority")
    return tuple(actions)


# ── render edge ─────────────────────────────────────────────────────────────
#
# CommandSurface speaks PanelStatus (OK/DEGRADED/BLOCKED/UNKNOWN), a PRESENTATION
# vocabulary that predates this milestone. Rather than fork a third vocabulary or
# rewrite that surface, the mapping is stated once, here, explicitly.
#
# CRITICAL and FAILED_SAFE both render BLOCKED because both mean "do not proceed".
# They stay distinct in `overall_health`, where the difference matters: FAILED_SAFE
# is a system safely contained, CRITICAL is one in unsafe ambiguity. Collapsing
# them for display is acceptable; collapsing them in the record is not.
PANEL_STATUS_FOR_HEALTH = {
    HealthClass.HEALTHY.value: "OK",
    HealthClass.WARNING.value: "DEGRADED",
    HealthClass.DEGRADED.value: "DEGRADED",
    HealthClass.CRITICAL.value: "BLOCKED",
    HealthClass.FAILED_SAFE.value: "BLOCKED",
}


def panel_status_for(health: str) -> str:
    """Render-edge mapping. An unrecognised health is UNKNOWN, never OK."""
    return PANEL_STATUS_FOR_HEALTH.get(health, "UNKNOWN")
