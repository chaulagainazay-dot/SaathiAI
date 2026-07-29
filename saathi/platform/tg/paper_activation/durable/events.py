"""M201 — Append-only paper operations event types and helpers."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from saathi.platform.tg.paper_activation.durable.schema import SCHEMA_VERSION


def _id(prefix: str = "pevt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


# Material event types (canonical)
EVENT_TYPES = frozenset({
    "portfolio.created",
    "strategy.approved",
    "approval.consumed",
    "strategy.activated",
    "order.submitted",
    "order.accepted",
    "order.rejected",
    "order.partially_filled",
    "order.filled",
    "order.cancelled",
    "position.opened",
    "position.increased",
    "position.partially_closed",
    "position.closed",
    "fee.charged",
    "dividend.applied",
    "corporate_action.applied",
    "risk.warning",
    "risk.limit_breached",
    "portfolio.halted",
    "kill_switch.engaged",
    "kill_switch.released",
    "journal.created",
    "reconciliation.started",
    "reconciliation.passed",
    "reconciliation.failed",
    "campaign.started",
    "campaign.paused",
    "campaign.completed",
    "state.recovered",
    "operator.override_attempted",
    "prohibited.live_action_attempted",
    "snapshot.created",
    "backup.created",
    "worker.lease_acquired",
    "worker.lease_released",
    "order.queue_enqueued",
    "campaign.created",
    "campaign.approved",
    "incident.opened",
    "incident.resolved",
})


@dataclass
class PaperEvent:
    event_id: str = field(default_factory=_id)
    event_type: str = ""
    schema_version: str = SCHEMA_VERSION
    aggregate_type: str = ""
    aggregate_id: str = ""
    expected_version: int | None = None
    resulting_version: int | None = None
    ts: float = field(default_factory=time.time)
    actor_type: str = "system"
    actor_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    idempotency_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    payload_fingerprint: str = ""
    previous_event_id: str = ""
    audit: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def __post_init__(self) -> None:
        if not self.payload_fingerprint:
            self.payload_fingerprint = fingerprint(self.payload)
        if self.event_type and self.event_type not in EVENT_TYPES:
            # allow extension with prefix warning in audit
            self.audit = {**self.audit, "unlisted_event_type": True}

    def to_row(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "expected_version": self.expected_version,
            "resulting_version": self.resulting_version,
            "ts": self.ts,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "payload_json": json.dumps(self.payload, sort_keys=True, default=str),
            "payload_fingerprint": self.payload_fingerprint,
            "previous_event_id": self.previous_event_id,
            "audit_json": json.dumps(self.audit, sort_keys=True, default=str),
            "seq": self.seq,
        }

    def to_public(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "expected_version": self.expected_version,
            "resulting_version": self.resulting_version,
            "ts": self.ts,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "payload_fingerprint": self.payload_fingerprint,
            "previous_event_id": self.previous_event_id,
            "audit": self.audit,
            "seq": self.seq,
            "immutable": True,
            "paper_only": True,
        }


def make_event(
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
    actor_type: str = "system",
    actor_id: str = "",
    correlation_id: str = "",
    causation_id: str = "",
    idempotency_key: str = "",
    expected_version: int | None = None,
    resulting_version: int | None = None,
    previous_event_id: str = "",
    audit: dict[str, Any] | None = None,
) -> PaperEvent:
    return PaperEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=dict(payload or {}),
        actor_type=actor_type,
        actor_id=actor_id,
        correlation_id=correlation_id or _id("corr"),
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        resulting_version=resulting_version,
        previous_event_id=previous_event_id,
        audit=dict(audit or {"paper_only": True, "live_authorized": False}),
    )
