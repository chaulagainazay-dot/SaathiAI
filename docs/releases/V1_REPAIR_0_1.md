# SaathiOS v1 — Repair 0 (Secrets) + Repair 1 (Execution Layer)

**Date:** 2026-07-10 · **Branch:** `milestone/m7-security-engine` · **Rollback point:** `d1736ed`
Scope lock: secret containment + execution-layer restore only. No BFF, Event Bus, Chat, Code Workspace, Cowork, or UI work.

---

## Repair 0 — Emergency Secret Containment

### State (Step 0.1)
- Branch `milestone/m7-security-engine`, HEAD `d1736ed`, tree clean except staged release docs.
- Branch **is** on `origin/milestone/m7-security-engine` (pushed).
- All secret values redacted in every report/command below.

### Findings & actions
| Finding | Reality | Action |
|---|---|---|
| HF push token in `git remote -v` (`hf` remote) | Token lived **only in local `.git/config`**, never committed to tree/history | `git remote set-url hf https://huggingface.co/spaces/Baadar/baadar-ai` — token stripped. `git remote -v` now contains no `@credential`. |
| `firebase-admin.json` committed at root | **Not tracked** (`git ls-files` empty, **0 history commits**); already gitignored (line 12); local file mode `600` | Left secure local copy in place; added example template + broadened ignore patterns. |
| `.env`, `secrets/`, `.env.bak` | Not tracked; already gitignored | Reinforced with pattern rules. |
| Other credential files (service-account/oauth/pem/session) | None tracked; 4 cred-adjacent **scripts** read from env/args, no literals | Verified via `git grep` for `AIza…/hf_…/sk-…/BEGIN …/xox…` — clean. |

### Changes
- `.gitignore`: added pattern exclusions — `.env.*` (keep `.env.example`), `*-admin.json` (keep `*-admin.example.json`), `*serviceAccount*.json`, `*service-account*.json`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*-credentials.json`, `*_credentials.json`, `*.token`, `token.json`, `oauth*.json`, `*session*.json`, `!*.example.json`.
- Added `firebase-admin.example.json` — placeholder values only, no real IDs/keys.

### History assessment (Step 0.5)
**`NOT PRESENT IN PUSHED HISTORY`.** The HF token existed only in local git config; `firebase-admin.json` was never tracked (0 commits). No `git filter-repo`/BFG history rewrite required. No force-push planned.

### Rotation status (Step 0.4) — honest
- **HF token: ROTATE MANUALLY.** It was printed to this session's terminal during the audit → treat as compromised. Revoke + reissue at `huggingface.co/settings/tokens`. Old token remains **active until you revoke**. I have no provider access; cannot rotate or verify rotation.
- **Firebase service account: optional/precautionary.** Never leaked through git. If desired, rotate at Firebase Console → Project Settings → Service accounts.

### Repair 0 acceptance
- [x] No secret in `git remote -v`
- [x] `firebase-admin.json` not tracked + gitignored
- [x] Secret files gitignored (exact + pattern)
- [x] Safe example config exists
- [x] Rotation requirements documented honestly
- [x] No secret value in this report

---

## Repair 1 — Restore the Universal Secure Execution Layer

### Root cause (Step 1.1)
`saathi.execution` was a **module/package name collision**:
- `saathi/execution.py` — the M5 **finance** trade-execution module (`ExecutionIntent`, `ExecutionSide`, `OrderType`, finance `ExecutionStatus`, `PaperConnector`, `ReplayConnector`, `BrokerRegistry`, `ExecutionService`), wired to `saathi.investment/portfolio`.
- `saathi/execution/` — the ADR **ExecutionGateway** package (`ToolIntent`, `gateway`, `state`, `results`, `errors`, `adapters/`, `orchestrators/`, `queue/`).

Python resolves `saathi.execution` to the **package**, whose `__init__.py` was **empty** → shadowed the finance module → 3 test files (`test_execution.py`, `test_trade_journal.py`, `test_m5_explainability.py`) failed at collection. The gateway package was also unexported and unused by the server.

### Canonical public API (Step 1.2)
- Moved `saathi/execution.py` → `saathi/execution/trade.py` (`git mv`, history preserved).
- Wrote `saathi/execution/__init__.py` exporting **both** concerns via one stable surface (`__all__`), Repair-1 mandated names present: `ToolIntent, ExecutionGateway, ExecutionResult, RiskLevel, ApprovalDecision` (+ `ExecutionContext, SanitizedResult, Evidence, AuditTrail, IntentState, ApprovalStatus`, full error hierarchy, and finance symbols).

**Name-collision resolution (documented, reversible):** both subsystems defined `ExecutionStatus`. Bare `ExecutionStatus` = **finance** order status (preserves the 3 pre-existing tests, zero test edits); gateway result status exported as **`ToolExecutionStatus`**. `RiskLevel` = the gateway/`state` enum (ToolIntent-local risk hint stays at `saathi.execution.toolintent.RiskLevel`). `ApprovalDecision` = alias of `ApprovalStatus`. This is the single deviation from Repair 1's literal symbol list — flip trivially by swapping the two `ExecutionStatus` names in `__init__.py` if gateway should own the bare name.

### Correctness fixes (beyond import restore)
- **Dropped-coroutine defect:** `gateway.enqueue_for_execution` called async `queue.enqueue()` without await → coroutine silently discarded, enqueue was a no-op → **idempotency/duplicate-detection never ran** (violated invariant #6). Added `_run_coro()` helper (runs a coroutine to completion whether or not a loop is active) and awaited the enqueue.
- **MemoryQueue internal bug:** `enqueue()` tested `if self.is_duplicate(...)` on the **coroutine object** (always truthy) → would have falsely raised "Duplicate" once enqueue actually ran. Fixed to `await self.is_duplicate(...)`.

### Narrow reference path wired + tested
`tests/test_execution_gateway.py` (3 tests): public-API surface guard, finance+gateway coexistence, and one reference `ToolIntent → ExecutionGateway` run (validate → authorize → classify risk → approve → queue → execute local adapter → sanitize → evidence) asserting SUCCESS + zero external cost for confidential data. Package `test_integration.py` reference script also runs green (video + LLM paths).

### Scope respected
Gateway is importable, coherent, tested, and exercised by one reference path. **Not** force-wired into every side-effect route (existing paths still reach the Connector Registry directly) — full enforcement is Phase 3.2. No durable queue, credential provider, or retry engine added.

### Tests
| Gate | Before | After |
|---|---|---|
| Collection errors | 3 | **0** |
| Passed | 832 | **854** (+22: 19 finance recovered, 3 gateway new) |
| Failed | 9 | **9** (unchanged — all out-of-scope: event-bus ×5, BFF ×2, ai_lab ×1, client_intake ×1) |
| Skipped | 1 | 1 |
| Server import | OK (296 routes) | OK (296 routes) |
| Runtime | 6m37s | 6m36s |

**Zero regressions.** All 3 previously-uncollectable files pass (19 tests). Remaining 9 failures are the separately-scoped Event Bus and BFF repairs, explicitly excluded from this task.

### Files changed
- `.gitignore` (hardened) · `firebase-admin.example.json` (new)
- `saathi/execution.py` → `saathi/execution/trade.py` (moved)
- `saathi/execution/__init__.py` (canonical public API)
- `saathi/execution/gateway.py` (`_run_coro` + awaited enqueue)
- `saathi/execution/queue/memory.py` (awaited `is_duplicate`)
- `tests/test_execution_gateway.py` (new, 3 tests)

### Still blocked for v1 (unchanged by this task)
Event Bus `subscribe()` (5 tests), BFF contract/dream_pct (2 tests), studio tracking (2 tests); 6-mode Chat, Code Workspace, Cowork unbuilt; gateway not yet enforced on all side-effect paths. See `V1_CAPABILITY_AUDIT.md`.
