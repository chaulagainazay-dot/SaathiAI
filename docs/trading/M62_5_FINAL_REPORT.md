# M62.5 — Deterministic Paper Broker & Durable Order Lifecycle — Final Report

**1. Verdict:** `M62_5_COMPLETE_WITH_LIMITATIONS` (bounded limitations in §42 are the
intended M62.5 scope; reconciliation certification is deferred to M62.6).

**2. Starting branch / SHA:** `milestone/m61-backend-workflow-persistence` @ `3e6ae98`.

**3. Ending branch / SHA:** `milestone/m61-backend-workflow-persistence` @ commit
`feat(trading): add deterministic paper broker lifecycle` (see §4).

**4. Commits:** one scoped commit adding the `saathi/platform/paper_trading/`
package, RBAC permissions, tool registration, `/paper` API, tests, docs, evidence.
No push, no merge, no deploy.

**5. Working-tree state:** clean except the pre-existing untracked `docs/design-spec/`
(preserved, never staged).

**6. Reuse audit:** see `m62_5_evidence/REUSE_AUDIT.md`. Reused canonical
`OrderIntent`, `TradingGuardian`, M62.2 market data (adapter), RBAC/Approval Center,
`PlatformExecutionContext`, `ExecutionGateway`, `tool_runtime`.

**7. Legacy-code disposition:** legacy M5 `saathi.execution.trade` remains
`LEGACY_ISOLATED` — not imported by `api.py` or `paper_trading`, unreachable. The
prohibited `m49.financial_execution_stub` stays manifest-`PROHIBITED`.

**8. New modules:** `paper_trading/{__init__,models,broker,store,service,execution_tool,orchestration,fixtures}.py`
(~1.8k LOC).

**9. Paper-account domain:** `PaperAccount` (durable, tenant/workspace/project scoped,
positive starting cash, Decimal cash/reserved/available, realized P&L, status
`DRAFT/ACTIVE/HALTED/CLOSED`, `PAPER` env, version). No margin/borrow/short.

**10. Intent/order separation:** M62.1 `OrderIntent` (proposal) vs durable
`PaperOrder` (broker order created only after all gates). No direct
recommendation→order transition.

**11. Order lifecycle:** validated `BrokerOrderState` machine
(`PENDING_VALIDATION→ACCEPTED→OPEN→PARTIALLY_FILLED→FILLED`, plus
`CANCEL_PENDING/CANCELLED/REJECTED/EXPIRED/FAILED`), optimistic concurrency,
audited transitions. See `PAPER_ORDER_LIFECYCLE.md`.

**12. Supported order types:** `MARKET`, `LIMIT` only (STOP/bracket/OCO rejected).

**13. Long-only enforcement:** SELL ≤ available long position; oversell, SHORT side,
and negative quantity rejected before any write.

**14. Guardian integration:** independent `TradingGuardian.evaluate` runs before
every submission with account cash/positions/exposure/concentration + market
quality/state; veto blocks submission, is persisted on the intent, and is marked
`is_trade_approval=false`. May veto even post-approval.

**15. Approval integration:** server-owned Approval Center; tool-runtime scope check
+ service verification with **atomic consumption** in the submission transaction;
cross-tenant/expired/reused/self-approval rejected. See `PAPER_APPROVALS.md`.

**16–18. Runtime / Gateway / registered tools:** mutations flow
Runtime → `ExecutionGateway.execute_registered_tool` → `paper.order.{submit,cancel,process_event}`
→ `PaperTradingService` → `PaperBroker`. Tools are `LOCAL_MUTATION` (never
`FINANCIAL_EXECUTION`). See `PAPER_EXECUTION_AUTHORITY.md`.

**19. Broker determinism:** stateless engine; identical hashed inputs → identical
decision/fill/`result_hash` (proven; `EVIDENCE_MANIFEST.json`).

**20. Fill assumptions:** conservative next-event fill at adverse touch + slippage;
limit never crosses unfavorably; bar CLOSE used for both touches (no favorable OHLC
sequencing); non-VALID quality / non-OPEN market → no fill.

**21. Partial fills:** participation-capped, floored to whole units; remainder stays
open; exact remaining quantity; immutable append-only fills.

**22. Cash reservation:** BUY reserves notional+fee+slippage; released
proportionally on fill and fully on completion/cancel; never negative; no
double-reserve.

**23. Position reservation:** SELL reserves available long quantity; released on
cancel; prevents double-sell.

**24. Accounting:** Decimal cash ledger, positions, avg cost, realized/unrealized
P&L, equity; invariants reconcile (`check_account_invariants`). See
`PAPER_ACCOUNTING.md`.

**25. Fees & slippage:** versioned `FeeModel`/`SlippageModel`; every fill persists
model versions + computed fee/slippage; costs always in P&L.

**26. Idempotency:** multi-layer — intent idem key, unique order idempotency index,
gateway tool-runtime idempotency, market-event dedup by `(order, event_hash)`,
cancel idempotency; same key+different payload → conflict.

**27. Cancellation:** through the Gateway; open/partial cancellable; releases
reservation; retains fills; idempotent; cross-tenant rejected.

**28. Expiry:** `DAY` modeled; `GTC` deferred.

**29. Halt behavior:** account halt (owner+) rejects new submissions, preserves
state read-only (bounded fail-closed policy; existing open orders frozen for M62.6).

**30. Persistence:** single-host SQLite, tenant-scoped, FKs/unique constraints,
optimistic concurrency, immutable fills + terminal transitions, restart-safe
reservations, bounded/deterministically-ordered queries.

**31. Transaction boundaries:** atomic `persist_submit` / `persist_fill` /
`persist_cancel`; rollback proven (`test_atomic_rollback_on_approval_failure`).

**32. API endpoints:** 16 authenticated tenant-scoped `/paper/*` routes; mutations
route through the Gateway; `409` stale/idempotency, `400` invalid, tenant-safe `404`;
no credential/provider/live-env fields; no order route outside `/paper`.

**33. Permission matrix:** 7 `PAPER_*` permissions wired viewer→system (see
`PAPER_APPROVALS.md`); agents gain no approval/halt permission by default.

**34. Audit coverage:** account/intent/guardian-veto/submit/fill/cancel/halt events
appended to the platform audit sink with correlation IDs; order transitions +
ledger persisted.

**35. Fixtures:** deterministic hashed `MarketEvent` scenarios (`fixtures.py`;
stable manifest).

**36–39. Tests:** 46 (unit/service/persistence/integration/HTTP/adversarial).
**40. Regression:** 100 (M62.x+M49.3) + 43 (tool_runtime) + 21 (approval/identity) +
494 broad sweep — all green. See `m62_5_evidence/TEST_RESULTS.md`.

**41. Safety scan:** no executable forbidden capability; only docstring safety
statements; `git diff --check` clean; no listener/deploy/production change.

**42. Known limitations:** fixture/replay data only · single-host SQLite · long-only ·
MARKET+LIMIT only · no stop orders · no external broker sandbox · no distributed
workers · no browser workspace · no prolonged paper observation · no multi-currency
conversion · no corporate actions · reconciliation certification not yet performed.

**43. Push/merge/deploy:** none performed. Local commit only.

**44. Recommended M62.6 scope:** paper reconciliation, restart recovery, drift
detection, ledger repair controls, fail-closed halts, immutable reconciliation
evidence.

**45. Final authority statement:** below.

---

```
PlatformAgentRuntime remains the canonical agent runtime.
ExecutionGateway remains the sole authority for registered tool execution.
Trading Guardian remains an independent fail-closed veto layer.
M62.5 provides deterministic, durable paper-account and paper-order simulation only.
A paper-broker fill is a simulation event and is not a live trade, investment
recommendation, profitability proof, or authorization to allocate capital.
No live broker, real funds, leverage, margin, short-selling, options, futures,
perpetuals, derivatives, borrowing, production deployment, or autonomous capital
execution is authorized.
Services remain localhost-only.
No push, merge, deployment, or external rollout authority is granted.
```
