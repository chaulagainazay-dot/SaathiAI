# Paper Broker (M62.5)

A deterministic, durable, event-driven **simulation** broker. Isolated from live
capital and live broker infrastructure. A paper fill is a simulation event — **not**
a live trade, recommendation, profitability proof, or authorization to allocate
capital.

## Package layout — `saathi/platform/paper_trading/`

| module | responsibility |
|---|---|
| `models.py` | durable domain (`PaperAccount`, `PaperPosition`, `PaperOrder`, `PaperFill`), state machines, versioned fee/slippage models, hashing, `assert_paper_safe` |
| `broker.py` | **pure, stateless** `PaperBroker` — order validation + conservative fill engine; `MarketEvent` (`from_quote` / `from_bar` adapters for M62.2 data) |
| `store.py` | single-host SQLite persistence; atomic `persist_submit` / `persist_fill` / `persist_cancel` |
| `service.py` | `PaperTradingService` — permission-gated, tenant-scoped orchestration (Guardian, approval, reservation, accounting, audit) |
| `execution_tool.py` | registered tool manifests + adapters (the only mutation path) |
| `orchestration.py` | Runtime → Gateway → tool routing helpers |
| `fixtures.py` | deterministic certification market events |

## Determinism

`PaperBroker` never reads wall-clock time, never fetches live data, uses no hidden
randomness, and never sees a future event. Identical inputs —

```
engine version, account-state hash, order-state hash, market-event hash,
fee-model version, slippage-model version, seed, calendar
```

— produce an identical acceptance decision, rejection reason, fill quantity, fill
price, fee, and `result_hash` (see `fill_result_hash`; proven by
`test_fill_determinism_identical_inputs_identical_hash` and the evidence manifest).

## Market data

Consumes M62.2 canonical `MDQuote` / `MDBar` via `from_quote` / `from_bar`, or a
bounded deterministic `MarketEvent` fixture. Each event carries its own coarse
`DataQuality` and `MarketState`; anything not fully `VALID` and `OPEN` blocks the
fill (fail closed).

## Separation from the backtest engine (M62.4)

The paper broker is event-driven, durable, account-bound, order-stateful, and
restart-safe. It shares only narrowly scoped primitives conceptually (Decimal
accounting, fee/slippage/position math). It does **not** share the backtest run
state machine, result manifests, historical batch assumptions, future-bar
knowledge, or any backtest execution shortcut.

## Bounded scope / limitations

Deterministic fixture/replay market data only · single-host SQLite · long-only ·
MARKET + LIMIT only (no stop/bracket/OCO) · no external broker sandbox · no
distributed workers · no multi-currency conversion · no corporate actions · no
prolonged paper observation · reconciliation certification deferred to M62.6.
