# M54 Operational Runbooks

Actionable private-alpha runbooks. All commands are local; no production service
is involved. Backend uses the `.venv` Python; UI uses `saathi-os`.

## Startup and shutdown
**Prerequisites:** Python `.venv` with requirements, Node deps in `saathi-os`,
Playwright chromium installed.
1. Start BFF: `SAATHI_PLATFORM_DB=<path> .venv/bin/python -m uvicorn saathi.server:app --port 8765`.
2. Verify health: `GET /api/v1/platform/health` returns identity/rbac/gateway.
3. Start UI: `cd saathi-os && NEXT_PUBLIC_SAATHI_API=http://127.0.0.1:8765 npm run dev`.
4. Clean shutdown: stop UI, then BFF (SIGTERM). Failure cleanup: remove the
   isolated `SAATHI_PLATFORM_DB` temp file.

## Browser certification
- Seed + run: `cd saathi-os && npm run cert:m54` (dev) or `cert:m54:build`.
- Artifacts: `docs/platform/m54_evidence/m54_browser_cert.json` + `screenshots/`.
- Interpretation: exit 0 = all hard gates pass. Rerun after any UI change.

## Paused execution
1. Inspect `/runtime/executions/{id}` and `/runtime/executions/{id}/timeline`.
2. Determine whether dispatch was recorded (`dispatch_started`).
3. **No recorded dispatch** → allowed: `RESUME`, `CANCEL_BEFORE_DISPATCH`,
   `RESOLVE_FAILED`, `ATTACH_NOTE`, `MARK_REVIEWED`.
4. **Recorded dispatch** → forbidden: automatic resume/replay. Allowed only:
   `RESOLVE_FAILED`, `CONFIRM_TIMEOUT` (if eligible), `ATTACH_NOTE`,
   `MARK_REVIEWED`.
5. Escalate when external side effects may have occurred.

## Uncertain dispatch
Preserve evidence; never auto-replay; operator reviews timeline; resolve only via
an allowed terminal action; external verification is a manual placeholder; every
action is audited.

## Approval incidents
Expired / revoked / rejected / replay attempt / scope mismatch → the approval
fails closed; request a new approval via `REQUEST_NEW_APPROVAL`; approvals are
single-use.

## Binding incidents
Suspension, revocation, stale version, excessive authority, suspected compromise
→ suspend or revoke the binding; queued executions fail closed on stale context.
Revocation is irreversible. No production-credential workflow is introduced.

## Database recovery
Back up the private-alpha SQLite file (copy while stopped); integrity check
(`PRAGMA integrity_check`); restore rehearsal into a temp path; restart triggers
reconciliation of recoverable executions. Limitation: single-host only.

## Security incident containment
Revoke sessions (`/sessions/{id}/revoke`); suspend bindings; use owner safety to
disable execution; preserve audit evidence; confirm connectors remain dry-run and
trading remains disabled via `/runtime/diagnostics`.
