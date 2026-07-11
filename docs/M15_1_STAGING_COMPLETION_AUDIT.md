# M15.1 Staging Completion Audit

## Starting state
Commit `46db7cb` (M15). 11 connectors / 28 tools, ExecutionEngine boundary,
gateway provenance, approval binding, idempotency, redaction, health, webhook,
sync, MCP, Spec Kit governance. Full suite 1204 passed. Verdict DEVELOPMENT READY.

## Completed M15 foundations (reused, not rebuilt)
models, catalog, registry, credentials, adapters, store, execution, health,
webhook, sync, mcp, specs governance.

## Gaps found (and how M15.1 closes them)
| Gap | Evidence in repo | M15.1 action |
|-----|------------------|--------------|
| No authenticated REST API | only read-only CLI existed | `saathi/connectors/platform/api.py` @ `/api/v1/connectors/*`, owner-scoped, mounted in `server.py` |
| Legacy connector API/UI on old path | `server.py` `@app /api/v1/connectors/{providers,accounts,execute}` + `saathi/connectors/` + `adapters/telegram` (real Bot API) | migration ledger `migration.py`; new API is canonical; legacy kept as shim |
| Direct provider calls | `connectors/adapters/telegram.py` uses real Bot API | recorded transitional-exception; direct-call scanner guards the platform package |
| In-process resolver too weak for staging | `resolve_secret` only checked status | `resolve_for_account` validates owner/connector/scope before lookup, typed errors |
| UI on legacy endpoints | `app/connectors/page.jsx` hit `/connectors/providers` | rewritten on platform API, honest integration-status states |
| No Chat/Agent/CEO/Voice funnel | each could call providers | `integration.py` single funnel; CEO evidence tier keeps failures unavailable |
| No observability | — | `store.metrics()` over genuine sample |

## Direct-call bypass scan
`scan_direct_calls()` over `saathi/connectors/platform` → 0 violations.

## Connectors suitable for live verification (this environment)
- `local_fs`, `local_git` → LIVE TESTED (genuinely executed).
- GitHub/browser/sqlite → DETERMINISTIC ADAPTER TESTED (no token).
- gmail/gcal/gcontacts/telegram/studio_publish → ENVIRONMENT BLOCKED (no creds).
- deploy → CONTRACT READY.

## Credential / auth / browser gaps (honest)
- Cloud live-mutation: blocked (no credentials). Contracts + deterministic paths done.
- Interactive browser smoke: frontend build passes (34/34 pages, `/connectors`
  compiled); a running authenticated server session is not available here →
  browser smoke ENVIRONMENT BLOCKED, not claimed.

## Staging exit criteria (met vs blocked)
Met: authenticated API + isolation + redaction; approval-binding via API;
credential hardening; UI on real API + build; local live execution; legacy
migration ledger + scanner; Chat/Agent/CEO/Voice funnel; failure-path + backup
tests; convergence 18/18. Blocked: cloud live-mutation, interactive browser smoke.

## Note on gstack
gstack is an optional external Claude/Codex development workflow and review
toolkit. It is not a Spec Kit implementation, connector runtime, or SaathiOS
production dependency.
