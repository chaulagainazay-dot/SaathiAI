# Twenty temporary-runtime backup, restore, and removal plan

Status: design complete for review; not executed or approved.

| Phase | Required operation | Required evidence | Accountable role |
| --- | --- | --- | --- |
| `CREATE` | create approved private host, encrypted volume, firewall, private DNS | approval reference, host class, encrypted-volume and firewall fingerprints | `RUNTIME_OPERATOR` |
| `CONFIGURE` | apply pinned images/config and synthetic-only settings | digest list, redacted config hash, network-policy result | `RUNTIME_OPERATOR` + `SECURITY_REVIEWER` |
| `VALIDATE` | run approved read-only tests and resource sampling | test IDs, schemas, request fingerprints, denial evidence | `EVIDENCE_REVIEWER` |
| `BACKUP` | quiesce writes, export PostgreSQL plus required storage/config metadata | encrypted backup checksum, size, tool/version, timestamp | `RUNTIME_OPERATOR` |
| `RESTART` | restart pinned runtime without configuration drift | before/after health, digest/config equality, persistence checksums | `RUNTIME_OPERATOR` |
| `RESTORE` | restore into a separate disposable target | restore log, integrity checks, synthetic record checksums | `RUNTIME_OPERATOR` + `EVIDENCE_REVIEWER` |
| `SHUT_DOWN` | stop server, worker, database, cache, and ingress | process/container absence, closed ports, stopped billing meter | `RUNTIME_OPERATOR` |
| `DELETE` | revoke credentials; delete host, volumes, backups, snapshots, firewall, DNS, logs | provider deletion receipts/IDs with secrets redacted | `RUNTIME_OPERATOR` + `COST_OWNER` |
| `VERIFY_REMOVAL` | independently confirm no billable or reachable resource remains | inventory zero-result, DNS/port checks, final cost status | `SECURITY_REVIEWER` + `EVIDENCE_REVIEWER` |

## Backup requirements

- PostgreSQL logical backup in an encrypted archive; include schema and synthetic data.
- Record database/version, migration state, command/tool version, timestamp, size,
  SHA-256 checksum, and synthetic counts.
- Include required local-storage objects and a redacted configuration manifest;
  never include raw API keys in evidence.
- Store only in an owner-approved encrypted location with access limited to the
  runtime operator and evidence reviewer.
- Default retention is until successful restore plus 24 hours, then deletion;
  any longer retention needs explicit owner approval.
- Restore only into a new disposable target, never over the source runtime.

## Removal gate

Owner approval must name an operator and a concrete removal deadline. On abort,
revoke the API key first, block network paths, snapshot only if policy permits,
stop billable compute, then perform deletion and independent verification. Removal
is not proven by this plan; it becomes proven only through future captured evidence.
