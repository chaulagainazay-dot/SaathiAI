# M48.3 — Lease and Heartbeat

- `acquire_lease(rid, owner, lease_sec)` — exclusive until expiry
- `heartbeat(rid, owner)` — renews lease
- `release_lease(rid, owner)`
- Terminal / cancelled runs cannot acquire leases
- Concurrent second owner denied while lease valid
- Orchestrator.run acquires lease for wall-clock execution
