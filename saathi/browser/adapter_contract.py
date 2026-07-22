"""M17.26 — Canonical browser adapter contract, health model, and typed errors.

Adapters execute already-validated governed action requests. They must NOT decide
authorization, policy, approval, Trading Guardian, domain allow, or retry policy.
They may enforce defensive checks and must fail closed if required context is absent.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AdapterHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    CLOSED = "CLOSED"


class AdapterErrorCode(str, Enum):
    ATTACH_FAILED = "ATTACH_FAILED"
    SESSION_REQUIRED = "SESSION_REQUIRED"
    OWNERSHIP_MISMATCH = "OWNERSHIP_MISMATCH"
    LEASE_INVALID = "LEASE_INVALID"
    PAGE_UNKNOWN = "PAGE_UNKNOWN"
    PAGE_MISMATCH = "PAGE_MISMATCH"
    DOMAIN_RECHECK_FAILED = "DOMAIN_RECHECK_FAILED"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    TARGET_NOT_INTERACTABLE = "TARGET_NOT_INTERACTABLE"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    DISCONNECTED = "DISCONNECTED"
    RECONNECT_FAILED = "RECONNECT_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    KILL_SWITCH = "KILL_SWITCH"
    CANCELLED = "CANCELLED"
    HEALTH_DEGRADED_BLOCK = "HEALTH_DEGRADED_BLOCK"
    HUMAN_CONCURRENT = "HUMAN_CONCURRENT"
    CONTEXT_MISSING = "CONTEXT_MISSING"
    CLOSED = "CLOSED"
    UNCERTAIN_OUTCOME = "UNCERTAIN_OUTCOME"
    RAW_FALLBACK_DENIED = "RAW_FALLBACK_DENIED"


class AdapterError(RuntimeError):
    def __init__(
        self,
        code: str | AdapterErrorCode,
        message: str,
        *,
        details: Optional[dict] = None,
        retryable: bool = False,
        reconciliation: bool = False,
    ):
        self.code = code.value if isinstance(code, AdapterErrorCode) else str(code)
        self.message = message
        self.details = dict(details or {})
        self.retryable = retryable
        self.reconciliation = reconciliation
        super().__init__(f"{self.code}: {message}")

    def as_dict(self) -> dict:
        return {
            "error": "browser_adapter",
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
            "reconciliation": self.reconciliation,
        }


@dataclass
class AdapterHealth:
    state: AdapterHealthState = AdapterHealthState.UNKNOWN
    adapter_id: str = ""
    adapter_type: str = ""  # cdp | playwright | human_mac | fake | service
    session_id: str = ""
    adapter_available: bool = False
    process_alive: bool = False
    cdp_connection_alive: bool = False
    browser_context_alive: bool = False
    active_page_available: bool = False
    session_lease_valid: bool = False
    last_heartbeat: float = 0.0
    last_successful_action: float = 0.0
    last_error_category: str = ""
    disconnect_count: int = 0
    reconnect_count: int = 0
    reconciliation_required: bool = False
    kill_switch_active: bool = False
    supported_capabilities: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "state": self.state.value if isinstance(self.state, AdapterHealthState) else self.state,
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "session_id": self.session_id,
            "adapter_available": self.adapter_available,
            "process_alive": self.process_alive,
            "cdp_connection_alive": self.cdp_connection_alive,
            "browser_context_alive": self.browser_context_alive,
            "active_page_available": self.active_page_available,
            "session_lease_valid": self.session_lease_valid,
            "last_heartbeat": self.last_heartbeat,
            "last_successful_action": self.last_successful_action,
            "last_error_category": self.last_error_category,
            "disconnect_count": self.disconnect_count,
            "reconnect_count": self.reconnect_count,
            "reconciliation_required": self.reconciliation_required,
            "kill_switch_active": self.kill_switch_active,
            "supported_capabilities": list(self.supported_capabilities),
            "details": dict(self.details),
        }

    def allows_high_risk(self) -> bool:
        """DEGRADED and worse must not silently execute high-risk actions."""
        return self.state == AdapterHealthState.HEALTHY and not self.kill_switch_active


@dataclass
class GovernedActionRequest:
    """Fully validated governed action — adapters receive this, not raw agent intent."""
    session_id: str
    action_id: str
    action_type: str
    action_class: str
    actor_id: str
    mission_id: str = ""
    mission_run_id: str = ""
    url: str = ""
    selector: str = ""
    target_digest: str = ""
    page_id: str = ""
    page_fingerprint: str = ""
    expected_effect: str = ""
    expected_page_state: str = ""
    approval_id: str = ""
    idempotency_key: str = ""
    payload: dict = field(default_factory=dict)
    text_redacted: bool = True
    timeout_sec: float = 30.0
    lease_owner: str = ""
    kill_switch_checked: bool = False
    domain_validated: bool = False
    policy_validated: bool = False
    trading_authorized: bool = False

    def require_context(self) -> None:
        if not self.session_id:
            raise AdapterError(AdapterErrorCode.SESSION_REQUIRED, "session_id required")
        if not self.action_id:
            raise AdapterError(AdapterErrorCode.CONTEXT_MISSING, "action_id required")
        if not self.actor_id:
            raise AdapterError(AdapterErrorCode.CONTEXT_MISSING, "actor_id required")
        if not self.domain_validated and self.url:
            raise AdapterError(
                AdapterErrorCode.CONTEXT_MISSING,
                "domain must be validated above adapter boundary",
            )
        if not self.policy_validated:
            raise AdapterError(
                AdapterErrorCode.CONTEXT_MISSING,
                "policy must be validated above adapter boundary",
            )


@dataclass
class AdapterActionResult:
    status: str  # succeeded | failed | denied | uncertain
    action_id: str = ""
    action_type: str = ""
    summary: str = ""
    error_category: str = ""
    final_url: str = ""
    final_origin: str = ""
    page_id: str = ""
    page_fingerprint: str = ""
    page_title: str = ""
    retryable: bool = False
    reconciliation_required: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    duration_sec: float = 0.0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "summary": self.summary,
            "error_category": self.error_category,
            "final_url": self.final_url,
            "final_origin": self.final_origin,
            "page_id": self.page_id,
            "page_fingerprint": self.page_fingerprint,
            "page_title": self.page_title,
            "retryable": self.retryable,
            "reconciliation_required": self.reconciliation_required,
            "evidence_refs": list(self.evidence_refs),
            "details": dict(self.details),
            "duration_sec": self.duration_sec,
        }


# High-risk action classes that DEGRADED health must not execute
HIGH_RISK_ACTION_CLASSES = frozenset({
    "sensitive_input", "external_effect", "financial",
})

# Interactive external-effect actions that must not blindly retry after reconnect
NO_BLIND_RETRY_ACTIONS = frozenset({
    "submit", "send_message", "publish", "create_account", "book", "confirm",
    "accept_terms", "purchase", "checkout", "payment", "trade", "withdrawal",
    "delete_external", "money_transfer", "upload", "download",
})


class BrowserSessionAdapter(ABC):
    """Canonical production adapter interface (extend, do not replace)."""

    adapter_id: str = "base"
    adapter_type: str = "base"

    @abstractmethod
    def attach_session(self, session_id: str, *, endpoint: str = "", metadata: dict | None = None) -> AdapterHealth:
        ...

    @abstractmethod
    def validate_session(self, session_id: str, *, actor_id: str = "", lease_owner: str = "") -> bool:
        ...

    @abstractmethod
    def health(self, session_id: str = "") -> AdapterHealth:
        ...

    @abstractmethod
    def navigate(self, request: GovernedActionRequest) -> AdapterActionResult:
        ...

    @abstractmethod
    def inspect(self, request: GovernedActionRequest) -> AdapterActionResult:
        ...

    @abstractmethod
    def act(self, request: GovernedActionRequest) -> AdapterActionResult:
        ...

    @abstractmethod
    def capture_evidence(self, request: GovernedActionRequest, *, kind: str = "screenshot") -> AdapterActionResult:
        ...

    @abstractmethod
    def pause(self, session_id: str, *, reason: str = "") -> AdapterHealth:
        ...

    @abstractmethod
    def resume(self, session_id: str, *, checkpoint: dict | None = None) -> AdapterHealth:
        ...

    @abstractmethod
    def reconcile(self, session_id: str, *, action_id: str = "") -> AdapterActionResult:
        ...

    @abstractmethod
    def close_session(self, session_id: str, *, detach_only: bool = True) -> AdapterHealth:
        ...


def heartbeat(health: AdapterHealth) -> AdapterHealth:
    health.last_heartbeat = time.time()
    return health
