# Phase 3 Execution Audit — Current Paths & Bypass Risks

**Date:** 2026-07-10  
**Scope:** Universal Secure Execution Runtime architecture audit  
**Purpose:** Identify all current execution paths, authorize risks, and plan mandatory migration

---

## Executive Summary

SaathiOS currently has **two separate execution entry points**:

1. **Connector Manager** (`saathi/connectors/manager.py:execute()`)
   - Primary path for external actions (email, social, Telegram, YouTube, Drive, payments)
   - Checks: account exists, capability valid, account connected, rate limit
   - Emits: events → Event Bus → Evidence → Mission Timeline
   - **Gap:** No mission-scoped authorization, no approval gating, no credential abstraction, no idempotency

2. **Infrastructure Registry** (`saathi/infrastructure/connectors/__init__.py`)
   - Secondary path for autonomous tools and agents
   - Called by n8n tools, analytics loops, trend hunters
   - Bypasses some Connector Manager checks
   - **Gap:** Minimal validation, no audit trail

**Additional direct paths** (high-risk, uncontrolled):

- LLM API calls (Anthropic, OpenAI, Groq, DeepSeek, Qwen, GLM, Gemini) — no access control, no rate limiting, no cost tracking
- HTTP requests (raw httpx calls) — from health checks, embedding imports, external fetches
- Telegram Bot handler (`saathi/telegram_bot.py`) — direct to Connector Manager, no authorization per user/mission
- Payment execution (`saathi/execution.py`) — minimal idempotency, no approval gate, no compensation logic
- n8n workflows (`saathi/content_pipeline.py`) — deferred retry to n8n, no SaathiOS-level durability

---

## Current Authorization Model

| Layer | Current Check | Gap |
|-------|---|---|
| **Endpoint** | `_is_authed(request)` — user session only | No mission context, no capability/resource gating |
| **Account Access** | Account owner check only | No mission-scoped account permissions |
| **Capability** | Provider catalog check | No role-based capability restrictions |
| **Risk** | None | No risk classification, no approval thresholds |
| **Rate Limit** | Per-IP login/password only | No per-provider rate limits, no cost caps |
| **Credential** | Raw secrets to adapter | No scoping, no rotation support, no audit |
| **Execution** | Synchronous, fail-fast | No durable queue, no retry strategy, no compensation |
| **Output** | Raw result returned | No sanitization of secrets, no redaction |
| **Audit** | Event emitted optional | Not guaranteed, not structured, not searchable |

---

## Direct Execution Paths (Bypass Risk)

### Path 1: Connector Manager → Adapter (Primary)

```
UI POST /connectors/accounts/{id}/mission
  ↓
Server: execute(account_id, capability, params)
  ↓
Connector Manager:
  1. Check account exists
  2. Check capability valid
  3. Check account status
  4. Check rate limit
  ↓
Adapter (if live): provider.verb(account, params)
  ↓
Result + Event emit
```

**Risks:**
- No mission-scoped authorization (any authed user can execute any account capability)
- No risk classification (high-value actions treated same as reads)
- No approval gate (payments/publishing/deletions all automatic)
- No idempotency tracking (duplicate requests may double-execute)
- No compensation (no rollback for failures)
- Synchronous (timeouts fail the entire request)
- No durable queue (failed execution is lost)

**Evidence:** `saathi/connectors/manager.py:execute()`, `saathi/server.py` lines 315+

---

### Path 2: Infrastructure Registry (Secondary)

```
n8n Tool / Analytics Loop / Trend Hunter
  ↓
registry.execute(capability="...", connector_id="...", account_id="...", params={})
  ↓
Minimal validation (no rate limit check visible)
  ↓
Adapter call
```

**Risks:**
- Bypasses some Connector Manager checks
- No authorization enforcement
- No event emission
- No audit trail
- Called from autonomous scripts (no user context)

**Evidence:** `saathi/infrastructure/connectors/__init__.py`, `saathi/tools/*.py`

---

### Path 3: LLM API Calls (Direct, Uncontrolled)

```
saathi/llm.py:
  - httpx.post("https://api.anthropic.com/v1/messages", ...)
  - httpx.post("https://api.openai.com/v1/chat/completions", ...)
  - httpx.post("https://api.groq.com/openai/v1/chat/completions", ...)
  - httpx.post(deepseek/qwen/glm/gemini endpoints, ...)

No:
  - Access control (anyone can call any LLM)
  - Rate limiting
  - Cost tracking
  - Budget enforcement
  - Fallback routing
  - Failure audit
  - Idempotency
```

**Risks:**
- Budget overruns undetected (no spend limits)
- Denial of service via LLM spam
- No failover to cheaper models
- LLM API failures cascade to caller

**Evidence:** `saathi/llm.py` (direct httpx.post calls)

---

### Path 4: Telegram Bot Handler (Direct Dispatch)

```
Telegram webhook
  ↓
saathi/telegram_bot.py:handle()
  ↓
default_registry().execute(capability="send_text", ...)
  ↓
Adapter sends to Telegram
```

**Risks:**
- No authorization (any webhook caller can send Telegram messages)
- No message validation (no spam/abuse filtering)
- No sender identity (messages appear as SaathiOS, not per-mission)
- No rate limiting per chat
- No user context (can't audit which user triggered action)

**Evidence:** `saathi/telegram_bot.py`, registered webhook endpoint

---

### Path 5: Payment Execution (High-Risk, Partially Addressed)

```
saathi/execution.py:
  1. Order validation
  2. Broker timeout idempotency check (good)
  3. Connector.execute()
  ↓
Result: order filled or failed
```

**Risks:**
- Approval gate missing (no explicit confirmation required)
- Compensation not implemented (no refund workflow)
- No approval trail (no record of who approved)
- No cost limits (unlimited trading size)
- No rate limiting per broker
- Synchronous (broker network issues block entire request)

**Evidence:** `saathi/execution.py`, payment flows

---

### Path 6: n8n Workflow Execution (Deferred Retry)

```
SaathiOS triggers n8n workflow
  ↓
n8n executes, calls webhook back to SaathiOS
  ↓
SaathiOS processes result
  ↓
On failure: n8n retries (deferred to n8n)
```

**Risks:**
- No SaathiOS-level retry logic (dependent on n8n)
- No idempotency enforcement (n8n may retry same payload)
- No compensation (SaathiOS can't roll back n8n actions)
- No cost tracking (n8n actions not visible in spend/audit)
- No rate limiting coordination (n8n and SaathiOS not synchronized)

**Evidence:** `saathi/content_pipeline.py`, n8n callback handling

---

## Credential Handling (Current)

| Component | Credential Flow | Risk |
|-----------|---|---|
| Connector Manager | Account record → `get_with_secret=True` → Adapter | Secrets in memory, no scoping per operation, no access audit |
| LLM Calls | Environment variables → Direct API call | Raw keys in process memory, no access control |
| Telegram Bot | Token in DB → Adapter | Accessible to webhook handler, no per-action scoping |
| n8n | Secrets in n8n vault → n8n-to-SaathiOS callback | SaathiOS never holds keys, but n8n has unlimited access |

**Gaps:**
- No credential scoping (adapter gets full account access)
- No temporary/rotated credentials (always same static secret)
- No credential audit (no log of who accessed which secret)
- No revocation (secret can't be instantly invalidated)
- No backend abstraction (secrets always from `.saathi/connector_key` file)

**Evidence:** `saathi/connectors/accounts.py`, Fernet decryption in adapter calls

---

## Event & Audit Integration (Current)

**What exists:**
- Connector Manager emits events to Event Bus
- Events land in Evidence + Mission Timeline
- Security timeline records auth events

**What's missing:**
- No ToolIntent events (intent creation, validation, authorization, approval)
- No execution queue events (queued, running, retrying, failed)
- No compensation events (rollback, refund, recovery)
- No risk classification events (risk scored, approval requested)
- No credential access audit (who accessed what secret when)
- No authorization decision audit (why was this allowed/denied)

---

## Retry & Idempotency (Current)

| Component | Retry Logic | Idempotency | Risk |
|-----------|---|---|---|
| Connector Manager | None (sync call) | None | Duplicate requests execute twice |
| n8n Tools | Deferred to n8n | n8n-managed | Depends on n8n idempotency |
| Payment Execution | Timeout reconciliation only | Via order ID in broker | Good for trades, incomplete for other actions |
| LLM Calls | Caller retry | None | May resend duplicate prompts |

**Gaps:**
- No queue-based retry (failed executions are lost)
- No exponential backoff (immediate retries overwhelm failing services)
- No jitter (synchronized retry storms)
- No idempotency key registry (no deduplication across requests)
- No dead-letter queue (permanently failed executions discarded)

---

## High-Risk Patterns Requiring Immediate Gating

| Pattern | Current | Should Require |
|---------|---------|---|
| Email send | Auto | L4 approval |
| Social post | Auto | L4 approval |
| Video upload | Auto | L4 approval |
| Drive upload | Auto | L4 approval |
| Calendar event | Auto | L4 approval |
| Payment | Auto | L4 approval (explicit confirmation) |
| Delete action | Auto | L4 approval |
| Telegram send | Auto | L4 approval (per chat) |
| API token creation | Auto | L4 approval |
| Webhook registration | Auto | L4 approval |

---

## Direct Calling Locations (Must Be Migrated)

### Connector Manager Calls
- `saathi/telegram_bot.py` — webhook handler calls directly
- `saathi/tools/n8n_tools.py` — n8n tool wrappers call directly
- `saathi/tools/analytics_loop.py` — autonomous analytics calls directly
- `saathi/tools/trend_hunter.py` — autonomous trend mining calls directly
- `saathi/tools/comment_miner.py` — autonomous comment analysis calls directly
- `saathi/pielts.py` — PIELTS integration calls directly
- `saathi/analytics.py` — analytics module calls directly
- `saathi/server.py` line ~3200+ — UI endpoint for connector execution

### LLM Calls
- `saathi/llm.py` — 8 direct httpx.post() calls to different LLM providers

### Infrastructure Registry Calls
- `saathi/infrastructure/connectors/__init__.py` — autonomous agent capability dispatch

---

## Current Strengths (Keep)

1. **Event Bus integration** — Events already emitted to Evidence + Timeline
2. **Connector Manager single entry point** — Already funneling most calls through one function
3. **Account validation** — Already checks account exists and is connected
4. **Capability validation** — Already checks provider supports requested capability
5. **Rate limit skeleton** — `_rate_ok()` hook exists (placeholder)
6. **Adapter pattern** — Actual SDK calls isolated to adapter layer

---

## Migration Strategy

### Phase 3.1 — Build ToolIntent Schema
- Define immutable intent model with required fields
- Add schema validation
- Create tests for valid/invalid intents

### Phase 3.2 — Build ExecutionGateway
- Single mandatory entry point for all external actions
- Orchestrates: validation → authorization → approval → credential access → execution → sanitization → events
- All existing paths route through this (no bypass)

### Phase 3.3 — Mission-Scoped Authorization
- Define mission-capability matrix (Mr. Yeti can access YouTube/Telegram/Drive, Surmount cannot)
- Implement per-mission credential access control
- Block cross-mission leakage

### Phase 3.4 — Approval Policy
- Classify each capability as L1-L4 (read-only → irreversible)
- L4 (external publish, payment, delete, permission) requires explicit approval
- Approval records immutable and non-reusable

### Phase 3.5 — Credential Manager
- Abstract credential access
- Support Environment, Vault, Keychain backends (start with Environment)
- Credentials scoped to operations, never raw to adapters
- Audit every access

### Phase 3.6 — Durable Queue
- SQLite-backed execution queue
- Persist intent → wait → execute → record result
- Retry with exponential backoff
- Dead-letter for permanent failures

### Phase 3.7 — Idempotency Registry
- Track idempotency keys + operation fingerprints
- Detect duplicate submissions
- Return cached result if duplicate

### Phase 3.8 — Result Sanitization
- Redact API keys, tokens, secrets, stack traces
- Safe logging representation
- No sensitive data escapes

### Phase 3.9 — Migrate Each Path
1. Connector Manager calls (telegram_bot, n8n_tools, analytics, pielts) → ExecutionGateway
2. LLM calls (llm.py 8 endpoints) → Model Router via ExecutionGateway
3. Infrastructure Registry (autonomous tools) → ExecutionGateway
4. Payment execution → add approval gate
5. n8n callbacks → integrate with queue

### Phase 3.10 — Block Bypasses
- Remove direct adapter access
- Remove direct API calls
- Make ExecutionGateway the only path

---

## Migration Milestones

| Milestone | Files | Complexity | Risk |
|-----------|-------|------------|------|
| Build ToolIntent + Gateway | 2-3 new | Low | None (additive) |
| Mission-scoped authz | 3-5 modified | Medium | Blocks unauthorized access |
| Approval policy | 2-3 new | Medium | May require UI for approvals |
| Credential manager | 1-2 new | Medium | Must not break existing adapters |
| Durable queue | 1-2 new | Medium | New database tables |
| Idempotency | 1 new | Low | None (layer) |
| Result sanitization | 1 new | Low | None (filter) |
| Migrate Connector Manager calls | 7 files modified | Low | Each path tested independently |
| Migrate LLM calls | 1 file modified | Medium | Must route through Model Router, not direct |
| Block bypasses | 5+ files modified | Low | Removes dead code |

---

## Timeline Estimate

| Phase | Effort | Duration |
|-------|--------|----------|
| Build ToolIntent + ExecutionGateway | 3-4 days | 4 days |
| Authorization + Approval | 2-3 days | 3 days |
| Credential manager + Queue | 2-3 days | 3 days |
| Idempotency + Sanitization | 1-2 days | 2 days |
| Migrate all paths + Block bypasses | 3-4 days | 4 days |
| Integration testing + Verification | 2-3 days | 3 days |
| **Total** | **13-19 days** | **19 days (conservative)** |

---

## Risks if Phase 3 Is Skipped

1. **Any user can trigger external actions on any mission** (no authorization)
2. **High-risk actions (payments, publishing) automatic** (no approval)
3. **Duplicate execution possible** (no idempotency)
4. **Credentials exposed in logs/errors** (no sanitization)
5. **Failed executions lost** (no durable queue)
6. **Autonomous scripts bypass all audit** (Infrastructure Registry unchecked)
7. **LLM budget uncapped** (no cost control)
8. **No rollback/compensation** (irreversible actions permanent)
9. **Evidence/Timeline incomplete** (missing intent + queue events)
10. **Multi-agent coordination impossible** (no standardized intent flow)

---

## Recommendation

**PROCEED WITH PHASE 3 IMMEDIATELY**

Phase 3 is foundational for:
- Multi-user safe operation
- Cost control and budget enforcement
- Audit compliance
- Multi-agent coordination
- Production readiness

Do not proceed to production multi-agent deployment (Phase 4) without Phase 3 security/governance layer in place.

---

**Next:** Phase 3.1 — Build ToolIntent Schema (awaiting approval)
