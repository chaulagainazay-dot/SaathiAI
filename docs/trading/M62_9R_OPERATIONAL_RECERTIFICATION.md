# M62.9R — End-to-End Paper Trading Operational Re-certification

**Verdict:** `M62_9R_COMPLETE_WITH_LIMITATIONS`
**Branch:** `milestone/m61-backend-workflow-persistence`
**Starting / ending HEAD:** `918b079` (no code changes; documentation/evidence only)
**Date:** 2026-07-28
**Scope:** bounded, local, single-host, localhost-only paper-trading simulation.

This document records the independent re-certification. Evidence lives in
`docs/trading/m62_9r_evidence/`. The concise verdict report is
`docs/trading/M62_9R_FINAL_REPORT.md`.

---

## 1. Baseline verification

```
pwd                 /Users/macbookpro/SaathiAI
git branch          milestone/m61-backend-workflow-persistence   ✓
git rev-parse HEAD  918b079f684d1c92f6d25de1516443d92fc84685      ✓
git status --short  ?? docs/design-spec/   (untracked, preserved, never staged)
```

Branch and SHA match the authoritative baseline. `docs/design-spec/` left untouched.

## 2. Why the prior attempt was blocked, and what changed

The earlier `M62.9_INCOMPLETE_BLOCKED` cited six gaps. Each is now independently re-verified as
present and tested:

| Prior blocker | Now |
|---------------|-----|
| M62.6 reconciliation absent | `paper_trading/reconciliation.py`, 7 dimensions, test_m62_6 (22) PASS |
| M62.7 circuit-breaker safety absent | `safety/` service+evaluator, test_m62_7 (41) PASS |
| M62.8 browser workspace absent | 11 `/trading/*` routes, test_m62_8 (4) PASS |
| corrupted replay failure injection absent | corrupted-checkpoint + quality tests in test_m62_2 PASS |
| SQLite interruption failure injection absent | `test_atomic_trip_rolls_back` + `test_interrupted_transaction_leaves_no_partial_state` PASS |
| committed trading-path manifest absent | `m62_9r_evidence/TRADING_PATH_MANIFEST.{json,md}` committed |

## 3. Read-only architecture & authority audit

### Canonical mutation path (single authority chain)

`OrderIntent → Trading Guardian (veto) → Approval → PlatformAgentRuntime →
ExecutionGateway.execute_registered_tool → registered paper tool → PaperTradingService →
PaperBroker → PaperOrder → immutable fills → accounting → reconciliation → safety → alert/halt`.

Verified in `paper_trading/orchestration.py` (module docstring names the exact chain; the API and
any runtime call **only** `submit_via_gateway` / `cancel_via_gateway` / `process_event_via_gateway`
/ `reset_via_gateway`, which each call `gw.execute_registered_tool`). HTTP endpoints
(`api.py:2488-2540`, `2736-2745`) call these helpers plus `ctx.require_permission(...)`, never the
service directly.

### Path classification

| Path | Class |
|------|-------|
| HTTP → `*_via_gateway` → Gateway → registered tool → service | SAFE_CANONICAL |
| Read endpoints (`GET /paper/...`, reconciliation runs, safety states/trips/alerts, evidence) | READ_ONLY |
| `run_sweep` by system actor | SYSTEM_BOUNDED |
| `saathi/repair/loop.py` (auto-dev code repair, subprocess) | OUT_OF_SCOPE (never touches financial state, never pushes/deploys) |
| `config.py HOST=0.0.0.0` env default | LEGACY_ISOLATED (launcher overrides to 127.0.0.1) |
| Any executable live-broker / eval / socket / auto financial-repair | **absent** (no UNSAFE/BLOCKING path found) |

No executable unsafe bypass exists.

### Registered tools (only mutation authority — 8)

`paper.order.submit`, `paper.order.cancel`, `paper.order.process_event`,
`paper_safety.trip`, `paper_safety.acknowledge`, `paper_safety.request_reset`,
`paper_safety.reset`, `paper_safety.run_sweep`.

### Actor / role authority

`is_agent_actor(ctx)` in `safety/service.py` (`_require_human`) blocks agents from configure, trip,
acknowledge, request_reset, reset. Sweeps are the only protective action a SYSTEM actor may run.
Role permission tiers in `models.py` isolate viewer (read) / operator (propose…reset_request) /
owner (halt, configure, authorize repair, reset).

## 4. Repair non-execution proof

`authorize_repair_plan` (`reconciliation.py:693-710`) marks status `AUTHORIZED` and audits
`outcome="authorized_not_executed"`. No `execute_repair`/`apply_repair`/`repair_account`/
`auto_repair`/`fix_financial_state` executable symbol exists. `RepairPlan.to_public()` reports
`executes_automatically: False`. Corruption remains until externally corrected — proven by
`test_repair_plan_generated_but_never_executed` and the corruption battery in test_m62_6.

## 5. Reset battery (fail-closed)

`execute_reset` (`safety/service.py:654-755`) runs, and requires **all** of:
`state_resettable`, `acknowledged`, `breaker_version_match`, `no_broader_breaker`,
`reconciliation_clean`, `accounting_invariants`, `threshold_cleared`, `approval_valid`
(single-use, tenant-scoped, payload/scope-matched, not agent-self-approved). `allowed = all(checks)`.
On denial: no state change, no approval consumption, halt retained. On success: protective state →
NORMAL, approval consumed **atomically** within the same `persist_reset` transaction, account
unhalted only if no other blocker remains; returns `financial_state_modified: False`. Orders, fills,
positions, cash, reservations, and ledger are never touched.

## 6. Fault injection (the two prior gaps)

- **Corrupted replay** — hash-mismatch / out-of-order / malformed inputs classified and rejected
  fail-closed; corrupted checkpoint restore rejected (`test_m62_2`).
- **SQLite interruption** — `test_atomic_trip_rolls_back` injects a RuntimeError inside
  `persist_trip`; the whole trip transaction rolls back: no partial halt, no orphan trip/alert,
  state stays NORMAL, the error surfaces in the sweep manifest (not swallowed). A failed
  approval-consume likewise rolls back leaving the account clean.

## 7. Determinism

Backtest result hash equal across three runs; market-data replay hash stable; long-duration
simulation financial outputs identical across two independent runs (2240 orders, 6720 events each).

## 8. Long-duration simulation & performance

`m62_9r_evidence/long_duration_harness.py` (scaled from the M62.9 harness): 4 tenants, 16 accounts,
2240 orders, 6720 events, partial fills, duplicate-event idempotency, restart recovery. Result:
invariants clean, 0 duplicate fills, no duplicate accounting after restart, order p95 1.567 ms /
p99 1.801 ms, 376.5 orders/s, 38.9 MB peak RSS, no unbounded growth. Single-host localhost only.

## 9. Test execution

Full suite `5182 passed, 1 skipped, 0 failed`. Trading suites 213 pass; runtime/gateway/authz 150
pass; frontend node tests 130 pass; lint clean; production build succeeds; `git diff --check` clean.
See `m62_9r_evidence/TEST_RESULTS.md`.

## 10. Limitations (bounded, non-safety)

Single-host SQLite · localhost-only · fixture/replay market data · local-only alerts · no
distributed scheduler · server-side reset-approval creation · limited manual config UI ·
`config.py` HOST env default `0.0.0.0` (launcher overrides) · browser live-walkthrough verified via
component tests + static inspection rather than a fresh screenshot drive this session.

## 11. Certification scope statement

M62.9R certifies only the bounded SaathiOS local paper-trading system described in the evidence and
trading-path manifest. PlatformAgentRuntime remains the canonical agent runtime; ExecutionGateway
remains the sole authority for registered mutation tools; Trading Guardian remains an independent
fail-closed veto; reconciliation may halt but never repairs financial state; acknowledgement does
not remove a halt; human approval cannot override failing technical safety checks; reset cannot
modify orders, fills, positions, cash, reservations, ledger, or repair corruption; the browser is an
operator interface, not a financial authority. Paper trading remains simulation-only, long-only,
fixture/replay-data-based, single-host, localhost-only. No live broker, real funds, leverage, margin,
short selling, derivatives, borrowing, withdrawal, production deployment, autonomous capital
allocation, external rollout, or automatic repair is authorized. No push, merge, or deploy performed.
