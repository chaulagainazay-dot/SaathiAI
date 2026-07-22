# M17.26 — Production Browser Adapter, Domain Policy, Evidence Redaction Audit

**Milestone:** Production Browser Adapter, Domain Policy, Evidence Redaction, and Workflow Migration  
**Starting commit:** `7b2191502a86533c94e97e311e2c63face801123` (M17.25)  
**Rollback point:** same HEAD  

## Classification legend

| Class | Meaning |
|-------|---------|
| `CANONICAL_PRODUCTION` | Production-safe governed adapter |
| `CANONICAL_SANDBOX` | Deterministic sandbox / test adapter with full contract |
| `GOVERNED_DELEGATE` | Wrapper that enters InteractiveBrowser / GovernedBrowser |
| `TEST_ONLY` | Tests / harnesses |
| `LEGACY_REMOVE` | Removed or superseded |
| `FAIL_CLOSED` | Production path returns typed denial |
| `UNGOVERNED_BLOCKING` | Must not remain |
| `UNCERTAIN_REQUIRES_PROOF` | Needs more evidence (none left unresolved) |

---

## 4.1 Adapter inventory

| Adapter ID | File / symbol | Type | Prod? | Session | Own | Lease | Taxonomy | Approval | Domain | Idem | Evidence | Redact | Reconnect | Reconcile | Kill | TG | Disposition | Remediation |
|------------|---------------|------|-------|---------|-----|-------|----------|----------|--------|------|----------|--------|-----------|-----------|------|----|-------------|-------------|
| A01 | `production_adapter.ProductionBrowserAdapter` | CDP sandbox/live | yes | yes | yes | yes | yes | upstream | yes | via IB | yes | via pipeline | yes | yes | yes | upstream | `CANONICAL_PRODUCTION` / `CANONICAL_SANDBOX` | — |
| A02 | `human_mac_adapter.HumanMacAdapter` | Human Mac | yes | yes | yes | yes | yes | upstream | via prod | via IB | yes | yes | via prod | yes | yes | upstream | `CANONICAL_PRODUCTION` | — |
| A03 | `governed.BrowserAdapter` fake | Fake | tests | n/a | n/a | n/a | yes | upstream | yes | upstream | yes | n/a | n/a | uncertain | n/a | upstream | `CANONICAL_SANDBOX` | — |
| A04 | `governed.BrowserAdapter` service | Service tiers | yes | via bind | via IB | via IB | via IB | upstream | yes | upstream | yes | via pipeline | via prod | via prod | via prod | upstream | `GOVERNED_DELEGATE` | binds ProductionBrowserAdapter for interactive |
| A05 | `computer_agent.operations.ComputerAdapter` | Connector | yes | live CDP | gateway | gateway | connector | gateway | connector | engine | yes | sensitive.py | recovery | yes | yes | gateway | `GOVERNED_DELEGATE` | remains gateway-routed |
| A06 | `computer_agent.browser_driver.LiveBrowserDriver` | CDP technical | technical | n/a | n/a | n/a | n/a | n/a | n/a | n/a | local | n/a | n/a | n/a | n/a | n/a | `CANONICAL_PRODUCTION` (driver only) | only via allowlisted adapters |
| A07 | `human_browser.chrome_backend.ChromeBackend` | AppleScript/CDP | isolated | profile | queue | queue | job | signed | job | job id | run store | vision | n/a | n/a | n/a | n/a | `FAIL_CLOSED` / isolated queue | not generic autonomy; workflow migrate fail-closed for raw |
| A08 | `tools.agent_browser._run` | CLI raw | no | no | no | no | no | no | no | no | deny | n/a | n/a | n/a | n/a | n/a | `FAIL_CLOSED` | M17.24/25/26 |
| A09 | `tools.agent_browser.ab_click/fill/type` | Tool | yes | ephemeral | yes | yes | yes | class | yes | optional | yes | yes | n/a | n/a | n/a | n/a | `GOVERNED_DELEGATE` | routes to IB |
| A10 | PlaywrightTier / HttpTier / CamofoxTier | Technical tiers | via adapter | cookie | n/a | n/a | open/ss | gateway | gateway | gateway | limited | n/a | n/a | n/a | n/a | n/a | `GOVERNED_DELEGATE` | never direct from product |
| A11 | Unit fakes | Test | no | injected | — | — | — | — | — | — | — | — | — | — | — | — | `TEST_ONLY` | — |

**Summary:** 11 adapters inventoried. **0 UNGOVERNED_BLOCKING.** **0 UNCERTAIN unresolved.**

---

## 4.2 Workflow migration inventory

| Workflow ID | File / symbol | Entry | Mechanism | IB.act? | Session | Policy | Approval | Evidence | Handoff | Prod? | Migrate? | Disposition |
|-------------|--------------|-------|-----------|---------|---------|--------|----------|----------|---------|-------|----------|-------------|
| W01 | `interactive.InteractiveBrowser.act` | API | governed | yes | yes | yes | yes | yes | yes | yes | n/a | `MIGRATED` (canonical) |
| W02 | `workflow_migrate.execute_workflow_step` | DSL step | IB.act | yes | yes | yes | yes | yes | yes | yes | done | `MIGRATED` |
| W03 | `agent_browser.ab_click/fill/type` | tools | IB | yes | ephemeral | yes | class | yes | limited | yes | done | `MIGRATED` |
| W04 | `agent_browser._run` | tools | raw CLI | no | no | blocked | — | deny | — | blocked | fail-closed | `FAIL_CLOSED` |
| W05 | `BrowserService.open/extract/screenshot` | service | gateway | via gov | technical | yes | gateway | yes | n/a | yes | governed | `GOVERNED_DELEGATE` |
| W06 | `human_browser.workflows.*` | queue jobs | primitives | no | profile | signed | secret | run store | teach | isolated | partial | `FAIL_CLOSED_OR_ISOLATED_QUEUE` — generic autonomy blocked; signed queue remains |
| W07 | `computer_agent.live_workflow` | connector | ComputerAdapter | no (gateway) | live | connector | gateway | yes | pause | yes | via CA | `GOVERNED_DELEGATE` |
| W08 | ChatGPT browser tool | tools | fail closed | no | no | — | — | deny | — | blocked | fail-closed | `FAIL_CLOSED` |

---

## 4.3 Domain-policy inventory

| Source | Env | Default | Allowlist | Denylist | Wildcards | Redirect | Subdomain | Localhost | Private IP | IDN | Custom protocols | Prod safe? | Remediation |
|--------|-----|---------|-----------|----------|-----------|----------|-----------|-----------|------------|-----|------------------|------------|-------------|
| `domain_policy.DomainPolicyService` production | production | deny | explicit / `SAATHI_BROWSER_ALLOWED_DOMAINS` | metadata + deny hosts | rejected | revalidate | exact only | denied | denied | mixed-script denied | denied | **yes** | — |
| staging config | staging | deny+list | staging hosts | metadata | no | revalidate | exact | denied | denied | flagged | denied | yes | — |
| development/test | dev/test | allowlist defaults | example.com + localhost | metadata | no unrestricted | revalidate | of listed roots | allowed | denied | flagged | denied | yes for non-prod | — |
| legacy `policy.check_domain` | any | staging suffixes | param or defaults | metadata | suffix exact | revalidate | endswith root | OK if listed | blocked | n/a | schemes only | via env branch | now delegates to DomainPolicyService when env set / production |
| Session `allowed_domains` | session | session scope | session list | — | no | via check | host match | per env | per env | — | — | yes | — |

**Gaps found pre-M17.26:** staging-oriented default allowlist applied in production-shaped paths; substring risk on deceptive hosts; no env-specific HTTPS-only production defaults. **Remediated.**

---

## 4.4 Evidence and redaction inventory

| Evidence type | Producer | Storage | Sensitive risk | Existing redaction | OCR | Deterministic masks | Retention | Prod? | Remediation |
|---------------|----------|---------|----------------|--------------------|-----|---------------------|-----------|-------|-------------|
| Screenshot | EvidenceRedactionPipeline / IB | ref hash only | high | class→mode; suppress secrets | optional secondary | selectors/types/ARIA/autofill | class-based days | yes | **implemented** |
| DOM snapshot | redact_dom_snapshot | bounded nodes | medium | strip secrets/values | n/a | yes | short | yes | **implemented** |
| Trace | policy | none by default | high | disabled default | n/a | headers/cookies policy | require policy | yes | disabled default |
| Video | policy | none by default | high | disabled default | n/a | n/a | strict if enabled | yes | disabled default |
| Cookies / storage_state | pipeline | never logged | critical | suppress | n/a | n/a | n/a | yes | secrets_not_logged |
| Download metadata | BrowserAdapter | workspace path | medium | filename sanitize | n/a | path inside workspace | default | yes | existing + no content log |
| Action ledger | gov_session | SQLite | medium | text redacted | n/a | sensitive payload digests | session TTL | yes | M17.25 |
| Alerts | adapter_monitor | in-memory / events | low | no screenshots/secrets | n/a | key strip | dedupe window | yes | **implemented** |

**Gaps found pre-M17.26:** screenshot redaction was metadata-level only; no classification model; no deterministic field masks. **Remediated** with fail-closed suppression for AUTH/FINANCIAL/TRADING/MEDICAL.

---

## Root causes (why M17.25 left live adapters incomplete)

1. Interactive governance existed in storage/API, but `BrowserAdapter` service mode returned `interactive_requires_live_session` without a session-bound production adapter.
2. Domain policy reused staging defaults (localhost + broad suffixes) without production deny-by-default.
3. Human Mac and CDP drivers remained technical surfaces not unified under one session/health/reconnect contract.
4. Evidence capture lacked classification + deterministic redaction pipeline (OCR-only would be insufficient).
5. Workflow steps lacked a governed schema forcing `InteractiveBrowser.act`.

## Residual limitations (evidence-backed)

1. Live CDP attach (`allow_live=True`) still requires a managed loopback endpoint and browser binary; unit tests use sandbox only.
2. Human browser **signed queue** workflows remain isolated (not fully rewritten into IB.act); raw generic paths fail closed.
3. Pixel-level screenshot blur uses deterministic mask stubs without a heavy imaging dependency — sensitive classes suppress rather than claim OCR safety.
4. Temporary domain exceptions are supported by model but no permanent override env bypass exists.
