# M46 — Architecture

```
Operator approval (local, gitignored)
    + M44 RolloutRequest
    + M45 RuntimeSnapshot
    + M43/M43.1 evidence bindings
        → preflight (fail-closed)
        → READY_FOR_ONE_COMMAND_LIVE_GATE (only if live env gate)
        → run_canary (read-only, ≤1%, budgeted)
        → CANARY_COMPLETED_PENDING_REVOCATION
        → [manual] external revoke
        → run_revocation (live 401 only)
        → REVOCATION_VERIFIED_PENDING_CLEANUP
        → [manual] remove local reference
        → verify_cleanup (exact absence)
        → CLOSED_ADVISORY_ONLY  (still grants nothing)
```

## State machine

DRAFT → AWAITING_APPROVAL → APPROVAL_VALIDATED → PREFLIGHT_PASSED →
READY_FOR_ONE_COMMAND_LIVE_GATE → CANARY_RUNNING →
CANARY_COMPLETED_PENDING_REVOCATION → REVOCATION_VERIFIED_PENDING_CLEANUP →
CLOSED_ADVISORY_ONLY

Failure paths: BLOCKED / ABORTED / ROLLED_BACK / FAILED

No state implies ACTIVE, production, write, deploy, or autonomous authority.
