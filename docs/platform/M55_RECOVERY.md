# M55 Recovery Certification

`POST /api/v1/platform/release/recovery` (owner/admin, `ORG_MANAGE`).
Each scenario runs against a **fresh isolated temp store** — operator data is
never touched — and must prove the invariants:

- no duplicate execution
- no authority escalation
- no replay
- no data corruption

## Scenarios

| Scenario | Proof |
|---|---|
| `process_restart` | A `WAITING_APPROVAL` execution survives a full service restart over the same SQLite file; the attention queue still reports `APPROVAL_REQUIRED`; recoverable; no duplicate. |
| `restart_before_dispatch` | An execution with no recorded dispatch is safe-resume eligible; no replay risk. |
| `restart_after_dispatch_recorded` | An execution driven to `PAUSED` with `dispatch_started` is classified `DISPATCH_OUTCOME_UNCERTAIN`; a `RESUME` reconciliation is rejected with `DISPATCH_OUTCOME_UNCERTAIN` — automatic replay is forbidden; manual resolution only. |
| `binding_interruption` | A binding suspended while an execution is queued invalidates the stale context (`BINDING_SUSPENDED`); no dispatch under an invalid binding state. |

Overall is `PASS` only when every scenario passes; `FAIL` if any scenario fails;
`WARNING` if any is inconclusive.

Backend certification: `tests/test_m55_release.py::test_recovery_certification_all_scenarios_pass`.

## Limitations
Single-host SQLite guarantees only. No distributed consensus or exactly-once
execution is claimed. Database-interruption and worker-interruption are covered by
the restart/dispatch invariants on a single host; multi-host coordination is out
of scope.
