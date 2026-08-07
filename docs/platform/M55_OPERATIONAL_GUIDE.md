# M55 Operational Guide

How a private-alpha operator runs and observes the release candidate.

## Surfaces
- **Platform console** (`/platform`) — sign-in, bindings, governed execution,
  approvals, attention, reconciliation, diagnostics, evidence export, dry-run
  retention (M50–M54).
- **Operator console** (`/platform/ops`) — read-only operations dashboard:
  Platform Health, Metrics, Release Readiness, Recovery Certification, Backup
  Validation, Security Status.
- **Release gate CLI** — `python -m saathi.platform.release_check [--json]`.

## Daily operation
1. Sign in on `/platform`; open `/platform/ops`.
2. Review Platform Health (runtime, uptime, latency, queue, sessions, tenants).
3. Review Metrics (executions, approvals, exports, attention reasons, errors).
4. Run **Release validation** — expect `READY_WITH_LIMITATIONS` (production
   intentionally disabled). Any `FAIL` means investigate before considering a
   future deployment.
5. Run **Recovery certification** — expect `PASS` on all scenarios.
6. Run **Backup validation** — expect `SIMULATION_ONLY`, integrity `ok`.
7. Confirm Security Status: connectors dry-run, financial/trading disabled,
   Trading Guardian advisory-only, production not authorized.

## API reference (owner/admin unless noted)
| Endpoint | Method | Auth |
|---|---|---|
| `/release/health` | GET | RUNTIME_READ |
| `/release/metrics` | GET | RUNTIME_READ |
| `/release/validate` | POST | ORG_MANAGE |
| `/release/backup` | POST | ORG_MANAGE |
| `/release/recovery` | POST | ORG_MANAGE |

## Incident handling
Follow `docs/platform/M54_RUNBOOKS.md` for paused executions, uncertain dispatch,
approval/binding incidents, database recovery, and security containment. The
operator console surfaces the signals; the runbooks give the actions.

## Boundary
Everything here is advisory and read-only except already-approved operations. No
deployment, no production authorization, no connector mutation, no financial or
trading execution.
