# M47.8 — Owner Review Plan

**Date:** 2026-07-23  
**Branch:** `milestone/saathios-ui-ux`  
**Starting HEAD:** `7dfd74de00241ae0fb05f99f36b3909ff16f9120`  
**PR:** #2 · base `master`  
**Authorization:** `REVIEW_PR2_FOR_DRAFT_EXIT`  
**Not authorized:** merge · deploy · delete branch · tag · production change

## PR purpose

Establish the SaathiOS UI/UX foundation stack: shared design tokens and primitives, grouped shell navigation, attention-first Home, multi-source Approval Inbox, soft redirects for two ready legacy routes, bounded BFF CORS, shared Chat/Copilot transport, and advisory-only Trading Guardian surface — with full browser re-certification (M47.7).

## Architecture introduced

| Layer | Content |
|---|---|
| Design system | Tokens in `globals.css`, primitives in `components/ui.jsx` |
| Shell | Sidebar, TopBar, StatusBar, Copilot panel, command palette, mobile tabs |
| Navigation | `lib/navigation.js` canonical model + groups |
| Home | Attention aggregation spine (`lib/attention.js`, `useAttentionHome`) |
| Approvals | Normalized multi-source inbox; ConfirmDialog; server decide only |
| Chat | Full `/chat` workspace + compact Copilot on same `/api/v1/chat/*` transport |
| Redirects | Soft only: `/infrastructure`→`/monitoring`, `/me`→`/settings` |
| CORS | `saathi/cors_policy.py` — no wildcard, prod fail-closed |
| Cert | Managed Playwright harnesses M47.4 + M47.7 (BFF+UI) |

## Routes added (canonical entry points)

`/` (attention Home), `/command`, `/missions`, `/projects`, `/approvals`, `/monitoring`, `/business`, `/agents`, `/trading`, `/settings`, plus studio paths already present.

## Routes redirected (soft, temporary)

| From | To |
|---|---|
| `/infrastructure` | `/monitoring` |
| `/me` | `/settings` |

## Routes retained (compatibility)

`/chat`, `/control`, `/finance`, `/studio-os`, and other KEEP_COMPATIBILITY / NO_REDIRECT_REQUIRED legacy surfaces per M47.6 matrix.

## Security boundaries

- Approvals: server-authorized; UI confirm; unavailable ≠ zero  
- Chat/Copilot: no silent privileged execution  
- Trading Guardian: ADVISORY_ONLY · NO_EXECUTION · leverage disabled · no withdraw  
- CORS: never `*` with credentials; production requires `SAATHI_CORS_ORIGINS`

## Known limitations (accepted if evidence holds)

1. Live model streaming not exercised with external credentials  
2. Live Stop/cancel not exercised against real stream  
3. A11y not full WCAG / AT certification  
4. Control / Finance / Studio keep documented compatibility surfaces  
5. Production needs explicit `SAATHI_CORS_ORIGINS`  
6. Expected API failures without session or live providers  

## Owner decisions required

1. Accept shell IA + foundation as reviewable code  
2. Accept KEEP_COMPATIBILITY surfaces for this PR  
3. Authorize **draft exit** only (this milestone)  
4. **Merge remains unauthorized**  
5. Production deploy remains blocked until CORS origins configured  

## Draft-exit gates

- Diff review clean of blockers  
- Commit scope UI/UX only  
- PR description truthful  
- No blocking review threads  
- Compatibility accepted  
- CORS production gate documented  
- Authority review pass  
- tests / lint / build / browser cert / secret scan pass  
- GitHub required checks not failing  
- No merge conflict  

## Merge exclusions

```text
MERGE_NOT_AUTHORIZED
DEPLOY_NOT_AUTHORIZED
```
