# M17.25 — Interactive Browser Path Audit

**Milestone:** Governed Interactive Browser Sessions, Actions, and Human Handoffs  
**Starting commit:** `caca1da4c5a3a2f23c0ae60855b4916dcfc5eb10` (M17.24 tag)  
**Canonical interactive API:** `InteractiveBrowser` → session store → `GovernedBrowser.execute` → `ExecutionGateway`

## Classification legend

| Class | Meaning |
|-------|---------|
| `GOVERNED_INTERACTIVE` | State-changing interactive action fully governed |
| `GOVERNED_READ_ONLY` | Read/navigate governed |
| `DELEGATES_TO_GOVERNED` | Wrapper that enters InteractiveBrowser / GovernedBrowser |
| `TEST_ONLY` | Tests / harnesses |
| `LEGACY_REMOVE` | Removed or superseded |
| `FAIL_CLOSED` | Production path returns typed denial |
| `UNGOVERNED_BLOCKING` | Must not remain |
| `UNCERTAIN_REQUIRES_PROOF` | Needs more evidence |

## Inventory

| ID | File / symbol | Entry | Session | Action | State-chg? | Side effect? | Policy | Approval | Actor | Mission/run | Ownership | Scope | Idempotency | Evidence | Handoff | Resume | Cancel | Prod? | Remediation | Disposition |
|----|--------------|-------|---------|--------|------------|--------------|--------|----------|-------|-------------|-----------|-------|-------------|---------|---------|--------|--------|-------|-------------|-------------|
| I01 | `interactive.InteractiveBrowser.open_session` | API | Creates gov session | lifecycle | no | no | domains | scope | yes | yes | owner | domains+classes | n/a | session row | n/a | n/a | yes | yes | — | `GOVERNED_INTERACTIVE` |
| I02 | `InteractiveBrowser.act` navigate/read | API | Required | read_only | no | no | domain | low | yes | yes | yes | yes | optional | gateway | n/a | n/a | yes | yes | — | `GOVERNED_READ_ONLY` |
| I03 | `InteractiveBrowser.act` click/fill/type | API | Required | low/sensitive | yes | possible | domain+target | class | yes | yes | yes | yes | recommended | gateway+ledger | blocks if paused | after handoff | yes | yes | — | `GOVERNED_INTERACTIVE` |
| I04 | `InteractiveBrowser.act` submit/publish | API | Required | external_effect | yes | yes | domain+pre-commit | **dedicated** | yes | yes | yes | yes | **required** | pre-commit cp + gateway | yes | yes | yes | yes | nav approval insufficient | `GOVERNED_INTERACTIVE` |
| I05 | `InteractiveBrowser.act` trade/payment | API | Required | financial | yes | yes | TG required | TG | yes | yes | yes | yes | required | denial | n/a | n/a | yes | yes | Trading Guardian | `FAIL_CLOSED` without TG |
| I06 | `InteractiveBrowser.request/complete_handoff` | API | Required | handoff | yes | no | reason+scope | human claim | yes | yes | lease release | bounded | n/a | checkpoint | full | validated | yes | yes | — | `GOVERNED_INTERACTIVE` |
| I07 | `InteractiveBrowser.resume` | API | Required | lifecycle | no | no | domain+fp | re-eval | yes | yes | yes | yes | n/a | checkpoint | n/a | core | yes | yes | mismatch fail closed | `GOVERNED_INTERACTIVE` |
| I08 | `gov_session.BrowserSessionStore` | store | SQLite | — | — | — | transitions | — | owner | mission | lease | domains | action ledger | durable | handoff table | checkpoint table | close | yes | — | `GOVERNED_INTERACTIVE` |
| I09 | `governed.GovernedBrowser.execute` | gateway | technical id | family | via intent | via adapter | M17.23/24 | digest | yes | yes | via interactive | domain | gateway | yes | via IB | via IB | cancel exec | yes | used by IB | `GOVERNED_READ_ONLY` / interactive via adapter |
| I10 | `BrowserAdapter` fake interactive | handler | n/a | click/fill/submit | yes | simulated | domain | upstream | upstream | upstream | n/a | redirect | upstream | summary | n/a | n/a | n/a | tests+IB | service mode live deferred | `GOVERNED_INTERACTIVE` (fake) |
| I11 | `BrowserAdapter` service interactive | handler | n/a | click… | yes | would | — | — | — | — | — | — | — | fail closed | — | — | — | if live | still `interactive_requires_live_session` without live adapter | `FAIL_CLOSED` |
| I12 | `tools/agent_browser.ab_click/fill/type` | agent tools | ephemeral | interactive | yes | via IB | yes | class | agent | agent_browser | ephemeral | yes | optional | yes | no | no | no | yes | M17.25 routes to IB | `DELEGATES_TO_GOVERNED` |
| I13 | `tools/agent_browser` raw `_run` | agent | none | any | yes | yes | blocked | — | — | — | — | — | — | deny | — | — | — | yes | M17.24 fail closed; prod blocks env | `FAIL_CLOSED` |
| I14 | `computer_agent` LiveBrowserDriver click/fill | computer ops | live CDP | interactive | yes | yes | connector risk | gateway | yes | yes | session | computer policy | engine | evidence | pause sensitive | recovery | yes | yes | remains gateway ComputerAdapter | `GOVERNED_INTERACTIVE` |
| I15 | `human_browser` Mac agent click/fill | signed jobs | profile | interactive | yes | yes | job sig | secret | queue | run store | profile | selectors | job id | run store | teach | n/a | n/a | yes | isolated queue; not generic autonomy | `DELEGATES_TO_GOVERNED` (queue) / isolated |
| I16 | Cookie `SessionManager` | technical | cookie jar | storage | no | cookies | n/a | n/a | n/a | n/a | name | origin | n/a | disk | n/a | n/a | delete | yes | not authority; gov session is | technical only |
| I17 | Playwright tier | tier | service | open/ss | limited | fetch | via gateway | via gateway | — | — | — | — | — | — | — | — | — | via adapter | allowlisted | technical |
| I18 | eval_js / captcha_solve | any | — | prohibited | — | — | deny | — | — | — | — | — | — | denial | handoff instead | — | — | yes | prohibited + handoff | `FAIL_CLOSED` |
| I19 | `SAATHI_ALLOW_RAW_BROWSER` | env | — | override | yes | yes | blocked in prod | — | — | — | — | — | — | — | — | — | — | prod=no | M17.25 production hard-block | `FAIL_CLOSED` in production |
| I20 | Unit tests / fakes | tests | injected | all | — | no | — | — | — | — | — | — | — | — | — | — | — | no | — | `TEST_ONLY` |

## Summary counts

| Disposition | Count |
|-------------|------:|
| Total paths | 20 |
| Governed interactive | 8 |
| Governed read-only | 2 |
| Delegates to governed | 2 |
| Fail-closed | 4 |
| Test-only | 1 |
| Technical (non-authority) | 2 |
| Isolated human queue | 1 |
| **UNGOVERNED_BLOCKING** | **0** |
| Uncertain production interactive | 0 |

## Root causes (pre-M17.25)

1. M17.24 governed **dispatch/navigation** but interactive click/type/submit on `BrowserService` failed closed without a session model.
2. No ownership/lease model for browser sessions (only cookie jars).
3. Navigation and form-fill could not express distinct approval scopes for final submit.
4. Human intervention (CAPTCHA/MFA) was informal, not a workflow state.
5. No action ledger for interactive idempotency across retries.

## Remaining limitations

1. Live Playwright/CDP interactive execution still requires ComputerAdapter live driver or human Mac agent; `BrowserService` service-mode interactive remains fail-closed without a live session adapter.
2. Domain allowlists remain staging-oriented by default.
3. Full migration of every human-browser workflow step into `InteractiveBrowser.act` is larger scope (queue remains isolated and signed).
4. Screenshot redaction is metadata-level (no OCR redaction pipeline in this milestone).
