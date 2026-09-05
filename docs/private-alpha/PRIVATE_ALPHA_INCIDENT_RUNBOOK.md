# Private Alpha — Incident Runbook

Every incident follows the same four moves: **contain, assess, remediate,
record.** Contain first. A private alpha has few users and no revenue at stake;
there is never a reason to leave a broken boundary running while you investigate.

Severity:

| | Meaning | First response |
| --- | --- | --- |
| **SEV1** | A safety boundary is broken: isolation, approval, credential, connectivity, execution, or public exposure | Stop the service now, then investigate |
| **SEV2** | Data or evidence integrity at risk: corruption, audit gaps, backup failure | Stop writes, back up, then investigate |
| **SEV3** | Degraded but bounded: performance, browser outage, repeated mission failures | Investigate while running |

---

## Universal first response

```bash
bin/saathi-local status
bin/saathi-alpha doctor              # includes a public-listener scan
.venv/bin/python -m saathi.ops storage
```

For SEV1 and SEV2, back up before you change anything:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from saathi.platform.private_alpha.backup_restore import create_system_backup, verify_system_backup
b = create_system_backup(dest_dir=Path("data/backups/system"), label="incident")
print(b["archive"], verify_system_backup(b["archive"]))
PY
```

---

## Authentication failure

**Symptoms** Testers cannot sign in; sign-in returns an error for known-good
credentials.

**Contain** None needed — failing closed is correct behaviour.

**Assess** Check whether login is disabled (`LOGIN_DISABLED`), whether membership
was revoked (`MEMBERSHIP_REVOKED`), or whether sessions are expiring immediately
(check the configured idle and absolute TTL).

**Do not** work around it by lowering the password policy, disabling the session
check, or minting a token by hand. A private alpha with weakened authentication
is worse than an unavailable one.

**Remediate** Re-issue an invitation, or have the owner restore membership.

---

## Authorization bypass — SEV1

**Symptoms** A viewer performed an operator action; an operator decided an
approval; a role gained authority it was not granted.

**Contain** `bin/saathi-local stop` immediately.

**Assess**

```bash
.venv/bin/python - <<'PY'
from saathi.platform.service import default_platform
p = default_platform()
for e in p.store.list_audit(limit=500):
    if e.get("event", "").startswith(("approval.", "runtime.")):
        print(e["at"], e["event"], e.get("user_id"), e.get("role"), e.get("outcome"))
PY
```

Identify every action taken under the wrong authority, and everything downstream
of it.

**Remediate** Fix the permission check. Roll back if the defect shipped in this
release. Revoke every session belonging to the affected user.

---

## Workspace or organization isolation concern — SEV1

**Symptoms** A tester saw data belonging to another workspace or organization.

**Contain** Stop the service. Do not let another request through.

**Assess** Reproduce with the isolation probes:

```bash
.venv/bin/python -c "from saathi.platform.private_alpha.journey import run_private_alpha_journey as j; r=j(write_evidence=False); print(r['stages']['rbac'])"
```

Confirm the four isolation refusals still hold: `PROJECT_ISOLATION`,
`WORKSPACE_ISOLATION`, `MEMBERSHIP_REVOKED`, `APPROVAL_ISOLATION`.

**Remediate** Fix, then re-run the journey before restarting. Tell every affected
tester exactly what was exposed. Do not soften this in the message.

---

## Approval bypass — SEV1

**Symptoms** A mutating action ran without a human decision; an approval was
reused; the assistant approved something.

**Contain** Stop the service.

**Assess** For every execution in the window, confirm there is a matching
`approval.decided` event with a human `decided_by`, and that the approval was
consumed exactly once. Concurrent decisions must show exactly one winner
(see `tests/test_m341_soak_safety.py`).

**Remediate** Fix the atomicity or the check. Never restart with approvals
bypassed "temporarily".

---

## Mission corruption

**Symptoms** A mission is stuck in a non-terminal state, or its recorded state
does not match its evidence.

**Contain** Cancel the mission. Do not retry it blindly — retrying a corrupt
mission can duplicate its effects.

**Assess** Compare the mission record, the execution records and the audit trail.
Determine whether the effect happened once, more than once, or not at all.

**Remediate** Reconcile the execution, then let the tester re-create the mission.

---

## Data loss — SEV2

**Contain** Stop writes immediately: `bin/saathi-local stop`.

**Assess**

```bash
sqlite3 data/platform/platform.db "PRAGMA integrity_check;"
.venv/bin/python -m saathi.ops db
```

**Remediate** Dry-run a restore first, always:

```bash
.venv/bin/python -c "from saathi.platform.private_alpha.backup_restore import dry_run_restore; print(dry_run_restore('<archive>'))"
```

Only restore after the dry run is clean. Tell testers precisely which window of
work was lost.

---

## Audit failure — SEV2

**Symptoms** Executions occurred but are absent from the audit trail, or audit
records were deleted.

This is severe even when nothing else broke: without the audit trail, no other
claim in this system can be verified.

**Contain** Stop the service. Back up the database as forensic evidence before
any repair.

**Assess** Compare execution records against audit events for the same window.

**Remediate** Fix the write path. Treat the gap as permanent — do not
reconstruct audit entries after the fact, and never backfill invented events.

---

## Backup failure — SEV2

**Symptoms** `create_system_backup` fails, or `verify_system_backup` reports a
checksum mismatch.

**Assess** Check disk headroom first (`bin/saathi-alpha prepare`), then archive
integrity. A corrupted backup must be detected, not used — the M341 recovery
scenario proves detection works.

**Remediate** Free disk, re-take the backup, verify it, and only then discard the
bad archive. Never delete the last known-good backup before the new one verifies.

---

## Performance degradation — SEV3

**Assess** Compare against the M341 soak baseline: p50/p95/p99 latency, error
rate, memory growth, open file descriptors, database and log growth.

**Common causes** unbounded log growth, a mission retry loop, a queue that is
never drained, or an 8 GB host under memory pressure.

**Remediate** Rotate logs, cancel the runaway mission, reduce concurrency. If
memory growth is monotonic across the soak window, treat it as a leak and fix it
rather than restarting on a schedule.

---

## Browser outage — SEV3

**Symptoms** The UI does not load; certification fails to reach the app.

**Assess** Is the backend healthy (`curl` the health endpoint)? Is the frontend
process running? Is it a CORS rejection between `localhost:3000` and
`127.0.0.1:8765`?

**Remediate** Restart the frontend. Do not widen CORS to `*` — that converts a
UI outage into an exposure incident.

---

## Unexpected network request — SEV1

**Symptoms** Any outbound request to a host that is not localhost.

**Contain** Stop the service, and disconnect the machine from the network if the
destination is unknown.

**Assess** Identify the exact destination, the code path, and whether anything
left the machine. Private alpha makes no external calls; there is no benign
explanation to look for first.

**Remediate** Remove the call. Re-run the network-isolation scan before
restarting. Tell the owner what, if anything, was transmitted.

---

## Credential-like value detected — SEV1

**Symptoms** The secret scan flags credential-bearing material, or a tester
pastes a real key into the product.

**Contain** Stop the service. Do not commit or push.

**Assess** Determine whether the value is real key material or a non-material
marker. The release gate distinguishes these: a PEM header with no key body is a
marker, a PEM header with a base64 body is a credential.

**Remediate** If real: treat it as compromised, rotate it at the source, purge
it from the working tree, and never assume deletion is sufficient. If a tester
supplied it, tell them to rotate it — private alpha never asks for credentials,
so any credential they entered went somewhere it should not have.

---

## Provider connectivity attempt — SEV1

**Symptoms** Code or configuration attempts to reach a broker, exchange or paid
provider.

**Contain** Stop the service.

**Assess** Confirm every authority lock is still `false`. Identify what tried to
connect and whether it succeeded.

**Remediate** Remove the capability. The private-alpha boundary is not a runtime
setting — a connectivity path that exists but is disabled is still a defect.

---

## Execution-authority violation — SEV1

**Symptoms** An order was submitted, modified or cancelled; paper or live
execution was enabled; automated investment authority was exercised.

**Contain** Stop the service immediately.

**Assess** Determine exactly what was submitted and where. Preserve all evidence
before any repair.

**Remediate** This is the most serious failure this system can have. Do not
restart until the path is removed and proven absent, the authority locks are
verified `false`, and the owner has personally signed off.

---

## Tester support

See [`PRIVATE_ALPHA_TESTER_GUIDE.md`](PRIVATE_ALPHA_TESTER_GUIDE.md) for the
reporting format testers use, what to collect, and the redaction rules.

## Escalation

1. Operator on duty — contains and assesses.
2. Owner — decides on rollback, tester communication, and any SEV1.
3. Nobody else. A private alpha has no on-call rota and no external escalation
   path; do not invent one under pressure.

## After every incident

Record: what happened, when, severity, which boundary was involved, what was
contained and when, what data was affected, what was communicated to testers, the
root cause, the fix, and the test that now prevents recurrence. An incident
without a new test is an incident that will happen again.
