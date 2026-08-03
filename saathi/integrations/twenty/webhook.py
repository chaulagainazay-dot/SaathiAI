"""Twenty webhook verification and normalization; never executes actions."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import TwentyScope


@dataclass(frozen=True)
class WebhookOutcome:
    accepted: bool
    reason: str
    observation: dict[str, Any] | None = None
    execution_requested: bool = False


class TwentyWebhookVerifier:
    def __init__(
        self,
        *,
        secret_resolver: Callable[[str], str | None],
        allowed_events: set[str] | frozenset[str],
        audit_sink: Callable[[str, dict[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.time,
        max_age_seconds: int = 300,
        max_payload_bytes: int = 262_144,
    ) -> None:
        self.secret_resolver = secret_resolver
        self.allowed_events = frozenset(allowed_events)
        self.audit_sink = audit_sink
        self.clock = clock
        self.max_age_seconds = max_age_seconds
        self.max_payload_bytes = max_payload_bytes
        self._seen: set[tuple[str, str, str]] = set()

    def _audit(self, event: str, detail: dict[str, Any]) -> None:
        if self.audit_sink:
            self.audit_sink(event, {k: v for k, v in detail.items() if k not in {"secret", "signature", "raw_body"}})

    def verify(
        self,
        *,
        scope: TwentyScope,
        credential_reference: str,
        raw_body: bytes,
        signature: str,
        timestamp: str,
        event_id: str,
    ) -> WebhookOutcome:
        scope.validate()
        base = {"org_id": scope.org_id, "workspace_id": scope.workspace_id, "event_id": event_id}
        if not credential_reference:
            return self._reject("credential_reference_required", base)
        if len(raw_body) > self.max_payload_bytes:
            return self._reject("payload_too_large", base)
        try:
            event_ts = float(timestamp)
        except (TypeError, ValueError):
            return self._reject("invalid_timestamp", base)
        # Twenty emits Date.now() (milliseconds). Accept seconds only for
        # compatibility with older fixtures, then compare on one time scale.
        event_ts_seconds = event_ts / 1000.0 if event_ts >= 100_000_000_000 else event_ts
        if abs(self.clock() - event_ts_seconds) > self.max_age_seconds:
            return self._reject("stale_timestamp", base)
        secret = self.secret_resolver(credential_reference)
        if not secret:
            return self._reject("credential_reference_unresolved", base)
        expected = hmac.new(secret.encode(), timestamp.encode() + b":" + raw_body, hashlib.sha256).hexdigest()
        supplied = signature.split("=", 1)[-1]
        if not hmac.compare_digest(expected, supplied):
            return self._reject("invalid_signature", base)
        replay_key = (scope.org_id, scope.workspace_id, event_id)
        if not event_id or replay_key in self._seen:
            return self._reject("duplicate_or_replayed_event", base)
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._reject("malformed_payload", base)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return self._reject("malformed_payload", base)
        event = str(payload.get("event") or "")
        if event not in self.allowed_events:
            return self._reject("unsupported_event_type", {**base, "event": event})
        self._seen.add(replay_key)
        observation = {
            "kind": "CRM_OBSERVATION",
            "provider": "twenty",
            "event": event,
            "event_id": event_id,
            "org_id": scope.org_id,
            "workspace_id": scope.workspace_id,
            "data": payload["data"],
            "direct_execution": False,
            "mission_state": "PROPOSAL_ONLY",
        }
        self._audit("twenty.webhook.observation", {**base, "event": event, "outcome": "accepted_no_execution"})
        return WebhookOutcome(True, "accepted_as_observation", observation, False)

    def _reject(self, reason: str, detail: dict[str, Any]) -> WebhookOutcome:
        self._audit("twenty.webhook.rejected", {**detail, "reason": reason})
        return WebhookOutcome(False, reason, None, False)
