# ADR: VideoBackendPolicy Engine

**Date:** 2026-07-10
**Status:** ACCEPTED_WITH_LIMITATIONS (FM-C1 normalized)
**Implementation status:** Policy engine design accepted; enforcement must remain under ExecutionGateway
**Context:** Phase 3.2 video production architecture; backend routing decisions
**Related:** ADR-CLAUDEVIDEO-RENDERING.md, ADR-OPENMONTAGE-SEPARATE-SERVICE.md, ADR-EXECUTIONGATEWAY-SPECIFICATION.md
**Authority impact:** Routing policy only — not a second execution gateway

---

## Problem

Two video backends exist:
- **Claude Video Toolkit** (fast, low-cost, limited quality)
- **OpenMontage** (slow, expensive, production-ready)

Previous designs used hardcoded routing: `mode='quick'|'production'`.

This is insufficient. Routing decisions depend on:
- business unit priorities
- mission criticality
- budget constraints
- time pressure
- quality expectations
- character type
- provider health
- queue depth
- data sensitivity
- user override preferences

A single binary choice cannot express this complexity. Requires a decision engine.

---

## Decision

**Implement VideoPolicyEngine:** A standalone component that evaluates contextual signals and returns a routing decision (backend, options, constraints).

No hardcoded routing. No magic strings. Every decision is traceable to policy rules.

---

## VideoBackendPolicy Architecture

```
ToolIntent (video-generation operation)
    ↓
VideoBackendPolicy.evaluate(intent, context)
    ↓
Policy engine reads:
  ├─ intent.business_unit
  ├─ intent.mission_id
  ├─ intent.metadata.urgency
  ├─ intent.metadata.budget
  ├─ intent.metadata.duration_sec
  ├─ intent.metadata.quality_tier
  ├─ intent.metadata.character_type
  ├─ intent.metadata.data_sensitivity
  ├─ intent.expires_at (deadline)
  ├─ context.provider_health (Ollama, Claude, OpenMontage)
  ├─ context.queue_depth (by backend)
  ├─ context.user_preference (cloud/local)
  └─ context.override_user (user_id)
    ↓
Decision vector:
  ├─ backend_choice (claude_toolkit | openmontage | fallback)
  ├─ options (quality settings, parallelization, retry budget)
  ├─ constraints (max_cost, max_duration, approval_required)
  ├─ fallback_chain ([primary], [secondary], [tertiary])
  └─ rationale (why this decision)
    ↓
ExecutionGateway applies decision
```

---

## Policy Input Signals

### From ToolIntent (immutable)

| Signal | Type | Example | Impact |
|--------|------|---------|--------|
| `business_unit` | string | "baadar", "pielts", "hcgms" | Priority tier |
| `mission_id` | UUID | | Traceability |
| `actor_id` | string | "user:123" | Access control |
| `expires_at` | ISO8601 | 2026-07-10T15:30:00Z | Deadline pressure |
| `metadata.urgency` | "low", "normal", "high", "critical" | | Speed vs. cost |
| `metadata.budget` | float | 2.50 | Max spend allowed |
| `metadata.duration_sec` | int | 60 | Video length |
| `metadata.quality_tier` | "draft", "social", "broadcast" | | Quality target |
| `metadata.character_type` | string | "yeti", "generic" | Rigging complexity |
| `metadata.data_sensitivity` | "public", "internal", "confidential" | | Privacy constraints |
| `metadata.user_preference` | "cloud", "local", "any" | | Infrastructure choice |
| `metadata.user_override` | bool | | Skip routing logic |

### From ExecutionContext (dynamic)

| Signal | Type | Example | Impact |
|--------|------|---------|--------|
| `provider_health["claude_toolkit"]` | "healthy", "degraded", "unavailable" | | Fallback trigger |
| `provider_health["openmontage"]` | "healthy", "degraded", "unavailable" | | Primary viability |
| `provider_health["ollama"]` | "healthy", "degraded", "unavailable" | | Local inference |
| `queue_depth["claude_toolkit"]` | int | 3 | Latency estimate |
| `queue_depth["openmontage"]` | int | 1 | Throughput |
| `current_time` | ISO8601 | | Time-sensitive logic |
| `business_hour` | bool | | Priority scheduling |
| `cloud_cost_today` | float | 45.67 | Daily cap logic |
| `user_tier` | "free", "pro", "enterprise" | | Quota enforcement |

---

## Routing Rules (Decision Tree)

```python
if intent.metadata.user_override:
    # User explicitly requested backend (within authorization scope)
    backend = intent.metadata.user_override
    if not is_authorized_for_backend(actor, backend):
        return DENIED("backend not authorized for this actor")
    if not is_backend_healthy(backend):
        return TRY_FALLBACK(rationale="requested backend unavailable")
else:
    # Policy-driven routing

    if intent.metadata.urgency == "critical":
        # Must complete before deadline
        seconds_remaining = (intent.expires_at - now).total_seconds()
        if seconds_remaining < 300:
            backend = "claude_toolkit"  # fast only
            budget_override = intent.metadata.budget * 1.5
        else:
            backend = best_by_deadline(seconds_remaining)

    elif intent.metadata.urgency == "high":
        # High priority, good budget
        if intent.metadata.budget >= 5.0:
            backend = "openmontage"  # quality
            fallback = ["claude_toolkit"]
        else:
            backend = "claude_toolkit"
            fallback = ["openmontage_budget_limited"]

    elif intent.metadata.urgency == "normal":
        # Balance cost and quality
        if intent.metadata.quality_tier in ["broadcast", "high"]:
            backend = "openmontage"
            fallback = ["claude_toolkit"]
        elif intent.metadata.quality_tier in ["social", "draft"]:
            backend = "claude_toolkit"
            fallback = ["openmontage"]
        else:
            backend = "claude_toolkit"

    elif intent.metadata.urgency == "low":
        # Cost optimization
        if cloud_cost_today >= DAILY_BUDGET * 0.8:
            backend = "local_only" (Ollama)
            fallback = []
        else:
            backend = "claude_toolkit"
            fallback = ["openmontage"]

# Health gating
if not is_backend_healthy(backend):
    backend, fallback = rotate_fallback_chain(fallback)

# Approval gating
if backend == "openmontage" and intent.metadata.budget > APPROVAL_THRESHOLD:
    policy.requires_approval = True
    policy.approval_deadline = now + timedelta(hours=1)

# Cost constraint
if backend == "openmontage":
    estimated_cost = estimate_cost(intent.metadata)
    if estimated_cost > intent.metadata.budget:
        return DENIED("cost exceeds budget")
    policy.cost_reservation = estimated_cost

return policy
```

---

## Policy Decision Output

```python
@dataclass
class VideoBackendPolicyDecision:
    backend: Literal["claude_toolkit", "openmontage", "ollama", "none"]

    # Routing
    fallback_chain: List[str]

    # Constraints
    max_cost_usd: float
    max_duration_sec: int
    approval_required: bool
    approval_deadline: Optional[ISO8601]

    # Options
    parallel_encoding: bool
    retry_budget: int
    timeout_sec: int
    quality_override: Optional[str]

    # Observability
    rationale: str
    rule_matched: str
    confidence: float  # 0.0-1.0

    # Timestamps
    decided_at: ISO8601
    valid_until: ISO8601
```

---

## Fallback Chains

No backend is 100% reliable. Fallback happens when:
- Primary backend is unhealthy
- Primary times out or rate-limits
- Primary rejects the request
- User-triggered retry with fallback flag

**Fallback chains are policy-defined, never ad-hoc:**

| Scenario | Primary | Secondary | Tertiary |
|----------|---------|-----------|----------|
| High quality needed | OpenMontage | Claude Toolkit | Ollama (local) |
| Fast turnaround | Claude Toolkit | OpenMontage | Fail (no 3rd option) |
| Cost-optimized | Ollama | Claude Toolkit | OpenMontage |
| Critical deadline | Claude Toolkit | Ollama | Fail (no fallback) |

Each fallback is attempted once. Failed fallbacks do not retry automatically.

---

## Cost Optimization

Policy gates costs at three levels:

### 1. Reservation (at routing decision)
```python
if backend == "openmontage":
    estimated_cost = calculate_cost(duration, quality, character)
    if estimated_cost > budget:
        deny_request()  # Gate before execution
    cost_reservation = reserve(estimated_cost)
```

### 2. Reconciliation (after execution)
```python
actual_cost = result.metadata.cost_usd
if actual_cost > cost_reservation:
    # Log overrun, alert
    log_cost_variance(estimated_cost, actual_cost)
if actual_cost < cost_reservation:
    # Release overage
    release(cost_reservation - actual_cost)
```

### 3. Daily/Monthly caps
```python
if business_unit_daily_spend >= DAILY_CAP:
    route_to_ollama_only()  # Force local if budget exceeded
if business_unit_monthly_spend >= MONTHLY_CAP:
    deny_all_video_requests()  # Hard stop
```

---

## Policy Override Semantics

A user CAN request a specific backend, but CANNOT bypass:

- **Authorization** — user must have permission for the backend
- **Approval** — high-cost operations still require approval
- **Budget** — request still subject to cost constraints
- **Provider health** — unavailable backends are unavailable
- **Data sensitivity** — "confidential" data cannot use cloud providers
- **Rate limits** — daily/monthly quotas still apply

```python
if user_override_requested:
    if not is_authorized(actor, backend):
        return DENIED("not authorized for this backend")
    if is_sensitive_data(intent) and backend == "openmontage":
        return DENIED("confidential data cannot use external providers")
    if estimate_cost(intent) > budget:
        return DENIED("cost exceeds budget")
    # Override allowed
    decision.backend = user_override
else:
    # Policy routing applies
    decision = apply_routing_rules(intent, context)
```

---

## Rationale

**Why separate policy engine?**
- Routing decisions are business logic, not infrastructure
- Policy rules must be versioned and auditable
- A/B testing policy variants (cost-optimized vs. quality-optimized)
- Different business units may have different policies
- Easier to add new backends without rewriting routing code

**Why multiple signals?**
- Single binary routing (quick|production) cannot capture the complexity of real video production
- Decisions depend on urgency, budget, quality, character type, provider health, deadline
- Policy rules make the decision transparent and debuggable

**Why policy is immutable during execution?**
- Once a decision is made, ExecutionGateway executes against that decision
- Changing policy mid-execution creates inconsistency
- Policy is re-evaluated only for retries/fallbacks

---

## Testing

Policy engine must have:

1. **Unit tests** — each routing rule
   - Urgency-based routing
   - Budget-based routing
   - Quality-based routing
   - Health-gated routing
   - Fallback chain correctness

2. **Integration tests** — end-to-end scenarios
   - Happy path: normal request → claude_toolkit
   - Expensive request → openmontage → approval
   - Urgency escalation → fast backend
   - Budget exceeded → deny or local-only
   - Backend unavailable → fallback
   - User override with authorization
   - User override without authorization → deny

3. **Simulation tests** — cost and latency metrics
   - Monthly cost distribution by backend
   - Approval SLA compliance
   - Fallback effectiveness
   - Queue depth impact

---

## Related Decisions

- **ADR-CLAUDEVIDEO-RENDERING.md** — video backend options (dual-backend hybrid)
- **ADR-EXECUTIONGATEWAY-SPECIFICATION.md** — how policy decision is enforced
- **ADR-OPENJARVIS-LOCAL-RUNTIME.md** — local inference as fallback option

---

**Status:** ACCEPTED
**Implementation:** Begin Phase 3.2
**Owner:** Infrastructure Team
**Review:** Policy rules must be approved by Finance (cost optimization) and Product (user experience)
