# SaathiOS Trading Completion Roadmap

Dynamic program controller. Updated at the end of every milestone.

**Program rule: LIVE DATA YES · LIVE ORDERS NO · PAPER FIRST · SHADOW SECOND ·
REAL EXECUTION LAST AND ONLY AFTER EXPLICIT USER AUTHORIZATION.**

Statuses: `NOT_STARTED` · `DISCOVERY` · `IMPLEMENTING` · `VALIDATING` ·
`CERTIFIED` · `CERTIFIED_WITH_LIMITATIONS` · `BLOCKED` · `DEFERRED` · `REJECTED`

---

## Completed before this program

| ID | Title | Status | SHA |
|---|---|---|---|
| ECC | Engineering harness hardening | `CERTIFIED` | `954daa4` |
| TA-EVAL | TradingAgents qualification | `CERTIFIED_WITH_LIMITATIONS` | `a766b69` |
| T-NEXT-4 | Execution integrity | `CERTIFIED_WITH_LIMITATIONS` | `07f4f2c` |
| T-NEXT-4.1 | Reconciliation gate enforcement | `CERTIFIED_WITH_LIMITATIONS` | `d644398` |
| TEST-INFRA-1 | Offline suite hang isolation | `CERTIFIED` | `0d10dff` |
| TEST-INFRA-2 | CI and test-state isolation | `CERTIFIED_WITH_LIMITATIONS` | see below |

---

## Stage A — Test / environment foundation

### A1 · TEST-INFRA-2 — CI and test-state isolation

- **Status:** `CERTIFIED_WITH_LIMITATIONS` — commits `1` `2` `3` below
- **Dependency:** TEST-INFRA-1 ✓
- **Risk:** low · **Authority impact:** none
- **Why first:** TEST-INFRA-1 proved that one unprotected home-directory store
  (`SecurityStore`) both deadlocked the suite and wrote into the operator's live
  security database. An audit found **44 more source files** persisting state
  under `Path.home()` — ~30 distinct SQLite databases, JSON stores and logs under
  `~/.saathi` (accounts, missions, evidence, events, knowledge library,
  production automation, …), **none** with an environment override. Every later
  milestone adds stores and tests; building market-data infrastructure on a test
  environment that mutates real user data would make every subsequent
  certification untrustworthy.
- **Findings:**
  - 44 files with unprotected home-path persistent stores
  - ~30 distinct `~/.saathi` databases / JSON stores / logs
  - trading-plane stores already had `SAATHI_*_DB` overrides; non-trading did not
  - tests rewrite tracked `docs/evidence/m25/*` files
  - no CI workflow exists
- **Approach:** redirect `HOME` for the test session in the root `conftest.py`
  rather than patching 44 call sites. `Path.home()` and `expanduser("~")` both
  resolve `$HOME` on POSIX, and the root conftest is imported before any `saathi`
  module, so module-level `Path.home()` constants are covered too.
- **Result:** offline suite **7641 passed / 0 failed / 643.76 s**; trading
  regression **294 passed / 0 failed**; 11 new isolation tests; working tree
  clean after a full run; `~/.saathi` untouched.
- **Defects found beyond scope:** a **protection bypass** in
  `agentdev/config_protection.py` (symlinked `$HOME` made `~/.claude/settings.json`,
  `~/.ssh/id_rsa`, `~/.aws/credentials` classify UNPROTECTED) — fixed with
  regression tests; and `inference/ops/state.py` writing live state into tracked
  `docs/evidence/m26`, found by fresh-context review.
- **Limitation:** `SAATHI_EVIDENCE_ROOT` overlaps the pre-existing
  `saathi/runtime_paths.py` mechanism. Documented as top infra debt.
- **Not done:** suite runtime unchanged (~10.7 min); per-store `SAATHI_*_DB`
  overrides still absent for the 44 files; CI workflow written but never executed.
- **Evidence:** `docs/testing/test-infra-2/`
- **Next:** B1 · MD-1.

### A2 · CI lanes

- **Status:** `PARTIAL` · **Dependency:** A1 ✓
- OFFLINE CORE and TRADING REGRESSION lanes written in
  `.github/workflows/offline-core.yml`, including a step that fails the build if
  a test run mutates tracked files. **Never executed** — no CI history exists.
- Remaining lanes: MARKET DATA CONTRACT, BROWSER, LIVE MARKET DATA CANARY.
- Lanes: OFFLINE CORE · MARKET DATA CONTRACT · TRADING REGRESSION · BROWSER ·
  LIVE MARKET DATA CANARY. Core CI must never require a live external API.

---

## Stage B — Market data foundation

### B1 · MD-1 — Canonical market data contract *(highest-value gap)*

- **Status:** `DISCOVERY` — **selected as the next milestone** · **Dependency:** A1 ✓
- **Risk:** medium · **Authority impact:** none (read-only, upstream of proposals)
- **Measured gap:** `grep -rn available_at saathi/ tests/` returns **one hit, and
  it is a comment**. The entire codebase is `as_of`-only. This is precisely the
  look-ahead defect identified in the TradingAgents evaluation
  (`docs/evaluations/tradingagents/LOOKAHEAD_AUDIT.md`, score 6/10) — recorded
  there as a defect to avoid, and currently unfixed here.
- Also to resolve: **4 duplicate `AssetClass` enums** (`investment.py`,
  `platform/trading_models.py`, `tg/broker_sandbox/models.py`,
  `tg/market_data/models.py`) and **2 competing quote models** (`MDQuote`,
  `Quote`).

### MD-1 · Canonical point-in-time market data contract

- **Status:** `CERTIFIED_WITH_LIMITATIONS` · SHA `9826796`
- `saathi/platform/market_data/contract.py`. Four timestamps — event_timestamp,
  as_of, **available_at**, received_at — and `visible_at()`, the only correct
  look-ahead filter. Before this, `grep available_at` returned one hit and it was
  a comment.
- Asset-class enums converged by adaptation, not deletion. `investment.py` left
  alone: different domain (personal investment categories).
- Fresh-context review found two defects, same root cause: `Decimal("0")` as a
  default conflated *absent* with *zero*. A one-sided quote returned spread -100
  and mid 50; a bar with `high=100, low=open=close=0` passed. Both fixed.
- **Tests:** 54. **Limitation:** no provider adapter; existing consumers not yet
  migrated onto the canonical types.

### NEPSE-CAL-1 · Authoritative trading calendar

- **Status:** `CERTIFIED_WITH_LIMITATIONS` · SHA `a3a1945`
- **Defect found:** `tg/historical/calendars.py` declared NEPSE as
  `open_weekdays={0,1,2,3,4}` — Monday–Friday. **NEPSE trades Sunday–Thursday,
  closed Friday–Saturday.** Wrong at both ends; ~2 days in 5 misclassified in
  every backtest built on it. Its holidays were self-annotated "(example
  fixture)".
- New `saathi/platform/nepse/calendar.py`: weekly pattern CONFIRMED; holidays are
  a versioned sourced dataset; uncovered trading weekday is UNKNOWN and fails
  closed; ships zero fabricated holidays; `Asia/Kathmandu` UTC+05:45 no DST via
  ZoneInfo.
- Fresh-context review caught my own bug: `__post_init__` promoted any year with
  a holiday into `covered_years`, so one 2027 holiday made an unbacked June 2027
  Tuesday report as trading. Removed.
- **Tests:** 34. **Top follow-up:** the Monday–Friday calendar is still in the
  tree and still used by `historical/import_service.py`. Migrating those
  consumers changes what their historical outputs mean and needs its own work.

### NEPSE-CAL-1.1 · Legacy calendar consumer migration

- **Status:** `NEPSE_CALENDAR_LEGACY_MIGRATION_CERTIFIED_WITH_LIMITATIONS` ·
  **Policy:** `REQUIRE_CALENDAR_COVERAGE`
- The historical NEPSE surface now delegates to the canonical calendar; the
  independent Monday-Friday policy and illustrative holiday dates were removed.
- Raw import retains Sunday-Thursday candidates with
  `HOLIDAY_COVERAGE_UNKNOWN` provenance. Certified backtests fail closed until
  every tested year has genuine versioned coverage. Friday/Saturday remain
  confirmed closed.
- Generated artifacts carry calendar version/source/coverage/policy. Old
  unversioned NEPSE artifacts remain labelled
  `NEPSE_CALENDAR_V1_LEGACY_INVALID`; they are not silently reclassified.
- Evidence: `docs/trading/nepse/cal-1-1/`.
- **Regression:** 7787 passed, 8 explained environment skips, 12 deselected,
  0 failed. **Next:** `SAFE_TO_CONTINUE -> NEPSE-TXN-1`; genuine export
  headers remain required before importer schemas become `VERIFIED`.

### NEPSE-TXN-1 · Normalized external transaction import

- **Status:** `NEPSE_TRANSACTION_IMPORT_CONTRACT_CERTIFIED_WITH_LIMITATIONS` ·
  **Dependency:** NEPSE-1, MD-1, NEPSE-CAL-1.1 ✓
- Canonical immutable transaction and import-result models, Decimal money,
  unsigned whole-share quantity, explicit trade/settlement/availability/receipt
  time, stable transaction IDs, visible duplicate/conflict states, deterministic
  reason codes, and bounded untrusted CSV/TSV parsing.
- Every accepted transaction resolves through `NepseInstrument`. Import is a
  proposal only: zero Fund Ledger, position, cash, OMS, gateway, guardian,
  construction, or risk mutation.
- Meroshare, TMS, and Nepal Share mappings remain
  `SOURCE_SCHEMA_UNVERIFIED`; no real source compatibility is claimed.
- **Regression:** 52 focused transaction tests, 284 NEPSE/MD/calendar/
  historical/market-data tests, 327 ledger/authority tests, and canonical
  offline suite `7844 passed, 8 skipped, 12 deselected, 0 failed`.
- **Evidence:** `docs/trading/nepse/txn-1/`.
- **Next dependency recommendation:** MD-1.1 venue consistency, then
  NEPSE-SCHEMA-1 when genuine headers exist. If headers remain unavailable,
  NEPSE-LEDGER-1 may proceed as contract design over synthetic normalized
  transactions only; no ledger application is authorized.

### MD-1.1 · Venue consistency & instrument identity hardening

- **Status:** `CERTIFIED_WITH_LIMITATIONS` · **Dependency:** MD-1, NEPSE-TXN-1 ✓
- Canonical venue identity validation now rejects contradictory instrument,
  market, venue, and asset-class combinations. Generic registration and
  normalization no longer default omitted venues to XNAS; explicit NEPSE
  identity derives NEPSE, and unknown venues fail closed.
- Historical NEPSE imports enforce NPR, Asia/Kathmandu, and the canonical NEPSE
  calendar even through generic local-file paths. Explicit US/XNAS fixtures
  remain supported and documented as intentional.
- **Regression:** 15 MD-1.1 tests, 274 NEPSE/MD-1/historical/market-data tests,
  and 328 authority tests passed. Existing TXN-1 semantics and source-schema
  status remain unchanged.
- **Evidence:** `docs/trading/md-1-1/`
- **Next:** `NEPSE-SCHEMA-1` when genuine headers are available; otherwise
  `NEPSE-LEDGER-1` contract design only over synthetic transactions.

### NEPSE-1 · Instrument master + portfolio file import

- **Status:** `CERTIFIED_WITH_LIMITATIONS` · **Dependency:** A1 ✓
- **Risk:** low · **Authority impact:** none (read-only, no ledger write)
- **Source:** teardown of `nepseportfoliotracker.app` — 9 screens, 7 backend
  requirements. This milestone builds the two that are unblocked.
- **Built:** `saathi/platform/nepse/` — instrument master (identity, 15-sector
  taxonomy, NEPSE conventions: lot 10, tick 0.10, whole shares, `Asia/Kathmandu`)
  and file importers (Meroshare / TMS / Nepal Share) with a fail-closed trust
  model.
- **Not built, deliberately:** no second portfolio store. Import produces a
  proposal; the Canonical Fund Ledger stays the sole books authority.
- **Tests:** 47 passed. Trading regression 286 passed / 0 failed.
- **Blockers carried forward:**
  - `NEPSE_IMPORT_SCHEMAS_UNVERIFIED` — column aliases derived from public
    descriptions, not real exports. Needs one genuine export of each to pin.
  - `NEPSE_LIVE_DATA_BLOCKED_PROVIDER_ACCESS` — 6 of 9 screens need a live feed;
    no scraping, so this is a licensing decision.
- **Evidence:** `docs/trading/nepse-1/`
- **Next:** NEPSE-2 (apply an ImportResult to the ledger) once schemas are pinned.

### B2 · MD-2 — Instrument master
### B3 · MD-3 — Provider interface
### B4 · MD-4 — Provider qualification system

All `NOT_STARTED`, dependent on B1.

---

## Stage C — Crypto live market data (spot only)

`C1` reference data · `C2` REST · `C3` WebSocket — all `NOT_STARTED`, dependent on B3.
No derivatives, no leverage, no futures. Public read-only endpoints only.

## Stage D — NEPSE live market data

`D1` instrument master · `D2` market calendar · `D3` live quote adapter ·
`D4` historical — roadmap delivery stages remain `NOT_STARTED`; canonical
calendar correctness groundwork exists from NEPSE-CAL-1/1.1.

**Existing seed, verified:** `saathi/platform/tg/historical/adapters/nepse.py`
(93 lines, **local file only, no network**) and
`saathi/platform/tg/historical/calendars.py`. NEPSE-CAL-1.1 removed its
independent Monday-Friday/illustrative-holiday implementation. A sourced annual
holiday dataset is still required before any NEPSE backtest can be certified.

**Standing constraint:** no scraping around access controls. If official
real-time access requires a licence, deliver adapter contract + replay/mock +
provider qualification report and mark
`NEPSE_LIVE_DATA_BLOCKED_PROVIDER_ACCESS`.

---

## Stages E–V

`E` data quality · `F` TA-1 research evidence · `G` qualitative research ·
`H` decision journal · `I` strategy/signal · `J` backtest validation ·
`K` portfolio construction · `L` portfolio risk v2 · `M` Trading Guardian v2 ·
`N` OMS market adaptation · `O` reconciliation v2 · `P` paper trading ·
`Q` shadow trading · `R` observability · `S` operational safety · `T` security ·
`U` shadow certification — all `NOT_STARTED`.

**`V` live canary — `BLOCKED_BY_DESIGN`.** Requires explicit user authorization.
Will not be started automatically under any circumstance.

---

## Canonical authority path (unchanged, non-negotiable)

### NEPSE-LEDGER-1 (certified with limitations)

Canonical NEPSE external transactions now reconcile to immutable, proposal-only records. The Fund Ledger remains sole books authority; source schemas remain unverified and no automatic application is enabled.

### NEPSE-DATA-1 (qualified with license required)

Research identified licensed NEPSE feed vendors as the legitimate production path. Public portals remain research/replay sources until written automation and redistribution terms are obtained.

### NEPSE-HIST-1 (certified with limitations)

Canonical point-in-time historical bars, dataset manifests, validation, revision metadata, and deterministic replay are available without a live NEPSE feed. Licensed historical data remains an external dependency.

```
Research / Data / Models / Agents
   ↓  Structured Research Evidence
   ↓  TradingIntentProposal
══════ LLM AUTHORITY ENDS HERE ══════
   ↓  PortfolioConstructionEngine
   ↓  PortfolioRiskEngine
   ↓  Trading Guardian
   ↓  Approval
   ↓  ExecutionGateway
   ↓  OMS → Execution Adapter → Fills
   ↓  Canonical Fund Ledger
   ↓  ReconciliationAuthority
```
