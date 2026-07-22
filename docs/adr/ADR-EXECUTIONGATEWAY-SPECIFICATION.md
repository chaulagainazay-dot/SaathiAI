# ADR: ExecutionGateway Specification (Phase 3.2)

**Date:** 2026-07-10  
**Status:** SPECIFICATION (awaiting implementation)  
**Context:** SaathiOS Phase 3.2 execution infrastructure; blocking all external action  
**Related:** ADR-TOOLINTENT-IMMUTABLE-CONTRACT.md, ADR-VIDEO-BACKEND-POLICY.md

---

## Executive Summary

ExecutionGateway is the **single authority** for external action in SaathiOS.

Every consequential operation flows through:
```
Planner
  ↓ creates
ToolIntent (immutable request)
  ↓ routed to
ExecutionGateway
  ├─ Validator (syntax, schema, idempotency)
  ├─ Authorizer (who is allowed?)
  ├─ RiskClassifier (what could go wrong?)
  ├─ ApprovalGate (does a human need to decide?)
  ├─ CredentialManager (lease secrets safely)
  ├─ Queue (durable ordering, deduplication)
  ├─ Executor (connector invocation)
  ├─ ResultSanitizer (no secrets in output)
  ├─ Evidence (audit trail, timestamps)
  └─ EventBus (state changes)
  ↓ produces
Evidence + Result (sanitized)
```

No bypasses. No direct SDK access. No credential leakage. No silent failures.

---

## Core Invariants (HARD CONSTRAINTS)

```
1. No external action bypasses ExecutionGateway.
   Every API call, file write, network request, credential access must 
   route through the gateway.

2. ToolIntent is never modified.
   Authorization decisions, approvals, and idempotency detection depend 
   on a stable intent. Changes invalidate audit trail and approval cache.

3. Credentials never appear in ToolIntent, logs, or events.
   Credentials are leased by ExecutionGateway only, passed to connectors 
   at execution time, then collected back. No trace in results.

4. Authorization fails closed.
   If authorization cannot be determined, the request is denied. 
   No "assume allowed" logic.

5. Approval fails closed.
   If a request requires approval and approval is missing, the request 
   is queued (not executed) until approval arrives or expires.

6. Duplicate detection prevents duplicate side effects.
   Idempotency key is stable across ToolIntent creation. 
   Same intent submitted twice executes once.

7. Unknown outcomes are reconciled before retry.
   If a connector returns unclear status (timeout, partial result), 
   the gateway queries state before retrying.

8. Every attempt produces Evidence.
   Timeline, state, decision, result (or error) are recorded. 
   Audit trail is append-only.

9. Connector output is untrusted.
   Results from external systems are sanitized, validated, 
   and quota-checked before acceptance.

10. Business-unit isolation is mandatory.
    Resources, quotas, costs, and audit trails are segregated 
    by business_unit. Cross-unit access is not permitted.
```

---

## Package Structure

```
saathi/execution/
├── __init__.py
├── gateway.py                 # Main ExecutionGateway class
├── context.py                 # ExecutionContext (environment, user, time)
├── results.py                 # ExecutionResult, Evidence, Audit
├── errors.py                  # ExecutionGatewayException hierarchy
├── state.py                   # State machine definitions
├── authorization.py           # Authorizer component
├── risk.py                    # RiskClassifier component
├── approvals.py               # ApprovalGate component
├── credentials.py             # CredentialManager component
├── sanitization.py            # ResultSanitizer component
├── events.py                  # EventBus, event schemas
├── evidence.py                # Evidence schema, audit trail
├── idempotency.py             # Deduplication, idempotency key generation
├── registry.py                # Connector registry
└── queue/
    ├── base.py                # Queue interface
    ├── memory.py              # In-memory queue (testing)
    └── sqlite.py              # Durable SQLite queue
```

---

## Execution State Machine

Every ToolIntent transitions through defined states. State transitions are atomic and audited.

```
RECEIVED
  ├─ ✓ Syntax + schema validation pass
  │   → VALIDATED
  │ ✗ Syntax or schema error
  │   → REJECTED (permanent, no retry)
  │
VALIDATED
  ├─ ✓ Idempotency check: intent not seen before
  │   → AUTHORIZED
  │ ✗ Idempotency check: exact duplicate (same key, same params)
  │   → DUPLICATE (return cached result, no re-execution)
  │ ✗ Idempotency check: partial duplicate (different params, same id)
  │   → CONFLICT (requires manual resolution)
  │
AUTHORIZED
  ├─ ✓ Authorization passes (actor has permission)
  │   → RISK_CLASSIFIED
  │ ✗ Authorization fails (no permission)
  │   → DENIED (permanent, no retry)
  │
RISK_CLASSIFIED
  ├─ ✓ Risk level low or acceptable
  │   → AWAITING_APPROVAL or APPROVED (skip approval if low-risk)
  │ ✗ Risk level unacceptable
  │   → REJECTED (permanent, no retry)
  │
AWAITING_APPROVAL
  ├─ ✓ Approval arrives before deadline
  │   → APPROVED
  │ ✗ Approval deadline expires
  │   → EXPIRED
  │ ✗ Approval is rejected
  │   → REJECTED
  │
APPROVED
  ├─ ✓ Credentials obtained, connector available
  │   → QUEUED
  │ ✗ Credential error (expired, invalid, missing)
  │   → FAILED_CREDENTIAL (permanent)
  │ ✗ Connector unavailable (health check fails)
  │   → QUEUED_WITH_FALLBACK or FAILED_PROVIDER
  │
QUEUED
  ├─ Ready to execute, waiting for slot
  │   → RUNNING (when queue slot available)
  │
RUNNING
  ├─ ✓ Connector succeeds, result valid
  │   → SUCCEEDED
  │ ✗ Connector fails, error is transient
  │   → FAILED_RETRYABLE (will retry per retry policy)
  │ ✗ Connector fails, error is permanent
  │   → FAILED_FINAL (no retry)
  │ ✗ Connector timeout, state unknown
  │   → UNKNOWN_OUTCOME (reconcile before retry)
  │
SUCCEEDED
  Result captured, Evidence recorded. Terminal state.

FAILED_RETRYABLE
  Attempt 1 of N. If retries remain, re-queue. If retries exhausted, FAILED_FINAL.

FAILED_FINAL
  Permanent failure. No more retries. Terminal state.

UNKNOWN_OUTCOME
  Timeout or partial result. Gateway queries connector state before retry.
  ├─ ✓ State query confirms completed
  │   → SUCCEEDED or FAILED_FINAL (depending on query result)
  │ ✗ State query cannot determine outcome
  │   → FAILED_FINAL (err on side of caution)

EXPIRED
  Approval deadline passed without decision. Terminal state.

REJECTED
  Authorization, approval, or risk check rejected. Terminal state.

DENIED
  Authorization check denied permission. Terminal state.

DUPLICATE
  Idempotency: exact duplicate detected. Return cached result. Terminal state.

CANCELLED
  User or system cancelled in progress. Terminal state.

```

Every state transition emits an event (append-only). Example:

```
event_type: "intent.state_changed"
timestamp: 2026-07-10T10:15:30.123Z
intent_id: "intent:12345"
old_state: "AUTHORIZED"
new_state: "RISK_CLASSIFIED"
risk_level: "high"
reasoning: "operation_cost_exceeds_threshold"
actor_id: "user:456"
```

---

## Component Contracts

### 1. Validator

**Input:** ToolIntent (JSON or dict)  
**Output:** (valid, error_details) or raises ExecutionGatewayException

Checks:
- Intent schema matches ToolIntent spec (type, fields, constraints)
- No required fields are missing
- Enum fields are valid
- Numeric fields are in range
- String fields are non-empty
- Timestamp fields are valid ISO8601
- Parameters dict is not empty
- Idempotency key is deterministic (same input → same key)

```python
def validate(intent: dict | ToolIntent) -> (bool, Optional[str]):
    """
    Returns (is_valid, error_message_or_none)
    Raises nothing. Validation is not an error; it's a gate.
    """
```

### 2. Authorizer

**Input:** ToolIntent, ExecutionContext (actor, role, permissions)  
**Output:** (authorized, reason) or raises AuthorizationException

Checks:
- Actor has explicit permission for operation type
- Actor has access to business_unit
- Actor's role permits this risk level
- Actor's quota allows this operation

```python
def authorize(intent: ToolIntent, context: ExecutionContext) -> (bool, str):
    """
    Returns (is_authorized, reason)
    """
```

### 3. RiskClassifier

**Input:** ToolIntent, ExecutionContext, VideoBackendPolicy  
**Output:** RiskClassification (level, factors, rationale)

Classifies:
- Cost risk (exceeds budget? exceeds daily cap?)
- Data risk (sensitive data? external provider?)
- Latency risk (deadline approaching?)
- Provider risk (provider unhealthy?)
- Fallback risk (fallback available? fallback healthy?)

```python
@dataclass
class RiskClassification:
    level: Literal["low", "medium", "high", "critical"]
    factors: Dict[str, Any]  # {"cost_risk": "high", "deadline_risk": "low", ...}
    requires_approval: bool
    approval_deadline: Optional[datetime]
    rationale: str
```

### 4. ApprovalGate

**Input:** ToolIntent, RiskClassification, ExecutionContext  
**Output:** ApprovalDecision (approved, rejected, pending, expired)

Workflow:
- If risk.level <= "medium", auto-approve (no human needed)
- If risk.level > "medium", create approval record and wait
- Approval timeout: if no decision within deadline, auto-reject
- Approval can be granted, denied, or sent back for revision

```python
def check_approval(
    intent: ToolIntent,
    risk: RiskClassification,
    context: ExecutionContext,
) -> ApprovalDecision:
    """
    Returns ApprovalDecision(status, decision_by, timestamp, rationale)
    """
```

### 5. CredentialManager

**Input:** ToolIntent, backend_identifier  
**Output:** LeaseToken (credentials, expiry, id)

- Retrieves secret from vault (never stored in intent)
- Grants short-lived lease (15 min default)
- Logs access (who, when, why)
- Invalidates lease on execution completion (or timeout)
- Audit: every credential access is recorded

```python
class LeaseToken:
    credential_id: str
    plaintext: Optional[str]  # None if using cloud provider SDKs
    expiry: datetime
    lease_id: str
    
def lease_credentials(intent: ToolIntent, backend: str) -> LeaseToken:
    """
    Returns LeaseToken. Caller must release() when done.
    Raises CredentialException if secret missing or invalid.
    """

def release_credential(lease: LeaseToken) -> None:
    """
    Invalidates the lease. Called after execution.
    """
```

### 6. Queue

**Input:** ToolIntent (after approval)  
**Output:** QueuedItem (position, eta, id)

- Durable: survives process restart (SQLite backend)
- In-memory for testing
- FIFO ordering with priority levels
- Deduplication: exact same intent not queued twice
- Status tracking: who's running, how many retries

```python
class QueuedItem:
    intent_id: str
    position: int
    eta: datetime
    retry_count: int
    attempt_number: int
    
def enqueue(intent: ToolIntent, priority: int = 0) -> QueuedItem:
    """
    Returns QueuedItem with position in queue.
    """

def dequeue() -> Optional[ToolIntent]:
    """
    Returns next queued intent (FIFO). Returns None if queue empty.
    """
```

### 7. Executor

**Input:** ToolIntent, credentials (LeaseToken), RetryPolicy  
**Output:** ExecutionResult (status, data, cost, duration, errors)

Invokes connector (external system). Handles:
- Network errors (retry)
- Timeouts (mark as unknown outcome, reconcile)
- Partial results (validate, accept if usable)
- Rate limits (backoff, re-queue)
- Quota exceeded (fail, do not retry)

```python
class ExecutionResult:
    status: Literal["success", "failed", "timeout", "partial"]
    data: Optional[dict]
    cost_usd: Optional[float]
    duration_sec: float
    error: Optional[ExecutionError]
    connector_trace: dict
    timestamp: datetime

def execute(
    intent: ToolIntent,
    credentials: LeaseToken,
    retry_policy: RetryPolicy,
) -> ExecutionResult:
    """
    Invokes connector. Returns ExecutionResult.
    Does NOT raise exceptions; failures are part of result.
    """
```

### 8. ResultSanitizer

**Input:** ExecutionResult (from connector)  
**Output:** SanitizedResult (no secrets, validated data)

Checks:
- No credentials in result data
- No bearer tokens or API keys
- No personally identifiable information (unless authorized)
- Result matches expected schema
- Cost is within reserved budget

```python
def sanitize(result: ExecutionResult, intent: ToolIntent) -> SanitizedResult:
    """
    Returns sanitized result (safe for logging, evidence, results cache).
    Raises ResultException if sanitation fails (malformed, contains secrets, etc.)
    """
```

### 9. Evidence & Audit

Every attempt produces an immutable Evidence record.

```python
@dataclass(frozen=True)
class Evidence:
    intent_id: str
    attempt_number: int
    state_transitions: List[StateTransition]
    authorization: AuthorizationDecision
    approval: Optional[ApprovalDecision]
    risk_classification: RiskClassification
    execution_result: ExecutionResult
    sanitized_result: SanitizedResult
    cost_reserved: float
    cost_actual: float
    timestamps: TimestampRecord
    actor_id: str
    
    # Immutability guarantee
    def __hash__(self) -> int:
        # Hashable for deduplication
        
    def to_audit_log(self) -> str:
        # Structured log entry (JSON-safe)
```

### 10. EventBus

Every state change, authorization decision, approval, execution event is published.

```python
events = [
    "intent.received",          # New intent created
    "intent.validated",         # Schema validation passed
    "intent.validation_failed", # Schema error
    "intent.duplicate",         # Idempotency hit
    "authorization.passed",     # Authorization succeeded
    "authorization.denied",     # Authorization failed
    "risk.classified",          # Risk level determined
    "approval.requested",       # Approval workflow started
    "approval.approved",        # Approval granted
    "approval.rejected",        # Approval denied
    "approval.expired",         # Deadline passed
    "execution.queued",         # Enqueued for execution
    "execution.started",        # Connector invoked
    "execution.succeeded",      # Connector returned success
    "execution.failed",         # Connector failed
    "execution.retrying",       # Retry attempt N of M
    "execution.timeout",        # Connector timeout
    "execution.unknown_outcome",# Outcome unclear, reconciling
    "credential.leased",        # Credential obtained
    "credential.released",      # Credential invalidated
    "result.sanitized",         # Result cleaned of secrets
    "cost.reconciled",          # Cost calculated and reconciled
]

def emit(event_type: str, data: dict) -> None:
    """
    Publishes event to EventBus. All subscribers notified.
    Events are append-only, immutable after emission.
    """
```

---

## Idempotency Model

**Idempotency key** is computed once at ToolIntent creation. Same intent submitted multiple times must have same key.

```python
def compute_idempotency_key(intent: ToolIntent) -> str:
    """
    Hash of:
      - intent_id (static)
      - operation (static)
      - business_unit (static)
      - parameters (deterministic JSON)
      - expires_at (static)
    
    Excludes:
      - metadata.priority (mutable)
      - metadata.timeout (mutable)
      - created_at (changes on re-submission)
    
    Result: stable SHA256 hex string
    """
    
def is_duplicate(key: str, db: ExecutionDB) -> bool:
    """
    Returns True if exact same key was executed before.
    """
    
def get_cached_result(key: str, db: ExecutionDB) -> Optional[Evidence]:
    """
    Returns cached Evidence from prior execution.
    """
```

If duplicate detected:
- Look up prior Evidence
- Return prior sanitized result
- Do NOT re-execute connector
- Emit "intent.duplicate" event
- Increment "duplicate_hit" counter

---

## Retry Classification

Not all failures should retry.

```python
@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_strategy: Literal["exponential", "linear"] = "exponential"
    backoff_base_sec: int = 1
    backoff_max_sec: int = 300
    
def classify_failure(error: ExecutionError) -> RetryableStatus:
    """
    Returns:
      - RETRYABLE: transient error, safe to retry
      - NOT_RETRYABLE: permanent error, do not retry
      - UNKNOWN_OUTCOME: unclear, reconcile first before retry
    """

# Examples:
#   HTTP 429 (rate limit)      → RETRYABLE
#   HTTP 500 (server error)    → RETRYABLE
#   HTTP 401 (unauthorized)    → NOT_RETRYABLE
#   HTTP 403 (forbidden)       → NOT_RETRYABLE
#   HTTP 400 (bad request)     → NOT_RETRYABLE
#   timeout (> 5 min)          → UNKNOWN_OUTCOME (reconcile first)
#   timeout (< 5 min)          → RETRYABLE
#   network unreachable        → RETRYABLE (maybe transient)
#   "out of quota"             → NOT_RETRYABLE (cost-related)
#   partial result             → depends on operation
```

---

## Unknown Outcome Reconciliation

When a connector times out or returns unclear status, gateway queries state before retrying.

```python
def reconcile_unknown_outcome(
    intent: ToolIntent,
    last_execution: ExecutionResult,
    credentials: LeaseToken,
) -> ExecutionResult:
    """
    Calls connector's status-query API (if available) to check outcome.
    
    Examples:
      - Video generation timeout: query render service for job status
      - Payment failed: query payment processor for transaction status
      - DB write timeout: SELECT to verify write succeeded
    
    Returns:
      - If operation succeeded: ExecutionResult(status="success", ...)
      - If operation failed: ExecutionResult(status="failed", ...)
      - If still unknown: ExecutionResult(status="unknown", retry_recommended=False)
    """
```

---

## Authorization Decision Contract

```python
@dataclass
class AuthorizationDecision:
    granted: bool
    actor_id: str
    operation: str
    business_unit: str
    risk_level_allowed: Literal["low", "medium", "high"]
    quota_available: bool
    rationale: str
    timestamp: datetime
    denied_reason: Optional[str]  # if not granted
```

Reasons for denial:
- "actor_not_found"
- "operation_not_permitted"
- "business_unit_not_accessible"
- "risk_level_exceeds_quota"
- "insufficient_quota"
- "data_sensitivity_restricted"
- "provider_policy_violation"

---

## Approval Binding

If approval is required:

```python
@dataclass
class ApprovalRecord:
    intent_id: str
    requested_at: datetime
    deadline: datetime
    requested_by_actor_id: str
    risk_level: str
    risk_rationale: str
    
    # Decision (set when approved/rejected)
    decided_at: Optional[datetime] = None
    decided_by_actor_id: Optional[str] = None
    decision: Literal["approved", "rejected", "expired"] = None
    decision_rationale: str = None
    
    # Binding
    is_final: bool = False  # Once set, cannot change
```

Approval rules:
- A single approval cannot cover two intents (1:1 relationship)
- Approval expires if decision not made by deadline
- Expired approval = automatic rejection
- Once approved, cannot be un-approved (immutable)
- Rejection can be appealed (create new approval request)

---

## Credential Lease Contract

```python
@dataclass(frozen=True)
class LeaseToken:
    credential_id: str
    secret_name: str  # e.g., "claude_api_key", "openai_api_key"
    plaintext: Optional[str]  # Only if secret is direct value
    sdk_context: Optional[object]  # e.g., OpenAI(api_key=...) instance
    obtained_at: datetime
    expires_at: datetime
    lease_id: str
    approved_by_actor_id: str
```

- Lease is short-lived (15 min default, max 1 hour)
- Plaintext secret is never stored (only in memory during execution)
- Lease ID is logged (audit: who used which secret when)
- Lease is invalidated on completion (no lingering credentials)

---

## Result Sanitization Rules

Before returning result to user:

1. **Strip credentials**
   - Remove bearer tokens
   - Remove API keys
   - Remove passwords
   - Remove session IDs

2. **Strip PII** (if not explicitly authorized)
   - Phone numbers
   - Email addresses
   - Social security numbers
   - Internal IDs

3. **Validate data**
   - Matches expected schema
   - No suspicious nested credentials
   - No excessively large blobs

4. **Cost verification**
   - Actual cost <= reserved cost (within 10% tolerance)
   - If actual > reserved, flag as variance

```python
def sanitize(result: ExecutionResult, intent: ToolIntent) -> SanitizedResult:
    """
    Strips secrets, PII, validates schema.
    Returns clean result safe for logging.
    Raises ResultException if sanitization fails.
    """
```

---

## Business Unit Isolation

Every ToolIntent must specify business_unit. ExecutionGateway enforces:

- Cost tracking: separate budgets per business unit
- Quotas: separate quotas per business unit
- Audit: separate audit trails per business unit
- Authorization: actor must have access to business unit
- Results: results are tagged with business_unit

```python
ALLOWED_BUSINESS_UNITS = ["baadar", "pielts", "hcgms", "crypto_signal"]

if intent.business_unit not in ALLOWED_BUSINESS_UNITS:
    raise ExecutionGatewayException("business_unit_not_recognized")

if not is_actor_authorized_for_business_unit(actor_id, intent.business_unit):
    raise AuthorizationException("business_unit_not_accessible")
```

---

## Observability

ExecutionGateway emits metrics:

- `gateway.intents_received_total` (counter, by business_unit, operation)
- `gateway.intents_validated_total` (counter, by business_unit)
- `gateway.intents_authorized_total` (counter, by business_unit, decision)
- `gateway.intents_approved_total` (counter, by business_unit, decision)
- `gateway.intents_queued_total` (counter, by business_unit)
- `gateway.intents_executed_total` (counter, by business_unit, status)
- `gateway.execution_duration_sec` (histogram, by operation)
- `gateway.execution_cost_usd` (histogram, by operation)
- `gateway.retry_count` (counter, by reason)
- `gateway.duplicates_detected_total` (counter)
- `gateway.queue_depth` (gauge, by backend)
- `gateway.approval_latency_sec` (histogram)
- `gateway.credential_leases_active` (gauge)

---

## Testing

### Unit Tests
- Each component in isolation
- Happy paths + error paths
- State machine transitions
- Idempotency key determinism
- Sanitization rules

### Integration Tests
- End-to-end flow: intent → execution → result
- Approval workflow
- Fallback chain
- Duplicate detection
- Retry logic
- Unknown outcome reconciliation

### Security Tests
- Authorization enforcement
- Credential isolation
- Result sanitization
- Business unit isolation
- Audit trail integrity

### Chaos Tests
- Provider timeout
- Provider rate limit
- Provider unhealthy
- Credential expired
- Queue failure
- Out of quota
- Approval timeout

---

## Migration Path (from Phase 3.1)

ExecutionGateway will be built incrementally:

**Week 1:** Validator + state machine core  
**Week 2:** Authorizer + RiskClassifier  
**Week 3:** ApprovalGate + CredentialManager  
**Week 4:** Queue (in-memory) + Executor  
**Week 5:** Queue (SQLite, durable) + ResultSanitizer  
**Week 6:** Evidence + EventBus  
**Week 7:** Integration testing + idempotency audit  
**Week 8:** Production deployment + monitoring  

No adapter work (Claude, OpenJarvis, OpenMontage) begins until ExecutionGateway is stable.

---

**Status:** SPECIFICATION (awaiting implementation)  
**Owner:** Infrastructure Team  
**Implementation Start:** 2026-07-15  
**Target Completion:** 2026-08-26  
**Blocking:** All Phase 3.2+ work (video, local runtime, media adapters)
