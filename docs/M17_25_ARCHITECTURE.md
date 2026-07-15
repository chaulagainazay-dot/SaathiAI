# M17.25 Architecture — Interactive Sessions, Actions, Handoffs

## Flow

```text
Caller
  → InteractiveBrowser.open_session / act / request_handoff / resume / close
  → BrowserSessionStore (ownership, lease, status, action ledger, handoff, checkpoint)
  → action taxonomy + target resolution + commit boundary
  → GovernedBrowser.execute (M17.23/24)
  → ExecutionGateway.submit
  → BrowserAdapter (fake interactive / technical tiers)
  → Evidence + security timeline + execution record
```

## Session states

`requested → policy/approval pending → ready → active ⇄ checkpointed |
paused_for_human | paused_for_approval | resuming → completed/cancelled/
failed/expired/reconciliation_required → closed`

## Action classes

| Class | Examples | Default approval |
|-------|----------|------------------|
| read_only | navigate, read, screenshot, scroll | auto when domain OK |
| low_interactive | click, menu, non-sensitive fill | auto on dev; policy elsewhere |
| sensitive_input | password fields, PII, upload | dedicated approval |
| external_effect | submit, publish, book | dedicated approval + idempotency + pre-commit checkpoint |
| financial | trade, payment, withdrawal | Trading Guardian only |
| prohibited | eval_js, captcha_solve, mfa_bypass | always deny |

Navigation approval **never** authorizes external_effect or financial actions.

## Human handoff

`request_handoff` → checkpoint + `paused_for_human` + release lease →
human claim → complete/decline → policy re-eval resume → owner lease restored.

## Raw browser

`SAATHI_ALLOW_RAW_BROWSER` is **ignored in production** (`SAATHI_ENV=production`).
Normal interactive work uses `InteractiveBrowser` without raw override.

## Modules

| Module | Role |
|--------|------|
| `saathi/browser/gov_session.py` | Session/action/handoff/checkpoint SQLite store |
| `saathi/browser/interactive.py` | Taxonomy, targets, InteractiveBrowser API |
| `saathi/browser/governed.py` | Existing gateway entry (unchanged contract) |
| `saathi/browser/guard.py` | Import allowlist + production raw block |
