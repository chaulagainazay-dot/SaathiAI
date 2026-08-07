# M56 Node & Cluster Health and Distributed Metrics

## Node health — `GET /cluster/node-health` (RUNTIME_READ)
Per node: status, heartbeat age, healthy flag (within heartbeat timeout), memory
RSS, CPU load estimate (best-effort, no OS-specific assumptions), worker count,
lease count, restart count, queue depth.

## Distributed metrics — `GET /cluster/metrics` (RUNTIME_READ)
Tenant-safe. Per node, per worker (status, lease count, workload, utilization),
per lease (active/total), per queue (active leases), per scheduler (paused), per
recovery (lease churn), execution ownership count, worker utilization, lease
churn, queue latency (0 on single-host inline).

No secrets, credentials, or paths. Values are bounded and tenant-scoped.
