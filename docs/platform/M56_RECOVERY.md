# M56 Recovery Certification (Distributed)

`POST /cluster/recovery` (owner/admin). Each scenario runs against a **fresh
isolated temp platform** — operator data untouched — and must prove:
no replay, no duplicate execution, no authority escalation, single-owner lease.

| Scenario | Proof |
|---|---|
| worker_restart | Lease survives a coordinator restart over the same store; single owner preserved. |
| lease_expiration | An expired lease is recovered; execution re-eligible; not valid; no replay. |
| heartbeat_timeout | A stale-heartbeat worker's lease is recovered; no duplicate execution. |
| scheduler_restart | Scheduler pause/resume state is durable across restart; deterministic ordering. |
| worker_drain | Draining releases held leases; recoverable; no duplicate. |
| worker_retirement | Retiring releases leases; no escalation. |
| lease_reassignment | Transfer yields a single new owner; the stale owner is rejected on renew. |

Overall is `PASS` only when every scenario passes. Backend certification:
`tests/test_m56_cluster.py::test_recovery_certification_all_scenarios_pass`.

## Limitations
Single-host SQLite guarantees only. No distributed consensus or exactly-once
execution is claimed; the abstractions prepare for multi-host, they do not enable
it.
