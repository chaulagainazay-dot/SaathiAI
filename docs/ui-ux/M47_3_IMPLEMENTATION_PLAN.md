# M47.3 — Implementation Plan

**Date:** 2026-07-22  
**Baseline HEAD:** `2c9f8c5c8120311cc549b28b951610fe39b3a35d`  
**PR:** #2 draft

## 1. Files to modify

- `saathi-os/app/page.jsx` — attention-first Home
- `saathi-os/app/approvals/page.jsx` — multi-source inbox
- `saathi-os/app/command/page.jsx` — primitives + less inline
- `saathi-os/app/missions/page.jsx` — M1 primitives
- `saathi-os/app/projects/page.jsx` — list-view primitives (bounded)
- `saathi-os/app/monitoring/page.jsx` — class-based layout
- `saathi-os/components/ui.jsx` — ConfirmDialog, DestructiveDialog
- `saathi-os/lib/api.js` — `controlApprovals` read export
- `saathi-os/app/globals.css` — home/attention/approval layout classes
- `saathi-os/package.json` — lint script + eslint deps if needed

## 2. Files to create

- `saathi-os/lib/attention.js` — normalize + aggregate
- `saathi-os/lib/approvals.js` — normalize multi-source
- `saathi-os/lib/attention.test.js`, `approvals.test.js`, `dialogs` safety tests
- `docs/ui-ux/M47_3_METRICS_BASELINE.md`
- `docs/ui-ux/M47_3_IMPLEMENTATION_REPORT.md`
- `docs/ui-ux/M47_3_VALIDATION_REPORT.md`
- `docs/ui-ux/M47_3_LIGHT_THEME_CERT.md`
- eslint config (flat or `.eslintrc.json`) if install succeeds

## 3. APIs / data sources (reuse)

| Source | API | Use |
|---|---|---|
| Control attention | `controlAttention()` → `/api/v1/control/attention` | primary attention spine |
| Control overview | `controlOverview()` | system posture, nested attention |
| Control approvals cell | `/api/v1/control/approvals` | aggregated pending cell |
| Connector approvals | `platformPendingApprovals()` | approval list |
| Missions | `fetchMissions()` | blocked/failed/status attention + continue |
| Projects | `fetchProjects()` | continue working |
| Evidence | `fetchEvidence({ limit })` + stats | recent evidence |
| Infra health | `fetchInfraHealth()` | degraded systems |
| Learning recommendations | `fetchRecommendations({ status: "pending" })` | approval-like queue |
| CEO briefing | `fetchCeoHome()` | optional secondary context only if real |

## 4. Approval sources found

- **Connected path:** connector pending (`platformPendingApprovals`)
- **Read aggregation:** control center `pending_approvals` cell
- **Recommendations:** learning recommendations (pending) — decision via existing `decideRecommendation` only with ConfirmDialog
- **Mission proposals:** no list API of all pending proposals — **not_integrated** (deep-link via mission)
- **Trading / deploy / finance:** **not_integrated**
- **Connector decide:** `platformDecideApproval` exists — use only with ConfirmDialog + server auth; optional opt-in

## 5. Attention categories

From control `kind` + derived: `approval_required`, `failed_run`, `degraded_system`, `security_attention`, `connector_attention`, `blocked_mission`, `evidence_ready`, `informational`, `business_attention`

## 6. Unavailable / not integrated

- Trading approvals, deploy approvals, unified mission-proposal inbox
- Fabricated executive revenue tiles (old Home) will not be reintroduced as “attention”

## 7. Pages for primitive adoption

`/` · `/approvals` · `/command` · `/missions` · `/projects` (list) · `/monitoring`

## 8. Style reduction

CSS classes for home/attention/approval grids; strip static inline from migrated pages; keep dynamic only.

## 9. Light-theme risks

Legacy glass/hex on unmigrated pages; shell tokens already theme-mapped; certify migrated set.

## 10. Lint

`eslint` + `eslint-config-next` if installable; script `lint` non-interactive; bound to saathi-os.

## 11. Validation

```bash
cd saathi-os && npm test && npm run build && npm run lint
# count style={{ ; browser :3100
```

## 12. Stop conditions

No new auth model; no trading execution; no redirects; no fabricate; no force-push/merge.
