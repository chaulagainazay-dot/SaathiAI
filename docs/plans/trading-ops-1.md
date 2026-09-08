# TRADING-OPS-1 — canonical trading operations supervision

Branch `feature/nepse-completion`, start `d206af05` (verified from repository
reality, clean tree, in sync). Discovery map: `trading-ops-1-discovery.md`.

**Posture held: DISCOVER → EXTEND → CONVERGE.** No new incident system, no new
recovery framework, no new kill switch, no new health vocabulary. One module,
`tg/trading_ops.py`, that binds authorities which already existed.

## What was reused rather than rebuilt

| Reused | From | How |
|---|---|---|
| `HealthClass` (5 members) | `paper_activation/ops/models` | the only health vocabulary this module speaks |
| `_worst` aggregator | `paper_activation/ops/monitoring` | **imported, not reimplemented** — a test asserts equality across cases |
| `FailureMode`/`Response`/`degrade` | `tg/resilience` | failure → required response → health, and the source of `auto_retry=False` |
| `KillSwitchStore` | `tg/kill_switch` | kill-switch truth, displayed never duplicated |
| `StrategyHealth` | `tg/strategy_monitor` | strategy verdicts consumed, never recomputed |
| `observation_from_shadow` | `tg/strategy_observation` | the chain certified last milestone |
| `PanelStatus` | `tg/command_surface` | mapped at the render edge, not forked |

Importing the private `_worst` is deliberate: forking it would create a second
precedence policy free to drift from the one the paper monitor certifies against.
If it is ever renamed the failure is a loud ImportError, not silent divergence.

## What was actually missing

`CommandSurface` already rendered five panels read-only — but every input is a
caller-supplied keyword, thirteen of them, and nothing assembled them from the
authorities. `OperationalMonitor` answers authoritatively for the paper store and
sees no market data, Guardian, shadow session or kill switch. So the question
*"is trading safe right now?"* could not be answered without already knowing the
answer. That join is the whole milestone.

## Design decisions worth stating

**Overall health is precedence, never an average.** One CRITICAL safety subsystem
stays CRITICAL beside seven healthy ones.

**FAILED_SAFE is contained, not chaotic.** An engaged kill switch reports
FAILED_SAFE — a system stopped on purpose. It renders BLOCKED alongside CRITICAL
but stays distinct in the record, because "safely halted" and "unsafely ambiguous"
are different operational facts. A test pins both halves.

**Incident convergence resolves to the ROOT cause.** A provider outage that stales
market data, blocks a strategy on data quality and starves the portfolio is ONE
incident with three symptoms.

**Deduplication excludes time.** The key is `(subsystem, cause, scope)`, so the
same unchanged condition observed a hundred times is one incident; only a changed
cause or scope creates another.

**A data-blocked strategy is not blamed for the feed.** `DATA_QUALITY_BLOCKED`
never emits `REVIEW_STRATEGY_DEGRADATION` — the action points at the feed.

**Guardian blocking correctly is not Guardian failing.** Policy enforcement at
HEALTHY raises no incident at all.

**Readiness is not health.** A healthy SHADOW stack reports HEALTHY *and*
`live_trading_authorized: False`. `LIVE` is absent from `OpsMode` entirely.

**No false actionability.** Conditions SaathiOS cannot resolve — a commercial feed
licence, DNS — emit `EXTERNAL_ACTION_REQUIRED` with `automatable: False`, never a
retry. Every action names the authority that owns it; there is no generic "Fix".

**No clock.** `observed_at` is caller-supplied; identical inputs reproduce an
identical `snapshot_id`. AST-pinned.

## Defects found in adversarial review

1. **A symptom of a symptom vanished.** Convergence resolved only one causal
   level, so in a provider → market-data → strategy chain the strategy attached to
   market data, which was itself a symptom — and dropped out of the tree entirely.
   A real condition became invisible to the operator. Fixed by walking to the root
   cause, and pinned by an invariant test asserting **convergence reduces alerts,
   never conditions**: every failing subsystem appears exactly once.
2. **Failure modes were routed to the wrong owner.** A binary if/else sent
   everything non-market to RECONCILIATION, so `DISK_PRESSURE` told the operator
   to reconcile. Replaced with an explicit `SUBSYSTEM_FOR_FAILURE` table; a test
   asserts every mode has an owner with a real authority.
3. **Private enum internals.** `Subsystem._value2member_map_` replaced with a
   public `authority_for()` that returns UNKNOWN for a foreign subsystem rather
   than raising — an unrecognised subsystem must still be reportable, since
   dropping it would hide a real condition.
4. **My own colour test was wrong**, not the code: it scanned substrings, and
   `RED` lives inside `REQUIRED`. Replaced with an AST scan of enum member names.

## Verification

**43 focused tests**, covering the required fault-injection and multi-fault
precedence matrices: disconnect, stale feed, sequence gap, strategy DEGRADED,
strategy DATA_QUALITY_BLOCKED, Guardian unavailable, Guardian correctly blocking,
reconciliation required, shadow reconciliation failure, kill switch engaged,
licence blocked, provider auth, process restart, duplicate incident, and multiple
symptoms from one root cause.

Two tests drive **real** components end to end: a real `ShadowSessionStore` →
`observation_from_shadow` → `evaluate_strategy_health` → ops snapshot (asserting a
genuine DEGRADED verdict propagates), and a real `KillSwitchStore` activation.

Focused regression: **328 passed** across trading ops, resilience, command
surface, ops graduation, strategy monitoring, strategy observation, shadow
session, shadow trading, attribution v2, performance attribution v2 and financial
numeric.

## Authority containment

AST-proven that `trading_ops` calls none of `submit`, `place`, `send_order`,
`create_order`, `cancel`, `reserve_cash`, `consume`, `approve`, `activate`,
`deactivate`, `promote`, `set_limit`, `set_policy`, `commit`, `execute`,
`record_fill`, `append_event`, `with_tx`; and imports no broker, ledger,
execution, OMS, venue or exchange module.

| Counter | Value |
|---|---|
| REAL_ORDER_ATTEMPTS | 0 |
| PRIVATE_API_CALLS | 0 |
| REAL_LEDGER_MUTATIONS | 0 |
| PARAMETER_MUTATIONS | 0 |
| RISK_POLICY_MUTATIONS | 0 |
| GUARDIAN_POLICY_MUTATIONS | 0 |

## Security and resources

No credentials, tokens, network calls, subprocess, `eval`/`exec`, pickle or file
I/O anywhere in the module; a test serialises a provider-auth snapshot and asserts
no credential marker appears in the payload. Dependencies are stdlib only
(`hashlib`, `json`, `dataclasses`, `enum`) plus two in-repo imports. Nothing is
persisted — the snapshot is derived and recomputed. No Kafka, Redis, Celery,
Docker, Elasticsearch or Prometheus introduced. Aggregation is a linear pass over
subsystem findings; resource impact on an 8 GB M2 is negligible.

## Certification, with limitations

**TRADING_OPS_1_CERTIFIED_WITH_LIMITATIONS.**

1. **Findings are caller-supplied, and their classification is the authority's.**
   `build_snapshot` combines verdicts; it does not poll subsystems. A production
   collector that reads each authority on a schedule is the natural next step and
   is NOT part of this milestone — so today an operator surface must still be
   wired to the authorities by its caller.
2. **Market-data, provider, Guardian, ExecutionGateway and approval health have no
   typed health producer yet.** No such surface exists in the repository — the
   discovery sweep found `provider_health` only as a `CommandSurface` keyword
   argument. The snapshot accepts and classifies these correctly; nothing yet
   produces them.
3. **Incidents are derived, not persisted.** Acknowledgement is passed in by the
   caller. Two incident stores already exist (`connectivity_governance`
   in-memory, paper `pg_ops_health` durable); binding acknowledgement to one is
   deliberately deferred rather than guessed.
4. **Runbook references are a passthrough field.** `private_alpha.playbook_for`
   exists and is unwired; no runbook was rewritten.
5. **NEPSE remains externally limited** — no commercial feed licence, no live
   execution. Nothing here implies NEPSE operational trading readiness.

### Invariants held

`NO_OPS_EXECUTION_AUTHORITY`, `NO_LIVE_TRADING` (LIVE absent from `OpsMode`),
`NO_UNKNOWN_AUTO_RETRY` (inherited structurally: `auto_retry` False for every
mapped mode, test-pinned), `NO_RECONCILIATION_BYPASS` (reconciliation REQUIRED
forbids a healthy readiness claim), `NO_GUARDIAN_BYPASS`,
`NO_DATA_FAILURE_CLASSIFIED_AS_STRATEGY_FAILURE`, `NO_FALSE_LIVE_LABEL`,
`NO_AUTOMATIC_LIVE_PROMOTION`, `NO_LLM_EXECUTION_AUTHORITY`.
