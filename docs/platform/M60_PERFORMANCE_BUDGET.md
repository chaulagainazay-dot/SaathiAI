# M60 — Performance Budgets

Verdict: **LOCAL_WORKFLOW_PERFORMANCE_BUDGETS_PASSED** ·
**REAL_USER_CORE_WEB_VITALS_NOT_YET_AVAILABLE**

Route JS (production build) — every M60 route is small and shares the M59 shell:

| Route | Route JS | First-load |
|---|---|---|
| /platform/onboarding | 4.31 kB | 130 kB |
| /platform/missions/new | 4.95 kB | 130 kB |
| /platform/missions/[missionId]/plan | 4.61 kB | 130 kB |
| /platform/approvals/new | 4.04 kB | 129 kB |
| /platform/actions | 2.03 kB | 127 kB |
| /platform/notifications | 1.91 kB | 127 kB |
| /platform/evidence | 2.22 kB | 128 kB |
| /platform/saved-views | 2.42 kB | 128 kB |
| /platform/search | 1.97 kB | 127 kB |
| /platform/templates | 1.54 kB | 127 kB |
| /platform/workflows | 1.00 kB | 126 kB |
| /platform/workflows/[workflowId] | 3.38 kB | 129 kB |
| /platform/workflows/new | 0.83 kB | 126 kB |

Budgets: no unbounded animation loops / particles / video; no unbounded state,
notification, or evidence lists (derived from bounded server data); no hydration
mismatch (cert: 0); no repeated full-dataset fetch per wizard step (single shared
`usePlatformData` load + targeted fetches); no memory growth observed across repeated
route navigation in the cert. Draft state is local and bounded.

Limitation: local lab measurements only; not real-user Core Web Vitals.
