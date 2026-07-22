# ADR: ToolIntent as Immutable Execution Contract

**Date:** 2026-07-10  
**Status:** ACCEPTED  
**Context:** Phase 3.1 execution infrastructure  

## Decision

ToolIntent is the immutable, canonical specification for every external action in SaathiOS.

All consequential actions must be:
1. Represented as a ToolIntent
2. Routed through ExecutionGateway
3. Validated once at creation
4. Never modified to bypass approval/authorization

## Immutability Guarantee

- **Identity fields** (intent_id, correlation_id, mission_id, business_unit, actor_id, created_at, expires_at) are immutable
- **Mutable fields** (parameters, priority, timeout, metadata) may be refined by approval workflow
- **Idempotency key** is computed once at creation; stable across parameter refinements
- **Authorization decisions** are based on state at creation time; later mutations don't affect approval validity
- **Isolation** via defensive deep copy: source dict mutation, external mutation of returned dicts cannot affect intent

## Boundaries

```
ToolIntent = immutable requested action (identity, audit, idempotency)
ExecutionGateway = authorization, approval, credential access, execution control
Connector = untrusted external capability (no direct SDK access)
```

What ExecutionGateway does NOT put back into ToolIntent:
- Approval records
- Execution state (queued, running, retrying)
- Credentials or credential leases
- Cost reservations
- Execution results
- Error details

All of these go to separate artifacts (Evidence, Timeline, Audit Trail).

## Implementation

- Frozen dataclass (`@dataclass(frozen=True)`) prevents field reassignment
- `__post_init__()` performs defensive deep copy of parameters/metadata (prevents source mutation)
- `from_dict()` and `to_dict()` perform deep copy (prevents external mutation)
- Validation runs once at creation; idempotency key computed and stable
- Phase 3.2 ExecutionGateway must not modify ToolIntent fields

## Testing

52 tests passing:
- 36 original schema + validation tests
- 5 JSON serialization tests (determinism, NaN/Infinity rejection)
- 6 deep immutability tests (mutation isolation)
- 5 event integration tests

## Rationale

**Why immutable?** Authorization decisions, approval caching, audit trails, and idempotency detection all depend on a stable, unchanging intent. Any mutation after hashing/approval invalidates those guarantees.

**Why separate-from-execution?** The intent says "what to do"; the gateway decides "whether to do it" and "how to do it safely." Mixing them creates feedback loops and makes it hard to audit who decided what.

**Why defensive copy?** Prevents accidental authorization bypass via external dict mutation. Callers who modify intent.parameters are not breaking the intent contract (it's intentionally mutable for approval workflow), but their changes won't invalidate the idempotency key or bypass the approval decision made at creation time.

## Related

- PHASE3.1_PRODUCTION_READINESS_REPORT.md
- TOOLINTENT_SPEC.md
- TOOLINTENT_SCHEMA.md
- Phase 3.2: ExecutionGateway design
