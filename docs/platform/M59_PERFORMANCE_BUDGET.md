# M59 — Performance Budgets (Workstream 10)

Verdict: **LOCAL_PERFORMANCE_BUDGETS_PASSED** ·
**REAL_USER_CORE_WEB_VITALS_NOT_YET_AVAILABLE**

## Budgets and results

| Budget | Result |
|---|---|
| No unbounded animation loops | PASS — all animation is finite CSS (particle drift, pulse halo, core breathe); reduced-motion disables it |
| No unbounded particles | PASS — particle field is a static CSS gradient, not spawned nodes; not rendered under reduced motion |
| No route-level video backgrounds | PASS — none |
| No major memory growth across navigation | PASS — repeated route navigation in the cert (list ↔ detail ↔ mobile ↔ reduced-motion contexts) produced no page errors or leaks; contexts are torn down cleanly |
| No hydration mismatch | PASS — 0 hydration errors on M59 routes (cert) |
| No blocking synchronous large-data layout | PASS — lists cap palette records at 20/type; data normalized with pure functions |
| No oversized initial JS increase | PASS — see route sizes below |

## Production route JS (from `next build`)

| Route | Route JS | First-load JS |
|---|---|---|
| /platform/missions | 2.87 kB | 122 kB |
| /platform/missions/[missionId] | 2.87 kB | 122 kB |
| /platform/agents | 3.34 kB | 123 kB |
| /platform/agents/[agentId] | 2.47 kB | 122 kB |
| /platform/approvals | 3.47 kB | 123 kB |
| /platform/approvals/[approvalId] | 2.92 kB | 122 kB |
| /platform/attention | 2.82 kB | 122 kB |
| /platform/attention/[attentionId] | 2.90 kB | 122 kB |

All eight new routes sit **below** the existing `/platform/ops` (6.66 kB / 163 kB)
and `/platform` (8.02 kB / 164 kB) baselines — the shared shell keeps per-route
payloads small.

## Interaction latency (observed in cert)

Command palette and context drawer open on a single React state toggle (no network,
no heavy compute) and were interacted with immediately after render in every cert
run without timeouts.

## Limitation

These are **local lab** measurements (build output + headless harness). They are
**not** real-user Core Web Vitals; field CWV are not yet available.
