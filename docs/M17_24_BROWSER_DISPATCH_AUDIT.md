# M17.24 — Browser Dispatch Path Audit

**Milestone:** Eliminate Residual Ungoverned Browser Dispatch Paths  
**Starting commit:** `f2f262f123f5327b5b47abaa4a39cc13b0947c0d`  
**Ending commit:** M17.24 commit on branch `milestone/m7-security-engine` (see `git log -1 --grep M17.24`)  
**Canonical boundary:** `GovernedBrowser.execute` → `ExecutionGateway.submit` → `BrowserAdapter` → tier drivers  

## Classification legend

| Class | Meaning |
|-------|---------|
| `CANONICAL_GOVERNED` | Authoritative production entry |
| `DELEGATES_TO_CANONICAL` | Caller constructs governed context and invokes gateway |
| `TEST_ONLY` | Reachable only from tests / injected harnesses |
| `DEAD_CODE` | Unused |
| `UNGOVERNED_BLOCKING` | Production-reachable and must be fixed (none remaining) |
| `LEGACY_TO_REMOVE` | Removed or fail-closed |
| `UNCERTAIN_REQUIRES_PROOF` | Needs further evidence (none remaining for production dispatch) |

## Dispatch path inventory

| Path ID | File / symbol | Entry point | Caller type | Mechanism | Status | Actor? | Mission/run? | Approval? | Policy? | Risk? | Evidence? | Idempotency? | Retry/resume governed? | Prod reachable? | Remediation | Disposition |
|---------|---------------|-------------|-------------|-----------|--------|--------|--------------|-----------|---------|-------|-----------|--------------|------------------------|-----------------|-------------|-------------|
| P01 | `saathi/browser/governed.py` `GovernedBrowser.execute` | Public API | API/agent/tools | Gateway | Governed | Yes | Yes (when required) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Canonical | `CANONICAL_GOVERNED` |
| P02 | `saathi/browser/governed.py` `BrowserAdapter.dispatch` | Gateway handler only | Technical | Tiers / fake | Governed upstream | Via intent | Via intent | Upstream | Defense-in-depth domain | Upstream | Via outer | N/A | N/A | Yes (via gateway) | Allowlisted technical | `CANONICAL_GOVERNED` |
| P03 | `saathi/browser/service.py` `BrowserService.open` (singleton) | `browser.open` | Product | Was direct tiers | Now governed default | Via kwargs | Via kwargs | Via gateway | Yes | Yes | Yes | Yes | Via gateway | Yes | Default `allow_direct=False` | `DELEGATES_TO_CANONICAL` |
| P04 | `BrowserService._open_direct` | Adapter / harness | Technical | Tiers | Technical only | N/A | N/A | Upstream | N/A | N/A | Events only | N/A | N/A | Only after gateway or harness | Keep technical | `CANONICAL_GOVERNED` (technical) |
| P05 | `BrowserService(tiers=…)` tests | Unit tests | Test | Direct tiers | Test | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | No | `allow_direct` when tiers injected | `TEST_ONLY` |
| P06 | `playwright_tier.py` / `http_tier` / `camofox_tier` | Service tiers | Technical | Playwright/HTTP | Technical | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | Via adapter only | Allowlist + AST guard | `CANONICAL_GOVERNED` (adapter) |
| P07 | `tools/agent_browser.py` `ab_*` | Tool registry | Agent | Was subprocess CLI | Fail closed / governed navigate | Partial | Partial | Via GB | Via GB | Via GB | Via GB | Via GB | Via GB | Yes (tools) | Raw CLI disabled; navigate delegates | `DELEGATES_TO_CANONICAL` / fail-closed |
| P08 | `tools/registry.py` `ab_*` handlers | `execute_tool` | Agent/chat | Registry dispatch | Gated by SafetyHarness + agent_browser | Via speaker | No (pre-M17) | SafetyHarness | SafetyHarness | Yes | Partial | No | No | Yes | Handlers call agent_browser | `DELEGATES_TO_CANONICAL` |
| P09 | `tools/browser.py` `post` | Social tools | Product | AppleScript | Fail closed + governed intent | Yes | Yes | Required for submit | Domain | High | Yes | N/A | N/A | Yes | Raw needs `SAATHI_ALLOW_RAW_BROWSER` | `DELEGATES_TO_CANONICAL` |
| P10 | `tools/chatgpt_browser.py` `ask_chatgpt` | Server endpoints | Product | AppleScript/JS | Fail closed + governed intent | Yes | Yes | Via GB | Domain | Medium+ | Yes | N/A | N/A | Yes | Prefer LLM connector | `LEGACY_TO_REMOVE` (fail-closed) |
| P11 | `computer_agent/browser_driver.py` `LiveBrowserDriver` | ComputerAdapter live | Computer agent | CDP subprocess | Gateway-routed via ComputerAdapter | Via engine | Via engine | Via gateway | Computer policy | Via risk class | Evidence | Via engine | Via engine | Yes (M17 computer) | Allowlisted; AST blocks other importers | `CANONICAL_GOVERNED` (via ComputerAdapter) |
| P12 | `computer_agent/operations.py` `ComputerAdapter` | Connector ExecutionEngine | Computer agent | Live or deterministic | Gateway | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Unchanged path | `CANONICAL_GOVERNED` |
| P13 | `computer_agent/live_workflow.py` | CLI / live validation | Operator | Sets live driver then gateway ops | Governed | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Staging/live validation | Documented | `DELEGATES_TO_CANONICAL` |
| P14 | `infrastructure/connectors/drivers/browser.py` | Connector registry | Infra | Was direct `browser.open` | Governed when production singleton | Yes | Yes | Via GB | Yes | Yes | Yes | Yes | Yes | Yes | Injected fakes remain direct | `DELEGATES_TO_CANONICAL` |
| P15 | `infrastructure/human_browser/*` | Mac agent queue | Human publish | Signed jobs → Chrome | Isolated subsystem | Queue identity | Run store | Job signature | Selector registry | Workflow | Run store | Job id | Agent loop | Yes (token APIs) | Not generic autonomy; claim/complete remain; `/human/test` gated | `DELEGATES_TO_CANONICAL` (test API) / isolated |
| P16 | `server.py` `/api/v1/human/test` | HTTP API | Operator | Enqueue open | Governed intent first; raw needs approval/env | Yes | Yes | Optional approval | Domain | Yes | Yes | N/A | N/A | Yes | Fail closed without approval/env | `DELEGATES_TO_CANONICAL` |
| P17 | `server.py` human claim/complete | Mac agent | System | Queue only | No browser on VM | Token | Job id | Secret signature | N/A | N/A | Run report | Job id | N/A | Yes | No browser driver on server | `CANONICAL_GOVERNED` (queue relay) |
| P18 | `scripts/youtube_test.py` etc. | CLI scripts | Operator | Playwright direct | Scripts | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | No (scripts/) | Out of product package scan | `TEST_ONLY` / operator scripts |
| P19 | `execution/trade.py` Trading Guardian | Finance | Finance | Paper/live trade | Separate boundary | Yes | Case id | L4 | Trade policy | Critical | Yes | Intent id | Reconcile | Yes | Must not be invoked by browser gateway | Isolated / unchanged |
| P20 | `webbrowser.open` in menubar/pushtotalk | Local UI | Desktop | OS open localhost | Localhost UI only | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | Local | Not automation | Not browser automation |

## Summary counts

| Disposition | Count |
|-------------|------:|
| Total paths inventoried | 20 |
| Canonical governed | 7 |
| Delegates to canonical | 7 |
| Test-only / scripts | 2 |
| Legacy fail-closed | 1 |
| Isolated (human queue / trade) | 2 |
| Local UI open (non-automation) | 1 |
| **UNGOVERNED_BLOCKING remaining** | **0** |
| **UNCERTAIN production dispatch** | **0** |

## Root causes (why residuals existed)

1. M17.23 introduced `GovernedBrowser` but left `BrowserService.open` default ungoverned for test compatibility.
2. Pre-gateway tool registry (`agent_browser`, AppleScript social/ChatGPT) predated ExecutionGateway.
3. Computer-agent CDP and human-browser Mac agent were intentionally deferred in M17.23.
4. Connector `BrowserConnector` wrapped the ungoverned service path.
5. No static import allowlist prevented new product modules from importing Playwright/CDP.

## Canonical contract (mapped to existing models)

| Requirement | Mapping |
|-------------|---------|
| actor_id / actor_type | `ToolIntent.actor_id` + `ActorType` via `build_browser_intent` |
| request_source | `metadata.request_source` |
| mission_id / mission_run_id | `ToolIntent.mission_id` + `metadata.mission_run_id` |
| browser_action_type | `operation` / `parameters.action` |
| target_scope | domain policy + `parameters.origin` |
| risk_tier | `classify_risk` → `RiskLevel` / approval level |
| policy_decision | domain + prohibited actions + `require_governed_context` |
| approval_reference | `approval_id` + digest-bound store |
| idempotency_key | `ToolIntent.idempotency_key` |
| correlation_id / parent_run_id | intent + metadata |
| retry_attempt / checkpoint | execute kwargs + metadata |
| evidence | Evidence store + security timeline + execution record |

Incomplete or forged context is **denied** (`BrowserGovernanceError` → denied `ExecutionRecord`).

## Architectural guardrails

- Module: `saathi/browser/guard.py`
- AST scan of `saathi/**/*.py` for forbidden Playwright/Selenium imports, dynamic imports, and subprocess browser launch patterns outside allowlist
- Blocking critical checks: `browser.dispatch_guard_present`, `browser.no_ungoverned_driver_imports`, `browser.direct_dispatch_blocked`, `browser.context_attribution_enforced`, `browser.trading_isolation`
- Production singleton: `BrowserService(allow_direct=False)`
- Emergency only: `SAATHI_ALLOW_RAW_BROWSER=1` (never production default)

## Trading Guardian isolation

- `BrowserAction.TRADE` / `PAYMENT` prohibited and require `trading_authorized`
- Generic browser approval (`approval_pre_resolved`) does **not** authorize trading
- Unrelated browser navigate/read does not import or mutate `saathi.execution.trade`
- No live trading capability added

## Remaining bounded limitations

1. Live interactive click/type/submit on `BrowserService` tiers still requires live session adapter (ComputerAdapter CDP or human-browser Mac agent); service mode returns fail-closed for interactive ops without live session.
2. Human-browser Mac agent stack remains an isolated signed-queue subsystem; full migration of every workflow step into `GovernedBrowser` is larger scope (documented, test API gated).
3. Domain allowlist remains staging-oriented (`example.com`, localhost, saathi.local); production host allowlists are configuration, not opened by this milestone.
4. `SAATHI_ALLOW_RAW_BROWSER` exists for local operator emergency use; must never be set in production deploy configs.

## Failure behavior

| Condition | Result |
|-----------|--------|
| Unknown / missing actor | DENIED |
| Missing mission/run when required | DENIED |
| Invalid / expired approval | DENIED |
| Cancelled / paused / blocked mission | DENIED |
| Disabled schedule | DENIED |
| Untrusted event trigger | DENIED |
| Retry without authorization | DENIED |
| Resume without checkpoint | DENIED |
| Mission ID forgery | DENIED |
| Trading without Trading Guardian | DENIED |
| Raw agent-browser / AppleScript | RAW_BROWSER_DISABLED |
| Direct `open(governed=False)` on production service | DIRECT_BROWSER_BLOCKED |
