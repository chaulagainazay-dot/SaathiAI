# SaathiOS Private Alpha — Database Retention and Growth Policy

**Status:** policy authored, tooling **not** implemented, **no data deleted**.
**Measured at:** `6b55013`, 2026-08-02.

Retention is a governance decision, not a cleanup script. This document decides *what may be
deleted and by whose authority* before any tool exists to delete it.

---

## 1. Measured position

The mission brief states a prior soak showed substantial database growth. **That premise is not
reproduced at current scale.**

| Measure | Value |
|---|---|
| `data/` total | 7.3 MB |
| `platform.db` | 1.17 MB, 79 tables, **642 rows** |
| Largest DB | `application_harness_runs/ledger.db`, 1.23 MB |
| Log directory | absent — no unbounded log growth |

Row concentration in `platform.db`:

| Table | Rows | Share |
|---|---:|---:|
| `audit_events` | 428 | 67% |
| `sessions` | 73 | 11% |
| `hcg_records` | 26 | 4% |
| `projects` | 20 | 3% |
| `platform_executions` | 16 | 2% |
| `invitations` | 16 | 2% |
| `approvals` | 12 | 2% |
| `missions` | 11 | 2% |
| everything else | 40 | 6% |

`audit_events` + `sessions` = **78% of all rows**. Both grow monotonically with use. Neither is
presently large. Governance is warranted as prevention, not as remediation.

## 2. Classification

| Data type | Class | Rationale |
|---|---|---|
| `audit_events` | **retain permanently** | Security and approval evidence. Deleting audit history destroys the ability to answer "who authorised this". Compaction only, never deletion. |
| `approvals` | **retain permanently** | Authority decisions. Permanent record. |
| `credentials`, `users`, `memberships`, `workspaces` | **retain permanently** | Identity backbone. |
| `sessions` (expired or revoked) | **retain fixed days — 30** | No forensic value past a month; the token hash is dead. **Highest-value reclaim with zero authority impact.** |
| `sessions` (active) | **never delete** | Deleting an active session signs a real user out mid-work. |
| `platform_executions` | **retain for alpha duration** | Needed to interpret mission history while alpha runs. |
| `missions`, `projects` | **retain for alpha duration** | User-created content. Deleting is a product decision, not maintenance. |
| `notifications` | **retain latest N — 500** | Transient. Old notifications have no evidentiary role. |
| `rate_limits` | **safe to delete when expired** | Purely operational, self-regenerating. |
| Evidence artefacts under `docs/evidence/**` | **protected — never auto-delete** | Certification evidence. Deletion would invalidate prior milestones. |
| Browser certification history | **archive** | Compress older runs, keep the latest per milestone. |
| `knowledge_index.db` | **rebuildable — safe to compact** | Derived index, reconstructable from source. |
| `idempotency.db` | **retain fixed days — 7** | Exists to prevent duplicate execution inside a short window. |
| Replay and snapshot data | **owner decision required** | Trading Guardian data; owner must classify before any tooling touches it. |
| `application_harness_runs/ledger.db` | **owner decision required** | Largest single database; contents not classified in this mission. |

## 3. Required properties before any tooling ships

Retention tooling must not be built until every one of these is satisfied:

1. **Bounded** — operates only on the classes above; no wildcard deletes.
2. **Archive before delete** — write the archive, verify it, *then* remove.
3. **Dry-run default** — the tool reports what it *would* do and changes nothing unless explicitly confirmed.
4. **Size estimation** — reports reclaimed bytes before and after.
5. **Owner approval** — deletion requires a human decision; no schedule may delete unattended during alpha.
6. **Protected evidence** — `docs/evidence/**` and audit tables are structurally excluded, not merely skipped by convention.
7. **No active-record deletion** — active sessions, running missions and pending approvals are never eligible.
8. **Audited** — every cleanup writes its own `audit_event`.
9. **Recovery tested** — a restore from archive is proven *before* the first real deletion.

## 4. What was deliberately NOT done

- **No data was deleted.** Not one row.
- **No retention tooling was implemented.** Building a deletion tool against a 7.3 MB dataset with
  no measured pressure would add a destructive capability to earn nothing.
- **No automatic schedule was created.**

The 73 expired sessions are the obvious first candidate and remain untouched pending owner
approval and a tested archive path.

## 5. Recommendation

1. Owner classifies `application_harness_runs/ledger.db` and replay/snapshot data (the two
   `owner decision required` rows).
2. Implement the expired-session reaper **first** — smallest blast radius, clearest rule, zero
   authority impact — with dry-run, archive and audit.
3. Re-measure after 30 days of real alpha use. Extend tooling only if growth is then material.
4. Keep `audit_events` permanent regardless of size. It is the evidence base for every approval
   claim SaathiOS makes.
