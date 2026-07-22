# M17.22 Architecture — Universal ExecutionGateway (Phase 1)

## Position in the stack

ExecutionGateway is the **single authoritative boundary** for external actions.
It does not replace ConnectorManager substrate, Mission Engine, Run Ledger, or
Trading Guardian — it sits above connector/CLI/local/MCP handlers and records
every attempt durably.

```text
Caller (API / CLI / agent / Control Center action)
  ↓ builds
ToolIntent (immutable)
  ↓
ExecutionGateway.submit  ← authoritative boundary (this milestone)
  ├─ Validation
  ├─ Permission
  ├─ Risk evaluation
  ├─ Approval (digest-bound; reuses existing approval model)
  ├─ Queued / Running
  └─ Handler dispatch by family
        ├─ connector  → connectors.platform.ExecutionEngine substrate
        ├─ cli        → same substrate (CLI tools)
        ├─ local      → built-in local handler (echo/noop/…)
        └─ mcp        → same substrate (MCP tools)
  ↓ always
Evidence Store · Security Timeline · Run Ledger · Event Bus
  ↓ observe
Control Center cell · CEO daily brief (gated)
```

## Hard invariants

1. No connector side effect outside `ExecutionGateway.submit` (Phase 1 path).
2. ToolIntent is never mutated.
3. Secrets never appear in records, metrics, events, or summaries.
4. Terminal states are immutable.
5. Invalid transitions fail closed (`StateException`).
6. Same digest / idempotency key does not double-execute.
7. Approval binds to ToolIntent digest; content change invalidates approval.
8. Trading Guardian (`saathi.execution.trade`) is **unchanged** and out of Phase 1.

## Durable ExecutionRecord

Fields: execution_id, tool_intent_digest, actor, target, created, started,
finished, status, approval, risk, evidence_id, result_summary,
failure_category, retry_count (+ ledger_run_id, security_event_id,
idempotency_key, transition_log).

Store: `data/execution_gateway/executions.db` (SQLite, WAL, restart-safe).

## State machine

See `saathi/execution/execution_state.py`. Explicit allow-list only.

## Approval

- Auto: low risk / L1 when not flagged
- Required: L3/L4 or high/critical risk without bound approval
- Connector store continues exact-action `input_hash` approvals; when already
  resolved, gateway metadata `approval_pre_resolved` avoids double-gating

## Retry

Reuses `saathi.application_harness.run_ledger.retry_delay` and max attempts.
Retry only from `failed` with `retryable=True`, after backoff, under max count.

## Observability

- Control Center: `execution_gateway()` cell + overview + attention
- CEO: summary only on failures / retries / approval backlog / high latency
- Critical checks: `execution.*` (5 blocking)

## Non-goals (Phase 1)

Browser automation, n8n, LLM model gateway migration, Trading Guardian
unification, multi-host consensus, distributed queues.
