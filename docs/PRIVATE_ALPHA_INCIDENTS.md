**Production authorized: false.** Local-only private alpha.

# Private Alpha Incident Playbooks

Playbooks are shipped in `saathi.platform.private_alpha.incidents`.

```bash
bin/saathi-alpha playbooks
```

Each playbook includes: detection, severity, containment, diagnosis, safe
remediation, rollback, evidence collection, escalation boundary.

Covered incidents include backend/frontend start failures, port conflicts, stale
processes, database locked, migration/backup/restore failure, automation stuck,
worker lease stale, browser open failure, disk/memory pressure, corrupt config,
session failure, approval backlog, unexpected public listener, provider
unavailable.

**Escalation boundary:** private-alpha owner only — not a public ops team.
