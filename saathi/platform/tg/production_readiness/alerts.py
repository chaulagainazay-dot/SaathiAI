"""M331 offline alert framework.

Three severities, three destinations, all local. Delivery is a write to the control
centre feed, the local structured log, and the governance audit history. There is no
transport that can leave the machine, and no alert can trigger an action.
"""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any, Mapping

from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
)
from saathi.platform.tg.production_readiness.models import (
    ALERT_SEVERITY_RANK,
    BOUNDARY_VALUES,
    FORBIDDEN_ALERT_DESTINATIONS,
    SCHEMA_VERSION,
    Alert,
    AlertDestination,
    AlertSeverity,
    AlertState,
    DeterministicClock,
    LogLevel,
    digest,
    redact,
    short_digest,
)
from saathi.platform.tg.production_readiness.observability import ObservabilityEngine

MAX_ALERTS = 500

ALLOWED_DESTINATIONS = (
    AlertDestination.CONTROL_CENTER,
    AlertDestination.LOCAL_LOG,
    AlertDestination.AUDIT_HISTORY,
)

SEVERITY_LOG_LEVEL = {
    AlertSeverity.INFORMATIONAL: LogLevel.INFO,
    AlertSeverity.WARNING: LogLevel.WARN,
    AlertSeverity.CRITICAL: LogLevel.ERROR,
}

# Legal state transitions. Resolved alerts are terminal: an alert is never reopened,
# a fresh occurrence raises a new record so history stays append-only.
ALLOWED_TRANSITIONS = {
    AlertState.OPEN: (AlertState.ACKNOWLEDGED, AlertState.RESOLVED),
    AlertState.ACKNOWLEDGED: (AlertState.RESOLVED,),
    AlertState.RESOLVED: (),
}


class AlertEngine:
    def __init__(
        self,
        observability: ObservabilityEngine,
        audit_sink: Any | None = None,
        clock: DeterministicClock | None = None,
    ):
        self.observability = observability
        self.audit_sink = audit_sink
        self.clock = clock or observability.clock
        self._lock = RLock()
        self._alerts: dict[str, Alert] = {}
        self._order: deque[str] = deque(maxlen=MAX_ALERTS)
        self._deliveries: list[dict[str, Any]] = []
        self._sequence = 0

    # ── raising ─────────────────────────────────────────────────────────────
    def raise_alert(
        self,
        severity: AlertSeverity | str,
        source: str,
        title: str,
        *,
        detail: Mapping[str, Any] | None = None,
        destinations: tuple[AlertDestination, ...] | None = None,
    ) -> dict[str, Any]:
        severity = (
            severity if isinstance(severity, AlertSeverity) else AlertSeverity(severity)
        )
        if not source or not title:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Alert requires a source and a title",
            )
        destinations = destinations or ALLOWED_DESTINATIONS
        for destination in destinations:
            value = destination.value if isinstance(destination, AlertDestination) else str(destination)
            if value in FORBIDDEN_ALERT_DESTINATIONS:
                raise OperationsError(
                    OperationsErrorCode.FORBIDDEN_DESTINATION,
                    "Alert destination is forbidden offline",
                    details={"destination": value},
                )
            if value not in {item.value for item in ALLOWED_DESTINATIONS}:
                raise OperationsError(
                    OperationsErrorCode.FORBIDDEN_DESTINATION,
                    "Alert destination is not on the offline allowlist",
                    details={"destination": value},
                )

        with self._lock:
            self._sequence += 1
            raised_at = self.clock.advance()
            alert_id = "alert_" + short_digest({
                "severity": severity.value,
                "source": source,
                "title": title,
                "sequence": self._sequence,
            }, 14)
            trace = self.observability.start_trace(
                "operations.alert", "alerts", correlation_key=alert_id,
            )
            alert = Alert(
                alert_id=alert_id,
                severity=severity,
                state=AlertState.OPEN,
                source=source,
                title=title,
                detail=redact(detail),
                destinations=tuple(destinations),
                trace_id=trace.trace_id,
                raised_at=raised_at,
                updated_at=raised_at,
            )
            self._alerts[alert_id] = alert
            self._order.append(alert_id)

        self._deliver(alert, trace)
        return {"ok": True, "alert": alert.to_dict(), **BOUNDARY_VALUES}

    def _deliver(self, alert: Alert, trace: Any) -> None:
        delivered: list[str] = []
        for destination in alert.destinations:
            if destination is AlertDestination.LOCAL_LOG:
                self.observability.log(
                    SEVERITY_LOG_LEVEL[alert.severity],
                    f"alert:{alert.title}",
                    trace=trace,
                    fields={
                        "alert_id": alert.alert_id,
                        "severity": alert.severity.value,
                        "source": alert.source,
                    },
                )
            elif destination is AlertDestination.AUDIT_HISTORY and self.audit_sink is not None:
                self.audit_sink.audit(
                    "operations_alert_raised",
                    "operations",
                    alert.source,
                    {
                        "alert_id": alert.alert_id,
                        "severity": alert.severity.value,
                        "title": alert.title,
                        "external_delivery": False,
                    },
                )
            delivered.append(destination.value)
        with self._lock:
            self._deliveries.append({
                "alert_id": alert.alert_id,
                "destinations": delivered,
                "delivered_at": alert.raised_at,
                "network_used": False,
                "email_sent": False,
                "sms_sent": False,
                "push_sent": False,
            })

    # ── lifecycle ───────────────────────────────────────────────────────────
    def _transition(self, alert_id: str, target: AlertState, actor: str) -> dict[str, Any]:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                raise OperationsError(
                    OperationsErrorCode.ALERT_UNKNOWN,
                    "Unknown alert",
                    details={"alert_id": alert_id},
                )
            if target not in ALLOWED_TRANSITIONS[alert.state]:
                raise OperationsError(
                    OperationsErrorCode.ALERT_TRANSITION_INVALID,
                    "Alert state transition is not permitted",
                    details={
                        "alert_id": alert_id,
                        "from": alert.state.value,
                        "to": target.value,
                    },
                )
            updated = Alert(
                alert_id=alert.alert_id,
                severity=alert.severity,
                state=target,
                source=alert.source,
                title=alert.title,
                detail={**alert.detail, "last_actor": actor},
                destinations=alert.destinations,
                trace_id=alert.trace_id,
                raised_at=alert.raised_at,
                updated_at=self.clock.advance(),
            )
            self._alerts[alert_id] = updated
        if self.audit_sink is not None:
            self.audit_sink.audit(
                "operations_alert_transition",
                actor,
                alert_id,
                {"from": alert.state.value, "to": target.value},
            )
        return {"ok": True, "alert": updated.to_dict(), **BOUNDARY_VALUES}

    def acknowledge(self, alert_id: str, actor: str = "operator") -> dict[str, Any]:
        return self._transition(alert_id, AlertState.ACKNOWLEDGED, actor)

    def resolve(self, alert_id: str, actor: str = "operator") -> dict[str, Any]:
        return self._transition(alert_id, AlertState.RESOLVED, actor)

    # ── reads ───────────────────────────────────────────────────────────────
    def get(self, alert_id: str) -> dict[str, Any]:
        with self._lock:
            alert = self._alerts.get(alert_id)
        if alert is None:
            raise OperationsError(
                OperationsErrorCode.ALERT_UNKNOWN,
                "Unknown alert",
                details={"alert_id": alert_id},
            )
        return {"ok": True, "alert": alert.to_dict(), **BOUNDARY_VALUES}

    def list_alerts(
        self,
        *,
        severity: AlertSeverity | str | None = None,
        state: AlertState | str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        with self._lock:
            alerts = [self._alerts[aid] for aid in self._order if aid in self._alerts]
        if severity is not None:
            wanted = severity if isinstance(severity, AlertSeverity) else AlertSeverity(severity)
            alerts = [alert for alert in alerts if alert.severity is wanted]
        if state is not None:
            wanted_state = state if isinstance(state, AlertState) else AlertState(state)
            alerts = [alert for alert in alerts if alert.state is wanted_state]
        alerts = alerts[-int(limit):]
        counts = {item.value: 0 for item in AlertSeverity}
        states = {item.value: 0 for item in AlertState}
        for alert in alerts:
            counts[alert.severity.value] += 1
            states[alert.state.value] += 1
        return {
            "ok": True,
            "count": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
            "by_severity": counts,
            "by_state": states,
            "open_critical": sum(
                1 for alert in alerts
                if alert.severity is AlertSeverity.CRITICAL and alert.state is AlertState.OPEN
            ),
            "severity_ranking": {
                item.value: rank for item, rank in ALERT_SEVERITY_RANK.items()
            },
            **BOUNDARY_VALUES,
        }

    def deliveries(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._deliveries)
        return {
            "ok": True,
            "count": len(rows),
            "deliveries": rows,
            "allowed_destinations": [item.value for item in ALLOWED_DESTINATIONS],
            "forbidden_destinations": sorted(FORBIDDEN_ALERT_DESTINATIONS),
            "external_deliveries": 0,
            "network_deliveries": 0,
            **BOUNDARY_VALUES,
        }

    def destination_policy(self) -> dict[str, Any]:
        return {
            "ok": True,
            "milestone": "M331",
            "schema_version": SCHEMA_VERSION,
            "severities": [item.value for item in AlertSeverity],
            "states": [item.value for item in AlertState],
            "allowed_destinations": [item.value for item in ALLOWED_DESTINATIONS],
            "forbidden_destinations": sorted(FORBIDDEN_ALERT_DESTINATIONS),
            "transitions": {
                state.value: [target.value for target in targets]
                for state, targets in ALLOWED_TRANSITIONS.items()
            },
            "alerts_trigger_actions": False,
            "alerts_grant_authority": False,
            **BOUNDARY_VALUES,
        }

    def isolation_scan(self) -> dict[str, Any]:
        """Prove every delivery stayed local and no forbidden destination was used."""
        with self._lock:
            deliveries = list(self._deliveries)
            alerts = list(self._alerts.values())
        findings: list[dict[str, Any]] = []
        allowed = {item.value for item in ALLOWED_DESTINATIONS}
        for delivery in deliveries:
            for destination in delivery["destinations"]:
                if destination not in allowed:
                    findings.append({"alert_id": delivery["alert_id"], "destination": destination})
            if delivery["email_sent"] or delivery["sms_sent"] or delivery["push_sent"]:
                findings.append({"alert_id": delivery["alert_id"], "external_delivery": True})
        return {
            "ok": not findings,
            "findings": findings,
            "alerts_scanned": len(alerts),
            "deliveries_scanned": len(deliveries),
            "email_transport_present": False,
            "sms_transport_present": False,
            "push_transport_present": False,
            "webhook_transport_present": False,
            "fingerprint": digest([alert.to_dict() for alert in alerts]),
        }


def evaluate_health_alerts(
    engine: AlertEngine,
    health_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Raise one advisory alert per non-healthy component. Raising changes nothing."""
    from saathi.platform.tg.production_readiness.health import health_to_alert_severity

    raised: list[dict[str, Any]] = []
    for domain in health_snapshot.get("domains", []):
        for component in domain.get("components", []):
            severity = health_to_alert_severity(component["state"])
            if severity is None:
                continue
            raised.append(engine.raise_alert(
                severity,
                component["component_id"],
                f"{component['component_id']} reported {component['state']}",
                detail={
                    "domain": component["domain"],
                    "reason": component["reason"],
                    "state": component["state"],
                },
            )["alert"])
    return {
        "ok": True,
        "raised_count": len(raised),
        "alerts": raised,
        "remediation_triggered": False,
        **BOUNDARY_VALUES,
    }
