# M56 Lease Coordination

Advisory single-owner ownership of executions. Prevents two workers from claiming
the same execution — **no duplicate execution / no duplicate ownership**. Leases
never execute anything; `ExecutionGateway` remains the sole registered-tool
execution authority.

## Lifecycle (RUNTIME_OPERATE unless noted)
- `acquire` — `POST /cluster/leases/acquire`. Fails closed (`LEASE_ALREADY_HELD`)
  if an active lease is held by another worker.
- `renew` — extends TTL; only the owner may renew (`LEASE_OWNER_MISMATCH` else).
- `transfer` — reassign to a new single owner; stale owner can no longer renew.
- `verify` — `GET /cluster/leases/verify` (RUNTIME_READ), tenant-scoped.
- `recover` — `POST /cluster/leases/recover` — expire leases whose owner is
  retired or whose heartbeat is stale, making the execution re-eligible for a
  fresh single-owner lease. Never replays or duplicates execution.
- audit — every acquire/renew/transfer/recover/deny emits an audit event.

## Guarantees
At most one active lease per execution. Leases are tenant-scoped
(org/workspace); cross-tenant verify/acquire fail closed. Lease state is
config-persisted, so ownership survives a process restart.
