# M17.22 — Universal ExecutionGateway (Phase 1) Validation

## Scope delivered

One authoritative **ExecutionGateway** boundary for external actions.

Every connector / CLI / local / MCP action eventually enters:

```text
ToolIntent
  → Validation
  → Permission
  → Risk evaluation
  → Approval check
  → ExecutionGateway.submit
  → Handler (ConnectorManager substrate / local tool)
  → Evidence
  → Security Event
  → Run Ledger
  → CEO Metrics (via Control Center + daily brief)
```

Phase 1 **does not** migrate browser automation, n8n, LLM execution, or
Trading Guardian. Those remain future migration work.

## Execution states (deterministic)

| State | Terminal? |
|-------|-----------|
| requested | no |
| validated | no |
| denied | **yes** |
| approval_required | no |
| approved | no |
| queued | no |
| running | no |
| succeeded | **yes** |
| failed | **yes** |
| cancelled | **yes** |
| expired | **yes** |

Invalid transitions and terminal mutations raise `StateException`.

## Approval

Reuses existing approval model (risk / approval level + connector store binding).

- Automatic for low-risk / L1 when not pre-flagged
- `approval_required` when L3/L4 or high/critical risk without bound approval
- Approval binds to **ToolIntent digest**; changing the intent invalidates approval
- Connector substrate continues exact-action `input_hash` binding (not replaced)

## Retry

Reuses M17 `retry_delay` / max-attempt schedule from the run ledger.

- Retryable vs non-retryable failures
- Exponential backoff schedule `(0, 60, 300, 900, 3600)` seconds
- Max retry count enforced
- No duplicate side effects (idempotency + digest lock)

## Idempotency

Same ToolIntent digest / idempotency key → same execution record → no re-run.

Restart safety: stale `running`/`queued` rows recovered to `failed`
(`stale_after_restart`).

## Observability (Control Center — no new dashboard)

Cell `execution_gateway` exposes:

- running, queued, succeeded, failed, denied
- average_runtime_sec, retry_count
- recent_failures (safe summaries only)
- API: `GET /api/v1/control/execution`

## CEO OS

Daily brief section **Execution** only when:

- failures, or
- retries, or
- approval backlog, or
- average runtime ≥ 30s

No spam on green quiet days.

## Critical checks (+5)

| id | intent |
|----|--------|
| `execution.gateway_present` | public surface + successful path |
| `execution.single_boundary` | state machine + connector gateway_ref |
| `execution.approval_enforced` | approval required + digest binding |
| `execution.idempotent` | same intent / digest replay |
| `execution.evidence_generated` | evidence + no secret leakage |

## Files

| Path | Role |
|------|------|
| `saathi/execution/execution_state.py` | states + transition graph |
| `saathi/execution/record.py` | ExecutionRecord + digest |
| `saathi/execution/store.py` | durable SQLite store |
| `saathi/execution/universal.py` | boundary pipeline |
| `saathi/execution/gateway.py` | `submit` / cancel / metrics on gateway |
| `saathi/connectors/platform/execution.py` | connectors enter via gateway |
| `saathi/control_center/aggregator.py` | execution cell + attention |
| `saathi/control_center/api.py` | `/control/execution` |
| `saathi/ceo/service.py` | brief integration |
| `tests/test_m17_22_execution_gateway.py` | focused suite |
| `saathi/repair/critical_checks.json` | +5 checks |
| `docs/M17_22_ARCHITECTURE.md` | architecture |

## Test results

- Focused M17.22: 25 passed
- M15 connectors / security / enterprise: green (approval single-use, scope deny)
- Trading Guardian: unchanged (asserted)
- Full suite: 1984 passed, 1 skipped, 0 failed
- release-check: exit 0

## Remaining migration work

- Browser automation path
- n8n workflow execution
- LLM / model gateway path (legacy integration remains)
- Trading Guardian (finance `ExecutionService` stays separate)
- Multi-host execution federation
- Production durable queue (current store is local SQLite)

## Rollback

```bash
git reset --hard <start-commit>   # 398d40e before this milestone
```

Do not push. Do not begin M17.23.
