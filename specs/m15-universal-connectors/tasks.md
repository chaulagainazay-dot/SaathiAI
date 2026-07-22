# M15 Tasks (drives M10 orchestration strategy)

Task graph — an M10 orchestrator derives its agent plan from this ordering
(dependencies are strict; independent leaves may run parallel).

- T1 models + catalog (risk floor, lifecycle, result envelope, capabilities) — no deps
- T2 credentials (references, in-process resolve) — no deps
- T3 adapters (deterministic fixtures + real-local fs/git) — deps: T1
- T4 store (accounts, cred refs, executions, approvals, webhooks, sync, buckets) — deps: T1,T2
- T5 registry (seed connectors + honest labels) — deps: T1,T3
- T6 execution engine (gateway-routed; approval binding; idempotency; rate;
      failure classification; uncertain no-retry; redaction) — deps: T4,T5
- T7 health platform — deps: T5
- T8 webhook platform (signature+freshness+replay) — deps: T4
- T9 sync runner (checkpointed, resumable) — deps: T6
- T10 MCP wrapper (untrusted, clamp-up risk) — deps: T5
- T11 specs governance (constitution, wrapper CLI, traceability, convergence) — deps: none
- T12 tests + manifest + docs + validation + convergence gate — deps: T6..T11

Orchestration strategy: sequential critical path T1→T4→T6, with T2/T3/T11 as
parallel leaves; T7/T8/T9/T10 fan out from T6/T5; T12 is the join/gate.
