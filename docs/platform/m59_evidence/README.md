# M59 Evidence

Bounded, test-only evidence for the M59 spatial workspace milestone. Contains no
credentials, tokens, private keys, secret-bearing logs, environment dumps, or build
artifacts.

## Contents

- `m59_browser_cert.json` — production-build browser + accessibility certification
  report (schema `m59.browser_cert.v1`): hard/soft gates, per-page axe results,
  browser-error counts, screenshot manifest. Verdict: **PASS** (mode=build).
- `screenshots/` — 15 PNGs captured during certification:
  - Desktop: `platform`, `ops`, `missions`, `mission_detail`, `agents`,
    `agent_detail`, `approvals`, `approval_detail`, `attention`,
    `command_palette`, `context_drawer`, `reduced_motion`.
  - Mobile (390×844): `mobile_missions`, `mobile_approvals`, `mobile_attention`.

## Route inventory (M59)

```
/platform/missions              /platform/missions/[missionId]
/platform/agents                /platform/agents/[agentId]
/platform/approvals             /platform/approvals/[approvalId]
/platform/attention             /platform/attention/[attentionId]
/platform          (M58, retained)   /platform/ops     (M58, retained)
```

## Reproduce

```
cd saathi-os
npm test                    # 112 unit tests incl. lib/workspace.test.js
npm run lint
npm run cert:m59:build      # production browser + a11y cert (this report)
npm run cert:m59            # dev-mode regression (same harness)
```

## Known limitations

See `docs/platform/M59_LIMITATIONS.md`.
