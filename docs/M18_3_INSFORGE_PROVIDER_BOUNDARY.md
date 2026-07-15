# M18.3 — InsForge Provider Boundary (Read-Only Pilot)

**Status:** `PILOT_APPROVED_READ_ONLY`
**Date:** 2026-07-15
**Provider:** [InsForge/InsForge](https://github.com/InsForge/InsForge) (Apache-2.0)
**Adapter:** `saathi/providers/insforge/`
**Disable:** `SAATHI_INSFORGE_ENABLED` unset/false (default)

---

## Ownership boundary

### SaathiOS owns (control plane — never delegated)

* Intent, planning, mission lifecycle
* Permissions, approvals, ExecutionGateway policy
* Audit, Evidence, SecurityStore
* Model Router
* Memory (including codebase memory M18.1/M18.2)
* Scheduler / mission occurrences
* Event bus
* Trading Guardian
* Rollback decisions
* SES governance

### InsForge may own (product-backend data plane only)

* PostgreSQL application data for a **product** backend
* Product end-user authentication (not SaathiOS operator root identity)
* Product file storage buckets
* Product edge functions (later write milestones only)
* Backend metadata and runtime logs (read in this pilot)
* Product site deployment — **later milestones only**

### Explicitly prohibited roles for InsForge

| Prohibition | Reason |
|-------------|--------|
| Raw InsForge MCP for unrestricted agents | High-privilege admin surface |
| InsForge Memory as SaathiOS memory | Dual memory authority |
| InsForge schedules as SaathiOS scheduling | Dual orchestration |
| InsForge model gateway replacing Model Router | AP-02 / control plane |
| InsForge auth as SaathiOS root identity | Operator vs product auth split |
| Trades / exchange credentials | Trading Guardian sole authority |
| Writes outside ExecutionGateway + approvals | SES + safety harness |

---

## Read-only pilot allowlist

All calls: **HTTP GET only**, path must match exact allowlist, base URL origin-only.

| Operation | Path | Input | Output (typed) | Timeout | Error mapping | Audit event | Secrets | Verification |
|-----------|------|-------|----------------|---------|---------------|-------------|---------|--------------|
| `health` | `/api/health` | none | status, version, service, reachable | config (default 10s) | auth/timeout/unavailable | `insforge.health` | optional API key header | status field present |
| `provider_metadata` | `/api/metadata` | none | sanitized metadata keys | same | same | `insforge.provider_metadata` | optional | object payload |
| `list_schema_objects` | `/api/database/tables` | none | table name list + count | same | same | `insforge.list_schema_objects` | optional | list bounded |
| `list_edge_functions` | `/api/functions` | none | slug/status list | same | same | `insforge.list_edge_functions` | optional | list bounded |
| `list_storage_buckets` | `/api/storage/buckets` | none | bucket name list | same | same | `insforge.list_storage_buckets` | optional | list bounded |
| `read_sanitized_logs` | `/api/logs` | limit ≤ max | redacted log records | same | 404 → unsupported | `insforge.read_sanitized_logs` | optional | secrets redacted |

Env:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SAATHI_INSFORGE_ENABLED` | false | Master enable |
| `SAATHI_INSFORGE_BASE_URL` | empty | Origin only (`https://host:port`) |
| `SAATHI_INSFORGE_API_KEY` | empty | Optional read credential |
| `SAATHI_INSFORGE_TIMEOUT_SEC` | 10 | Bounded ≤ 30 |
| `SAATHI_INSFORGE_MAX_RESPONSE_BYTES` | 512000 | Response cap |
| `SAATHI_INSFORGE_MAX_LOG_RECORDS` | 50 | Log page size |
| `SAATHI_INSFORGE_TLS_VERIFY` | true | TLS verify |
| `SAATHI_INSFORGE_ALLOW_LOOPBACK` | false | Dev loopback/private hosts |

---

## Explicit denylist (unreachable in pilot)

Migrations · SQL execution · table create/delete · storage upload/delete · auth mutations · user create/delete · function deploy/delete · site deploy · secrets create/read-value · schedules · InsForge Memory · model gateway completions · payments · compute · unrestricted MCP · any HTTP method other than GET · arbitrary paths.

---

## Trading Guardian

InsForge is **unengaged** for trading. No exchange keys may be stored in InsForge via this pilot. Regression tests ban trading symbols in the adapter package and reject `place_order` / trade-like invoke names.

---

## Deployment recommendation

Prefer **cloud or remote** InsForge for pilots. Full local Docker on 8 GB Apple Silicon is not the default (see prior evaluation). This milestone requires **no live InsForge** for tests (httpx MockTransport).

---

## Rollback / disable

```bash
unset SAATHI_INSFORGE_ENABLED
# or
export SAATHI_INSFORGE_ENABLED=0
```

Remove or ignore `saathi/providers/insforge/` on revert of the M18.3 commit.


---

## M18.4 extension — governed migration write

Status upgraded to **`PILOT_APPROVED_GOVERNED_MIGRATION_WRITE`**.

* Structured ops only (`create_table`, `add_column`, `create_index`)
* Requires `SAATHI_INSFORGE_WRITES_ENABLED=1` **and** valid fingerprint-bound approval
* Execution only via `MigrationService` → ExecutionGateway
* See `docs/M18_4_INSFORGE_MIGRATION_WRITE_PILOT.md`
