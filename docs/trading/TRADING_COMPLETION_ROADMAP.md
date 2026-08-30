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
`D4` historical — all `NOT_STARTED`.

**Existing seed, verified:** `saathi/platform/tg/historical/adapters/nepse.py`
(93 lines, **local file only, no network**) and
`saathi/platform/tg/historical/calendars.py` with a NEPSE calendar whose holiday
set is annotated *"illustrative operator-supplied set; not exhaustive"* — a
correctness blocker for any NEPSE backtest that must be resolved in D2.

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
