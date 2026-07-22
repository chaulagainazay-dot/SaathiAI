# ToolIntent Schema Specification v1.0

**Date:** 2026-07-10  
**Purpose:** Universal contract for every execution request in SaathiOS  
**Scope:** Phase 3.1 (foundation only; execution gateway deferred to Phase 3.2)

---

## Overview

ToolIntent is the immutable, auditable specification of a single external action request. Every call to execute a connector, make an LLM request, trigger a workflow, send an email, or publish content must be expressed as a ToolIntent.

**ToolIntent is NOT:**
- The execution result (that's ExecutionResult)
- A queue entry (that's ExecutionRecord in the durable queue)
- An approval workflow (that's ApprovalRecord)
- Authorization metadata (that's AuthorizationContext)

**ToolIntent IS:**
- The immutable specification of intent
- The correlation ID for a request through all systems
- The basis for idempotency detection
- The audit trail foundation
- The schema for ExecutionGateway input

---

## Immutability Contract

The following fields are **immutable** once created:
- `schema_version`
- `intent_id`
- `correlation_id`
- `mission_id`
- `project_id`
- `business_unit`
- `actor_id`
- `actor_type`
- `created_at`
- `expires_at`

Mutable fields (for future refinement):
- `parameters` (may be refined by approval workflow)
- `priority` (may be elevated during approval)
- `timeout` (may be extended)
- `metadata` (may accumulate trace data)

**Rationale:** Identity and audit trail cannot change; execution details may be refined by approval workflow.

---

## Field Definitions

### Identity & Correlation

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | str | Yes | "1.0" — enables future schema evolution |
| `intent_id` | str | Yes | UUID v4 — unique intent identifier, immutable |
| `correlation_id` | str | Yes | UUID v4 — same across retries, failures, compensation; bridges logs/events |
| `parent_intent_id` | str | No | UUID v4 — for chained intents (e.g., compensation intent references original) |

### Actor & Scope

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `actor_id` | str | Yes | User ID or agent ID (immutable for audit) |
| `actor_type` | enum | Yes | "user" \| "agent" \| "system" \| "webhook" |
| `mission_id` | str | Yes | Mission the action belongs to (immutable) |
| `project_id` | str | No | Project within mission, if applicable |
| `business_unit` | str | Yes | "mr-yeti" \| "pielts" \| "surmount-travels" \| "hcg-cafeteria" \| "hcg-live-signal" (immutable, for reporting/budgeting) |
| `workflow_id` | str | No | Workflow orchestrating this intent |
| `director_id` | str | No | Director that created the intent |

### Execution Spec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `capability` | str | Yes | "email.send" \| "social.post" \| "video.upload" \| "calendar.create_event" \| etc. |
| `connector_id` | str | Yes | "telegram" \| "youtube" \| "github" \| "n8n" \| etc. |
| `operation` | str | Yes | Specific operation within connector ("send_text", "publish_video", etc.) |
| `parameters` | dict | Yes | Operation-specific params (e.g., `{"to": "...", "message": "..."}`) |
| `expected_outcome` | str | No | Human description of expected result ("Message sent to #general") |

### Risk & Approval

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reason` | str | Yes | Why this action requested (audit trail) |
| `risk_level` | enum | Yes | "low" \| "medium" \| "high" \| "critical" — classified by gateway policy |
| `approval_level` | enum | Yes | "L1" \| "L2" \| "L3" \| "L4" — 1=auto, 2=policy-controlled, 3=internal, 4=explicit |

### Execution Control

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idempotency_key` | str | Yes | Fingerprint for duplicate detection (sha256 of canonical params) |
| `priority` | enum | No | "low" \| "normal" \| "high" \| "urgent" (default: "normal") |
| `timeout` | int | No | Seconds before execution times out (default: 30, max: 3600) |

### Timestamps

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `created_at` | float | Yes | Unix timestamp of intent creation (immutable) |
| `expires_at` | float | Yes | Unix timestamp; intent void after this (immutable) |

### Metadata & Extensibility

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metadata` | dict | No | Arbitrary key-value for future extensions (logged, not executed) |

---

## Serialization

### To JSON

```json
{
  "schema_version": "1.0",
  "intent_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "parent_intent_id": null,
  "actor_id": "user-123",
  "actor_type": "user",
  "mission_id": "mr-yeti-001",
  "project_id": "youtube-upload-001",
  "business_unit": "mr-yeti",
  "workflow_id": null,
  "director_id": "creative-director",
  "capability": "video.upload",
  "connector_id": "youtube",
  "operation": "upload_video",
  "parameters": {
    "title": "Episode 5",
    "description": "..."
  },
  "expected_outcome": "Video published to Mr Yeti channel",
  "reason": "Daily content release per schedule",
  "risk_level": "high",
  "approval_level": "L4",
  "idempotency_key": "sha256...",
  "priority": "normal",
  "timeout": 120,
  "created_at": 1720617600.123,
  "expires_at": 1720617600.123,
  "metadata": {}
}
```

### Safe Logging

When logged, parameters are sanitized:
```json
{
  ...
  "parameters": {
    "title": "Episode 5",
    "description": "...",
    "api_key": "***REDACTED***",
    "oauth_token": "***REDACTED***"
  },
  ...
}
```

---

## Validation Rules

### Required Fields
All marked "Required: Yes" must be present and non-null.

### Enum Constraints
- `actor_type`: one of {"user", "agent", "system", "webhook"}
- `risk_level`: one of {"low", "medium", "high", "critical"}
- `approval_level`: one of {"L1", "L2", "L3", "L4"}
- `priority`: one of {"low", "normal", "high", "urgent"}
- `business_unit`: one of {"mr-yeti", "pielts", "surmount-travels", "hcg-cafeteria", "hcg-live-signal"}

### UUID Constraints
- `intent_id`, `correlation_id`, `parent_intent_id` must be valid UUID v4

### Timestamp Constraints
- `created_at` must be <= current Unix time
- `expires_at` must be >= `created_at` and <= `created_at + 86400*365` (1 year max)

### Idempotency Key Constraint
- `idempotency_key` must be exactly 64 hex chars (SHA256 hash)
- Canonical form: `sha256(json.dumps(canonical_params, sort_keys=True))`

### Parameter Validation
- `parameters` must be a dict
- No required subfields (provider-specific validation deferred to adapter)
- May contain secrets (will be redacted in logs)

---

## Type Safety (Python)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import hashlib
import json

class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    WEBHOOK = "webhook"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ApprovalLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"

class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class BusinessUnit(str, Enum):
    MR_YETI = "mr-yeti"
    PIELTS = "pielts"
    SURMOUNT = "surmount-travels"
    HCG_CAFETERIA = "hcg-cafeteria"
    HCG_LIVE_SIGNAL = "hcg-live-signal"

@dataclass(frozen=True)  # Immutable
class ToolIntent:
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
        """Return list of validation errors, or empty if valid."""
        errors = []
        # Checks...
        return errors

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict (sanitized for logging)."""
        return {...}

    @staticmethod
    def from_json(data: str) -> ToolIntent:
        """Deserialize from JSON."""
        return ToolIntent(**json.loads(data))

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ToolIntent:
        """Construct from dict."""
        return ToolIntent(**data)

    def safe_repr(self) -> str:
        """Logging-safe representation (redacts secrets)."""
        d = self.to_dict()
        if "parameters" in d:
            d["parameters"] = redact_secrets(d["parameters"])
        return json.dumps(d, indent=2)
```

---

## Forward Compatibility

To support future schema evolution:

1. **Version field** — `schema_version` allows schema changes without breaking consumers
2. **Extensible metadata** — arbitrary key-value for future fields
3. **Enum extensibility** — consumers should accept unknown enum values (log warning, proceed)
4. **Optional fields** — new fields should default to None/omitted

Future schema versions (2.0, etc.) will maintain backward compat for v1.0 intents.

---

## Backward Compatibility

v1.0 intents must remain valid forever. If a field is deprecated, mark it deprecated in docs but continue accepting it.

---

## Examples

### Low-Risk Read (L1 Auto)

```json
{
  "schema_version": "1.0",
  "intent_id": "...",
  "correlation_id": "...",
  "actor_id": "user-1",
  "actor_type": "user",
  "mission_id": "mr-yeti",
  "business_unit": "mr-yeti",
  "capability": "social.analytics",
  "connector_id": "youtube",
  "operation": "get_channel_stats",
  "parameters": {"channel": "@mryeti"},
  "reason": "Daily metrics check",
  "risk_level": "low",
  "approval_level": "L1",
  "idempotency_key": "...",
  "created_at": 1720617600.0,
  "expires_at": 1720617600.0
}
```

### High-Risk External Publish (L4 Approval)

```json
{
  "schema_version": "1.0",
  "intent_id": "...",
  "correlation_id": "...",
  "actor_id": "director-creative",
  "actor_type": "agent",
  "mission_id": "mr-yeti",
  "business_unit": "mr-yeti",
  "capability": "video.upload",
  "connector_id": "youtube",
  "operation": "upload_video",
  "parameters": {
    "title": "Episode 5: Past Continuous",
    "description": "Teaching past continuous...",
    "playlist": "mr-yeti-playlist"
  },
  "expected_outcome": "Video published to Mr Yeti YouTube channel",
  "reason": "Content release per editorial schedule",
  "risk_level": "high",
  "approval_level": "L4",
  "idempotency_key": "...",
  "timeout": 600,
  "created_at": 1720617600.0,
  "expires_at": 1720617600.0
}
```

### Critical Payment (L4 Explicit Approval)

```json
{
  "schema_version": "1.0",
  "intent_id": "...",
  "correlation_id": "...",
  "actor_id": "trading-agent",
  "actor_type": "agent",
  "mission_id": "surmount-trades",
  "business_unit": "surmount-travels",
  "capability": "payments.charge",
  "connector_id": "stripe",
  "operation": "create_payment",
  "parameters": {
    "amount": 5000000,  // $50,000
    "currency": "usd",
    "customer": "acme-corp"
  },
  "expected_outcome": "Payment processed, receipt issued",
  "reason": "Invoice #INV-2026-001 payment",
  "risk_level": "critical",
  "approval_level": "L4",
  "idempotency_key": "...",
  "timeout": 120,
  "created_at": 1720617600.0,
  "expires_at": 1720617600.0
}
```

---

## Next Steps (Phase 3.2+)

This schema is **complete for Phase 3.1**. Phase 3.2 will build the ExecutionGateway that consumes ToolIntent and orchestrates: validation → authorization → approval → execution → sanitization → events.

Subsequent phases will add:
- ExecutionResult schema
- ExecutionRecord (queue entry)
- AuthorizationContext
- ApprovalRecord
- CompensationIntent

---

**Spec version:** 1.0  
**Status:** Complete for Phase 3.1  
**Ready for implementation:** Yes
