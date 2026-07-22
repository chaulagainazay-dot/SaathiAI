# M17.23 — Governed Browser Actions through ExecutionGateway

## Scope

Route browser automation through the existing **ExecutionGateway** (M17.22)
so browser side effects cannot bypass validation, permission, risk, approval,
idempotency, Evidence, security events, or the run ledger.

This is **not** a browser-engine rewrite. Playwright / HTTP / Camofox tiers
remain. Trading Guardian is unengaged.

## Governed flow

```text
Browser request
  → ToolIntent (family=browser)
  → domain / scheme policy
  → risk classification
  → ExecutionGateway.submit
  → BrowserAdapter (BrowserService or deterministic fake)
  → Evidence · security event · run ledger · CC / CEO metrics
```

Authoritative API: `saathi.browser.governed.GovernedBrowser`.

## Risk policy (summary)

| Class | Actions | Approval |
|-------|---------|----------|
| Low | navigate, open, read, extract, screenshot | auto when domain OK |
| Medium | click, type, fill, download, upload | auto on dev/staging; else L3 |
| High | submit, workflow, enter_credentials | always L4 |
| Prohibited | eval_js, trade, payment, password_change, mfa_bypass, captcha_solve, account_delete | fail closed |

Sensitive field names on fill/type elevate to high.

## Domain / network

- Allow: localhost, example.com/net/org, saathi.local, configured hosts
- Deny: private/link-local IPs (except loopback), cloud metadata, dangerous schemes (`file:`, `javascript:`, `data:`, …)
- Redirects revalidate **final** origin

## Approval binding

Digest includes actor, action params (url/origin/session/selector/payload digest), risk content fields. Session / origin / payload changes invalidate approval. No unlimited session-wide approval.

## Idempotency & uncertain outcomes

- Explicit idempotency key prevents double submit
- Uncertain submit → `failure_category=outcome_uncertain`, **non-retryable**

## Prompt injection

Page text is untrusted data (`untrusted_page_content=True`). Injection markers are recorded; they never auto-create ToolIntents or approvals.

## Downloads / uploads

Workspace-scoped paths only; sanitized filenames; path traversal rejected; upload outside workspace denied.

## Migrated entry points

| Path | Behavior | Migrated |
|------|----------|----------|
| `GovernedBrowser.execute` | Authoritative | **Yes** |
| `BrowserService.open(governed=True)` | Optional gateway path | **Yes** |
| `BrowserService.open()` default | Legacy tier path (tests/compat) | Documented residual |
| `saathi.tools.agent_browser` | CLI agent-browser | Deferred |
| `computer_agent.browser_driver` | Live CDP driver | Deferred |
| `infrastructure/human_browser` | Human Chrome tier | Deferred |

## Remaining bypasses

- Default `BrowserService.open` without `governed=True` still hits tiers directly (compat). Prefer `GovernedBrowser` for policy-bound work.
- Interactive click/type/submit on live `BrowserService` still needs session adapter (fake path covers policy in tests; live interactive is deferred).

## Critical checks (+6)

- `browser.gateway_boundary_present`
- `browser.domain_policy_enforced`
- `browser.high_risk_approval_enforced`
- `browser.idempotent_submission`
- `browser.prompt_injection_isolated`
- `browser.evidence_generated`

## Tests

`tests/test_m17_23_browser_execution_gateway.py` — 46 focused tests.

## Files

- `saathi/browser/policy.py`, `governed.py`
- `saathi/browser/service.py` (optional `governed=True`)
- Control Center / CEO integration
- M17.22 family list includes `browser`

## Rollback

```bash
git reset --hard <pre-M17.23-commit>
```

Do not push. Do not begin M17.24.
