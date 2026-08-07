# M130–M138 — HCG Native Operations Application Productization

Date: 2026-07-29

Terminal verdict: `HCG_NATIVE_APP_COMPLETE_WITH_LIMITATIONS`

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M130 | Domain model, money (integer paisa), persistence, tenancy, RBAC | Complete |
| M131 | Orders, payments, shifts, cash reconciliation | Complete |
| M132 | Customers, credit ledger, suppliers, purchases, expenses | Complete |
| M133 | Menu, inventory, recipes, stock movements, kitchen | Complete |
| M134 | Dashboard, reports, search, notifications, metrics | Complete |
| M135 | Skills, Knowledge/Conversation grounding, approvals, evidence | Complete |
| M136 | APIs, HCG UI/POS workspace, accessibility | Complete |
| M137 | Backup, restore, migration schema, health, security | Complete |
| M138 | Browser certification, regressions, final product cert | Complete with limitations |

## Architecture

`saathi/platform/hcg/` — first-party business application domain service.

Hosts through **Universal Application Runtime** (`saathi.hcg_pos` package).

Mutation path:

```
Authenticated operator
→ HCG API / UI command
→ tenant/workspace/app-instance authorization
→ HCG domain validation
→ approval when required (Approval Center)
→ HcgService transaction
→ evidence + audit + notification
→ read model update
```

Does **not** create parallel auth, RBAC, approval, audit, evidence, launcher,
conversation, knowledge, or skill systems.

## Money

Integer **minor units** (paisa for NPR). Binary float rejected for financial amounts.

## Evidence

- Tests: `tests/test_m130_hcg_operations.py`
- Frontend: `saathi-os/lib/hcg.test.js`
- Browser: `docs/evidence/m138/browser/M138_BROWSER_CERT.json`

## Limitations

- Local-only; no production deployment
- Deterministic synthetic demo data only
- Manual QR payment recording (no live gateway)
- No multi-device sync
- Approximate profitability when cost data incomplete
- English-primary UI

## Explicit non-goals preserved

- No live HCG POS mutation
- No Supabase/Vercel production access
- No marketplace
- Trading Guardian unchanged
