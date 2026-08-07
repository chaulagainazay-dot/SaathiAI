# M56 Worker Registry

Tracks execution workers (single-host today, multi-host ready). Advisory; workers
do not perform remote execution.

## Tracked per worker
worker id, node id, status (ACTIVE/PAUSED/DRAINING/RETIRED), runtime version,
capabilities, current workload, lease count, last heartbeat, last health check,
shutdown state.

## Operations (RUNTIME_OPERATE)
- `register` — `POST /cluster/workers/register` — add a worker under a node.
- `heartbeat` — `POST /cluster/workers/action {action:"heartbeat"}` — liveness +
  logical tick.
- `drain` — stop taking new leases; releases held leases for recovery.
- `pause` / `resume` — temporarily halt / resume assignment.
- `retire` — permanently remove; releases held leases.

The current process is always represented by `worker-local` under `node-local`
(`ensure_local`). No remote execution is performed.

## Safety
Registry mutations require `RUNTIME_OPERATE` (owner). Reads (topology/health) are
`RUNTIME_READ`. No secrets, credentials, or paths are exposed.
