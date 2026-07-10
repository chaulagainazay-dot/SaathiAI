"""ToolIntent — Universal contract for every execution request in SaathiOS.

Every connector call, LLM request, workflow trigger, email, or publish action
must be expressed as a ToolIntent. Immutable, auditable, idempotent.

This module defines the schema, validation, serialization, and safe logging.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class ActorType(str, Enum):
    """Who is executing the intent."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    WEBHOOK = "webhook"


class RiskLevel(str, Enum):
    """Risk classification of the action."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalLevel(str, Enum):
    """Approval requirement level."""
    L1 = "L1"  # Automatic (read-only)
    L2 = "L2"  # Automatic or policy-controlled
    L3 = "L3"  # Internal preparation
    L4 = "L4"  # Explicit approval required


class Priority(str, Enum):
    """Execution priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class BusinessUnit(str, Enum):
    """Scope for budgeting, reporting, connector permissions."""
    MR_YETI = "mr-yeti"
    PIELTS = "pielts"
    SURMOUNT = "surmount-travels"
    HCG_CAFETERIA = "hcg-cafeteria"
    HCG_LIVE_SIGNAL = "hcg-live-signal"


_SECRET_PATTERNS = [
    r"api[_-]?key",
    r"secret",
    r"token",
    r"password",
    r"auth",
    r"oauth",
    r"bearer",
]
_SECRET_RE = re.compile("|".join(_SECRET_PATTERNS), re.IGNORECASE)


def _redact_secrets(obj: Any) -> Any:
    """Recursively redact secrets from an object (for safe logging)."""
    if isinstance(obj, dict):
        return {k: "***REDACTED***" if _SECRET_RE.search(str(k)) else _redact_secrets(v)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_secrets(x) for x in obj]
    return obj


def _validate_uuid4(s: str, field_name: str) -> List[str]:
    """Validate UUID v4 format."""
    try:
        u = uuid.UUID(s, version=4)
        if str(u) != s:
            return [f"{field_name}: not UUID v4 format"]
    except (ValueError, TypeError):
        return [f"{field_name}: not a valid UUID"]
    return []


def _validate_idempotency_key(key: str) -> List[str]:
    """Validate idempotency key is 64-char hex (SHA256)."""
    if not isinstance(key, str):
        return ["idempotency_key: must be string"]
    if len(key) != 64:
        return [f"idempotency_key: must be exactly 64 chars, got {len(key)}"]
    try:
        int(key, 16)
    except ValueError:
        return ["idempotency_key: must be hexadecimal"]
    return []


def _canonical_params(params: Dict[str, Any]) -> str:
    """Return canonical (sorted) JSON representation of params."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ToolIntent:
    """Immutable, auditable specification of an execution request."""

    schema_version: str = "1.0"
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_intent_id: Optional[str] = None

    actor_id: str = ""
    actor_type: ActorType = ActorType.USER
    mission_id: str = ""
    project_id: Optional[str] = None
    business_unit: BusinessUnit = BusinessUnit.MR_YETI
    workflow_id: Optional[str] = None
    director_id: Optional[str] = None

    capability: str = ""
    connector_id: str = ""
    operation: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: Optional[str] = None

    reason: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    approval_level: ApprovalLevel = ApprovalLevel.L1

    idempotency_key: str = ""
    priority: Priority = Priority.NORMAL
    timeout: int = 30

    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    expires_at: float = field(default_factory=lambda: (datetime.now() + timedelta(hours=24)).timestamp())

    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        """Return list of validation errors, or empty list if valid."""
        errors: List[str] = []

        # Required string fields
        for fname in ["schema_version", "actor_id", "mission_id", "capability", "connector_id", "operation", "reason"]:
            val = getattr(self, fname)
            if not val or not isinstance(val, str):
                errors.append(f"{fname}: required, non-empty string")

        # UUID fields
        errors.extend(_validate_uuid4(self.intent_id, "intent_id"))
        errors.extend(_validate_uuid4(self.correlation_id, "correlation_id"))
        if self.parent_intent_id:
            errors.extend(_validate_uuid4(self.parent_intent_id, "parent_intent_id"))

        # Enum fields
        try:
            ActorType(self.actor_type)
        except ValueError:
            errors.append(f"actor_type: must be one of {[e.value for e in ActorType]}")
        try:
            RiskLevel(self.risk_level)
        except ValueError:
            errors.append(f"risk_level: must be one of {[e.value for e in RiskLevel]}")
        try:
            ApprovalLevel(self.approval_level)
        except ValueError:
            errors.append(f"approval_level: must be one of {[e.value for e in ApprovalLevel]}")
        try:
            Priority(self.priority)
        except ValueError:
            errors.append(f"priority: must be one of {[e.value for e in Priority]}")
        try:
            BusinessUnit(self.business_unit)
        except ValueError:
            errors.append(f"business_unit: must be one of {[e.value for e in BusinessUnit]}")

        # Idempotency key
        if not self.idempotency_key:
            errors.append("idempotency_key: required")
        else:
            errors.extend(_validate_idempotency_key(self.idempotency_key))

        # Timestamp fields
        now = datetime.now().timestamp()
        if self.created_at > now + 60:  # 60s leeway for clock skew
            errors.append(f"created_at: cannot be in future")
        if self.expires_at < self.created_at:
            errors.append("expires_at: must be >= created_at")
        max_expiry = self.created_at + (365 * 24 * 3600)
        if self.expires_at > max_expiry:
            errors.append("expires_at: max 1 year from created_at")

        # Timeout
        if not isinstance(self.timeout, int) or self.timeout < 1 or self.timeout > 3600:
            errors.append("timeout: must be int 1-3600 seconds")

        # Parameters
        if not isinstance(self.parameters, dict):
            errors.append("parameters: must be dict")
        else:
            # Validate JSON serializability (reject NaN/Infinity)
            try:
                json.dumps(self.parameters, allow_nan=False)
            except (TypeError, ValueError) as e:
                errors.append(f"parameters: contains non-JSON-serializable value ({type(e).__name__})")

        # Metadata
        if not isinstance(self.metadata, dict):
            errors.append("metadata: must be dict")
        else:
            # Validate JSON serializability (reject NaN/Infinity)
            try:
                json.dumps(self.metadata, allow_nan=False)
            except (TypeError, ValueError) as e:
                errors.append(f"metadata: contains non-JSON-serializable value ({type(e).__name__})")

        return errors

    def is_expired(self) -> bool:
        """Check if intent has expired."""
        return datetime.now().timestamp() >= self.expires_at

    def to_dict(self, redact: bool = False) -> Dict[str, Any]:
        """Convert to dict. If redact=True, sanitizes sensitive fields for logging."""
        d = asdict(self)
        # Convert Enum values to strings
        d["actor_type"] = self.actor_type.value
        d["risk_level"] = self.risk_level.value
        d["approval_level"] = self.approval_level.value
        d["priority"] = self.priority.value
        d["business_unit"] = self.business_unit.value

        if redact:
            d["parameters"] = _redact_secrets(d["parameters"])
            d["metadata"] = _redact_secrets(d["metadata"])
        return d

    def to_json(self, redact: bool = False, indent: Optional[int] = None) -> str:
        """Serialize to JSON (deterministic output via sort_keys, reject NaN/Infinity)."""
        return json.dumps(self.to_dict(redact=redact), indent=indent, sort_keys=True, allow_nan=False)

    def safe_repr(self) -> str:
        """Logging-safe representation with secrets redacted."""
        return self.to_json(redact=True, indent=2)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ToolIntent:
        """Construct from dict, converting string enums to types."""
        d = dict(data)
        # Convert string enums to enum types
        if isinstance(d.get("actor_type"), str):
            d["actor_type"] = ActorType(d["actor_type"])
        if isinstance(d.get("risk_level"), str):
            d["risk_level"] = RiskLevel(d["risk_level"])
        if isinstance(d.get("approval_level"), str):
            d["approval_level"] = ApprovalLevel(d["approval_level"])
        if isinstance(d.get("priority"), str):
            d["priority"] = Priority(d["priority"])
        if isinstance(d.get("business_unit"), str):
            d["business_unit"] = BusinessUnit(d["business_unit"])
        return ToolIntent(**d)

    @staticmethod
    def from_json(data: str) -> ToolIntent:
        """Deserialize from JSON."""
        return ToolIntent.from_dict(json.loads(data))

    @staticmethod
    def compute_idempotency_key(params: Dict[str, Any]) -> str:
        """Compute canonical idempotency key for params."""
        canonical = _canonical_params(params)
        return hashlib.sha256(canonical.encode()).hexdigest()


def builder() -> ToolIntentBuilder:
    """Create a new ToolIntent builder."""
    return ToolIntentBuilder()


class ToolIntentBuilder:
    """Fluent builder for ToolIntent."""

    def __init__(self):
        self.data: Dict[str, Any] = {
            "schema_version": "1.0",
            "actor_type": ActorType.USER,
            "business_unit": BusinessUnit.MR_YETI,
            "risk_level": RiskLevel.MEDIUM,
            "approval_level": ApprovalLevel.L1,
            "priority": Priority.NORMAL,
            "timeout": 30,
            "parameters": {},
            "metadata": {},
        }

    def actor(self, actor_id: str, actor_type: ActorType = ActorType.USER) -> ToolIntentBuilder:
        self.data["actor_id"] = actor_id
        self.data["actor_type"] = actor_type
        return self

    def mission(self, mission_id: str) -> ToolIntentBuilder:
        self.data["mission_id"] = mission_id
        return self

    def business_unit(self, unit: BusinessUnit) -> ToolIntentBuilder:
        self.data["business_unit"] = unit
        return self

    def capability(self, capability: str, connector_id: str, operation: str) -> ToolIntentBuilder:
        self.data["capability"] = capability
        self.data["connector_id"] = connector_id
        self.data["operation"] = operation
        return self

    def parameters(self, params: Dict[str, Any]) -> ToolIntentBuilder:
        self.data["parameters"] = params
        return self

    def reason(self, reason: str) -> ToolIntentBuilder:
        self.data["reason"] = reason
        return self

    def risk(self, risk_level: RiskLevel, approval_level: ApprovalLevel) -> ToolIntentBuilder:
        self.data["risk_level"] = risk_level
        self.data["approval_level"] = approval_level
        return self

    def correlation_id(self, cid: str) -> ToolIntentBuilder:
        self.data["correlation_id"] = cid
        return self

    def timeout(self, seconds: int) -> ToolIntentBuilder:
        self.data["timeout"] = seconds
        return self

    def metadata(self, meta: Dict[str, Any]) -> ToolIntentBuilder:
        self.data["metadata"] = meta
        return self

    def build(self) -> ToolIntent:
        """Build and validate."""
        # Auto-compute idempotency_key if not provided
        if not self.data.get("idempotency_key"):
            self.data["idempotency_key"] = ToolIntent.compute_idempotency_key(
                self.data.get("parameters", {})
            )
        intent = ToolIntent(**self.data)
        errors = intent.validate()
        if errors:
            raise ValueError(f"Invalid ToolIntent: {'; '.join(errors)}")
        return intent
