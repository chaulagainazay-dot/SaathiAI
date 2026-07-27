# M62.4 — Strategy Definition & Deterministic Backtesting

Simulation only. A backtest evaluates a **versioned** strategy against **versioned**
market data. A passing result is **not** trading approval, investment advice, or proof
of profitability, and grants **no** authority to allocate capital.

## Package

`saathi/platform/strategy/`

| Module | Responsibility |
|--------|----------------|
| `models.py` | Canonical domain: `StrategyDefinition`, `StrategyVersion`, `DatasetReference`, `SimulatedOrder`, `SimPosition`, `EquityPoint`; strategy + backtest state machines; hashing |
| `features.py` | Time-aware feature generation + the look-ahead-guarded `BacktestContext` |
| `signals.py` | Declarative signal-rule evaluation (deterministic priority) |
| `sizing.py` | Position sizing, leverage-refusing |
| `execution_model.py` | Next-bar fill simulation, fees, slippage, partial fills |
| `accounting.py` | Average-cost portfolio ledger + reconciliation invariants |
| `metrics.py` | Performance metrics with explicit sample sufficiency |
| `validation.py` | Structural validation + statistical/bias outcomes |
| `walk_forward.py` | Chronological splits + expanding/rolling walk-forward |
| `stress.py` | Regime stress + cost resilience + parameter sensitivity |
| `engine.py` | Deterministic run loop + result hashing |
| `guardian_sim.py` | Simulation-only Guardian veto (never approval) |
| `store.py` | Tenant-scoped SQLite persistence |
| `service.py` | Server-authoritative orchestration (permissions, audit, state machine) |
| `fixtures.py` | Valid + broken-strategy certification fixtures |

## Strategies are declarative

A strategy is **data**, not code: a set of `FeatureSpec` + `SignalRule` + `SizingRule`.
There is no arbitrary-code path — a strategy cannot `import`, `eval`, fetch, spawn a
subprocess, or read the filesystem. This is a *structural* safety property.

## Workflow

```
Research thesis (read-only)
 → Strategy hypothesis → Versioned definition → Dataset selection
 → Feature generation → Signal generation → Simulated order intent
 → Fill simulation → Portfolio accounting → Risk metrics
 → Benchmark comparison → Out-of-sample (walk-forward) → Stress & sensitivity
 → Certification decision (human, owner+)
```

## Strategy lifecycle

`DRAFT → RESEARCH_LINKED → DATA_VALIDATED → BACKTESTING → BACKTEST_COMPLETE →
VALIDATION_REQUIRED → VALIDATED | REJECTED → SUPERSEDED | EXPIRED`.

No jump from `DRAFT` to `VALIDATED`. **Validated means technically sound, never
profitable.** A strategy can be technically valid and economically unattractive; both
facts are reported (`validation.py` outcomes).

## Backtest orchestration state machine

`DRAFT → QUEUED → VALIDATING_DATA → GENERATING_FEATURES → RUNNING →
CALCULATING_METRICS → RUNNING_STRESS_TESTS → RUNNING_SENSITIVITY →
VALIDATION_REQUIRED → COMPLETE | FAILED | CANCELLED | REJECTED`.

Transitions are explicit, versioned, audited, and restart-safe. A completed run's
manifest is **immutable**. A failed/rejected run **preserves** its diagnostic evidence.

## Determinism

For identical `(strategy hash, dataset hash, engine version, config, seed)` the
`result_hash` is identical. See `docs/trading/m62_4_evidence/determinism_proof.json`.
No wall-clock, no RNG, no network, no filesystem.

## Authority statement

The backtest engine may create simulated fills and simulated portfolio state inside an
isolated backtest domain. It may **not** create platform order intents, consume
approvals, call ExecutionGateway, call a broker, register a trading tool, or modify
real/paper accounts. `PlatformAgentRuntime` remains the canonical runtime;
`ExecutionGateway` remains the sole registered-tool execution authority; the Trading
Guardian remains an independent fail-closed veto.
