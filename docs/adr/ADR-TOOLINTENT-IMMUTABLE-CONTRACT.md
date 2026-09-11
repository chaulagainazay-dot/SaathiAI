# ADR: ToolIntent as Immutable Execution Contract

| Field | Value |
| --- | --- |
| **ID** | ADR-TOOLINTENT-IMMUTABLE-CONTRACT |
| **Date** | 2026-07-10 |
| **Status** | **ACCEPTED_IMPLEMENTED** (FM-C1 status repair 2026-08-06) |
| **Context** | Phase 3.1 execution infrastructure |
| **Implementation status** | **Implemented** — `saathi/execution/toolintent.py` (`@dataclass(frozen=True)`, deep-copy parameters/metadata) |
| **Authority impact** | All consequential actions represented as ToolIntent and routed through ExecutionGateway |
| **Supersedes** | Informal mutable request envelopes for side effects |
| **Superseded by** | None |
| **Related** | ADR-EXECUTIONGATEWAY-SPECIFICATION |

## Decision

ToolIntent is the immutable, canonical specification for every external action in SaathiOS.

All consequential actions must be:
1. Represented as a ToolIntent
2. Routed through ExecutionGateway
3. Validated once at creation
4. Never modified to bypass approval/authorization

## Immutability Guarantee

- **All fields are immutable after construction** (`@dataclass(frozen=True)`).
- **parameters** and **metadata** are deep-copied at init; returned dicts are copies so external mutation cannot alter the intent.
- **Idempotency key** is computed once at creation and remains stable.
- **Authorization / approval** bind to the frozen intent identity; they must not rewrite ToolIntent fields. Approval *state* lives in separate records (execution/platform stores), not inside ToolIntent.
- **FM-C1 correction:** an earlier draft of this ADR claimed parameters/priority/timeout/metadata were “mutable for approval workflow.” That claim **contradicts current source** and is **rejected**. Create a new ToolIntent (new idempotency key rules apply) if the requested action changes.

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

**Why defensive copy?** Prevents accidental authorization bypass via external dict mutation. Callers cannot reassign frozen fields; copies returned from `to_dict()` isolation prevent accidental shared-dict mutation.

## Related

- PHASE3.1_PRODUCTION_READINESS_REPORT.md
- TOOLINTENT_SPEC.md
- TOOLINTENT_SCHEMA.md
- Phase 3.2: ExecutionGateway design
