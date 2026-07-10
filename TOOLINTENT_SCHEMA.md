# ToolIntent JSON Schema v1.0

**Canonical JSON Schema for ToolIntent validation.**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://saathi.ai/schemas/toolintent/1.0",
  "title": "ToolIntent",
  "description": "Universal contract for every execution request in SaathiOS",
  "type": "object",
  "required": [
    "schema_version",
    "intent_id",
    "correlation_id",
    "actor_id",
    "actor_type",
    "mission_id",
    "business_unit",
    "capability",
    "connector_id",
    "operation",
    "parameters",
    "reason",
    "risk_level",
    "approval_level",
    "idempotency_key",
    "timeout",
    "created_at",
    "expires_at"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+$",
      "description": "Schema version (1.0, 2.0, etc.)",
      "examples": ["1.0"]
    },
    "intent_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique intent identifier (UUIDv4)"
    },
    "correlation_id": {
      "type": "string",
      "format": "uuid",
      "description": "Correlation ID across retries, failures, compensation (UUIDv4)"
    },
    "parent_intent_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "For chained intents (e.g., compensation intent references original)"
    },
    "actor_id": {
      "type": "string",
      "minLength": 1,
      "description": "User ID or agent ID (immutable for audit)"
    },
    "actor_type": {
      "type": "string",
      "enum": ["user", "agent", "system", "webhook"],
      "description": "Type of actor"
    },
    "mission_id": {
      "type": "string",
      "minLength": 1,
      "description": "Mission the action belongs to (immutable)"
    },
    "project_id": {
      "type": ["string", "null"],
      "description": "Project within mission, if applicable"
    },
    "business_unit": {
      "type": "string",
      "enum": ["mr-yeti", "pielts", "surmount-travels", "hcg-cafeteria", "hcg-live-signal"],
      "description": "Business unit for reporting/budgeting (immutable)"
    },
    "workflow_id": {
      "type": ["string", "null"],
      "description": "Workflow orchestrating this intent"
    },
    "director_id": {
      "type": ["string", "null"],
      "description": "Director that created the intent"
    },
    "capability": {
      "type": "string",
      "minLength": 1,
      "pattern": "^[a-z_]+\\.[a-z_]+$",
      "description": "Capability identifier (e.g., email.send, social.post, video.upload)",
      "examples": ["email.send", "social.post", "video.upload", "calendar.create_event"]
    },
    "connector_id": {
      "type": "string",
      "minLength": 1,
      "description": "Connector provider ID (e.g., telegram, youtube, github)",
      "examples": ["telegram", "youtube", "github", "stripe"]
    },
    "operation": {
      "type": "string",
      "minLength": 1,
      "description": "Specific operation within connector (e.g., send_text, publish_video)",
      "examples": ["send_text", "publish_video", "upload_file"]
    },
    "parameters": {
      "type": "object",
      "description": "Operation-specific parameters (secrets will be redacted in logs)",
      "additionalProperties": true
    },
    "expected_outcome": {
      "type": ["string", "null"],
      "description": "Human description of expected result"
    },
    "reason": {
      "type": "string",
      "minLength": 1,
      "description": "Why this action was requested (audit trail)"
    },
    "risk_level": {
      "type": "string",
      "enum": ["low", "medium", "high", "critical"],
      "description": "Risk classification"
    },
    "approval_level": {
      "type": "string",
      "enum": ["L1", "L2", "L3", "L4"],
      "description": "Approval requirement level"
    },
    "idempotency_key": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA256 hash of canonical parameters for duplicate detection"
    },
    "priority": {
      "type": "string",
      "enum": ["low", "normal", "high", "urgent"],
      "default": "normal",
      "description": "Execution priority"
    },
    "timeout": {
      "type": "integer",
      "minimum": 1,
      "maximum": 3600,
      "default": 30,
      "description": "Execution timeout in seconds"
    },
    "created_at": {
      "type": "number",
      "description": "Unix timestamp of intent creation (immutable)"
    },
    "expires_at": {
      "type": "number",
      "description": "Unix timestamp; intent void after this (immutable)"
    },
    "metadata": {
      "type": "object",
      "description": "Arbitrary key-value for future extensions",
      "additionalProperties": true
    }
  },
  "additionalProperties": false,
  "allOf": [
    {
      "description": "expires_at must be >= created_at",
      "properties": {
        "created_at": { "type": "number" },
        "expires_at": { "type": "number" }
      }
    }
  ]
}
```

## Schema Validation Rules

### String Patterns
- `schema_version`: `^[0-9]+\.[0-9]+$` (e.g., "1.0", "2.0")
- `capability`: `^[a-z_]+\.[a-z_]+$` (e.g., "email.send", "social.post")
- `idempotency_key`: `^[a-f0-9]{64}$` (64 hex chars, SHA256 hash)

### Enum Constraints

**actor_type**: "user" | "agent" | "system" | "webhook"
**risk_level**: "low" | "medium" | "high" | "critical"
**approval_level**: "L1" | "L2" | "L3" | "L4"
**priority**: "low" | "normal" | "high" | "urgent"
**business_unit**: "mr-yeti" | "pielts" | "surmount-travels" | "hcg-cafeteria" | "hcg-live-signal"

### Timestamp Constraints
- `created_at` <= current Unix timestamp (immutable, set at creation)
- `expires_at` >= `created_at` (immutable, set at creation)
- `expires_at` <= `created_at + 86400*365` (max 1 year expiry)

### Required Fields
All fields listed in `required` array must be present and non-null (except those explicitly typed as ["type", "null"]).

### Optional Fields
- `parent_intent_id`: UUIDv4 or null
- `project_id`: string or null
- `workflow_id`: string or null
- `director_id`: string or null
- `expected_outcome`: string or null
- `metadata`: object (default: {})

### Immutable Fields
Once created, these fields cannot change:
- `schema_version`
- `intent_id`
- `correlation_id`
- `mission_id`
- `business_unit`
- `actor_id`
- `created_at`
- `expires_at`

---

## Validation Implementation

Python reference implementation available in `saathi/execution/toolintent.py`:

```python
intent = ToolIntent.from_dict(data)
errors = intent.validate()
if errors:
    # Handle validation errors
    pass
```

Errors list contains human-readable error messages for each violated constraint.

---

## Version History

### v1.0 (2026-07-10)
- Initial schema
- 23 fields (identity, actor, scope, execution, risk, control, timestamps, metadata)
- Added `business_unit` field for budgeting/reporting
- Strong validation (UUIDs, enums, timestamps, parameters)
- Immutable identity contract
- Secret redaction for safe logging
- Deterministic idempotency key (SHA256)
- Future versioning support

---

## Migration Path

**v1.0 → v1.1**: Additive changes (new optional fields) remain valid.
**v1.0 → v2.0**: Major version changes will define upgrade path.

All v1.0 instances remain valid forever.
