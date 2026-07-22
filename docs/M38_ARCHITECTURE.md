# M38 — Architecture

Thin multi-session reliability layer composed on M31–M37.

## Components

| Component | Module | Role |
|-----------|--------|------|
| MultiSessionCoordinator | `saathi/credentials/m38.py` | Bounded concurrency, budgets, lifecycle orchestration |
| Session state machine | same | Explicit validated transitions |
| RetryPolicy | same | Deterministic bounded backoff |
| Recovery / reconcile | same | Cleanup-only recovery; no secret reopen from evidence |
| Canary readiness evaluator | same | Read-only verdict; never grants CANARY |
| Session execution | M37 `run_provider_lifecycle` | Per-session secret/handle/provider path |
| Provider | M37 SandboxProvider / github_meta | Unchanged contract |

## Non-goals

No second session engine, lease store, credential registry, HTTP transport, or
ungoverned workers. No CANARY/ACTIVE/production grant.
