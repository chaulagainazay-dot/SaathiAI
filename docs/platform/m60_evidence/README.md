# M60 Evidence

Bounded, test-only evidence for the M60 guided operator workflow milestone. No
credentials, tokens, keys, secret-bearing logs, or environment dumps.

- `m60_browser_cert.json` — production browser + axe cert report (schema
  `m60.browser_cert.v1`): hard/soft gates, per-page axe results, screenshot manifest.
- `screenshots/` — 17 PNGs (onboarding, onboarding_safety, mission_new,
  mission_scope, mission_created, mission_plan, approval_new, actions, notifications,
  evidence, saved_views, search, templates, workflows, reduced_motion,
  mobile_onboarding, mobile_mission_new).

## Route inventory (M60)
```
/platform/onboarding
/platform/missions/new          /platform/missions/[missionId]/plan
/platform/approvals/new
/platform/actions               /platform/notifications
/platform/evidence              /platform/saved-views
/platform/search                /platform/templates
/platform/workflows  /platform/workflows/new  /platform/workflows/[workflowId]
```

## Reproduce
```
cd saathi-os
npm test                 # 130 unit tests incl. lib/operator.test.js
npm run lint
npm run cert:m60:build   # production browser + a11y cert
npm run cert:m60         # dev regression
```

Known limitations: `docs/platform/M60_LIMITATIONS.md`.
