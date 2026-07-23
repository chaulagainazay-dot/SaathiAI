# M47.8 — PR Diff Review

**PR:** #2 · `origin/master...HEAD`  
**Scale:** 102 files · ~+19.1k / −1.3k lines · 23 commits  
**Review date:** 2026-07-23

## Categories reviewed

| Category | Files (representative) | Finding class |
|---|---|---|
| Shell | Shell.jsx, Sidebar, TopBar, StatusBar, Dock, MobileTabBar | NON_BLOCKING |
| Navigation | navigation.js, departments.js, CommandPalette | NON_BLOCKING |
| Home | page.jsx, attention.js, useAttentionHome | NON_BLOCKING |
| Approvals | approvals/page.jsx, approvals.js | NON_BLOCKING |
| Chat | ChatWorkspace.jsx | NON_BLOCKING |
| Copilot | CopilotPanel.jsx, ShellChromeContext | NON_BLOCKING |
| Command / Control | command/page.jsx (control retained outside PR new-routes) | ACCEPTED_LIMITATION |
| Business / Finance | business/page.jsx; finance retained | NON_BLOCKING |
| Studio | docs boundary; pages retained | ACCEPTED_LIMITATION |
| Monitoring / Settings | monitoring, settings, redirects for infra/me | NON_BLOCKING |
| Trading | trading/page.jsx advisory-only | NON_BLOCKING |
| Redirects | redirects.js, next.config.mjs | NON_BLOCKING |
| CORS | cors_policy.py, server.py middleware | NON_BLOCKING |
| Tests / harness | *.test.js, m47_4/m47_7 browser cert | NON_BLOCKING |
| Documentation | docs/ui-ux/**, docs/ui/** | NON_BLOCKING |
| Configuration | package.json, eslint, package-lock | NON_BLOCKING |

## Targeted checks

| Risk | Result | Class |
|---|---|---|
| Accidental deletions of required routes | Not observed; legacy routes retained | FALSE_POSITIVE risk cleared |
| Duplicate routes / redirect loops | Soft redirects only two sources; validators forbid loops | NON_BLOCKING |
| Dead imports | Not systematically ESLint-clean across whole monorepo; saathi-os lint passes | NON_BLOCKING |
| Hidden authority controls | Approvals use ConfirmDialog + server decide; trading has no order buttons | NON_BLOCKING |
| Unsafe CORS | Replaced `allow_methods=["*"]` / `allow_headers=["*"]` with bounded lists; no ACAO `*` | NON_BLOCKING |
| Hard-coded secrets | Secret scan on 102 PR files: **NONE** | NON_BLOCKING |
| Production URLs hard-coded as CORS allow | Dev defaults only local ports; prod fail-closed | NON_BLOCKING |
| Temporary debug / console spam | No systematic debug commits in scope review | NON_BLOCKING |
| Mock data as real / zero for unavailable | Approvals + attention aggregate honesty tests | NON_BLOCKING |
| Deep-link loss | Compatibility paths retained; soft redirects preserve query | NON_BLOCKING |
| Large generated files | package-lock.json + selected evidence JSON/PNG expected | ACCEPTED_LIMITATION |
| Test-only code in production runtime | Browser cert is scripts/, not imported by app | NON_BLOCKING |

## Findings detail

### BLOCKING

```text
none
```

### NON_BLOCKING

1. PR body was outdated (early draft scope only) — **will update description** in Phase 4.  
2. `package-lock.json` large churn from adding eslint/playwright tooling — expected.  
3. Selected M47.4 screenshots committed for evidence (small set); bulk screenshots gitignored.

### ACCEPTED_LIMITATION

1. Compatibility routes remain by design (chat/control/finance/studio-os).  
2. Live stream/Stop not product-blocking for draft exit.  
3. A11y not full WCAG.

### FALSE_POSITIVE

1. Trading page text contains “Withdrawal permission” — advisory copy, not a withdraw control (M47.7 harness corrected).

## Verdict

```text
DIFF_REVIEW = PASS
```
