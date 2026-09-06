# HEALTH-COLLECTOR-1 — safe collection from live subsystems into the ops snapshot

Branch `feature/nepse-completion`, start `da05a918` (recovered from repository
reality, clean, in sync). Closes TRADING-HEALTH-PRODUCERS-1's principal
limitation: the producers classified supplied state and nothing polled anything.

## Discovery

| Component | Verdict |
|---|---|
| `pg_scheduler` job table (`upsert_job`/`mark_job_run`/`list_jobs`) in the paper store, already read by `OperationalMonitor._component_scheduler` | **KEEP** — the canonical cadence store; no second scheduler added |
| `saathi/scheduler.py` — app-level cron for content/business jobs | **REJECT** — not trading, wrong scope |
| `MetricsCollector`, `SyncRunner`, `ExperimentScheduler`, `SchedulerRunner` | **REJECT** — unrelated domains |
| `KillSwitchStore.status()` / `.is_blocked()` | **KEEP** — verified pure reads |
| `TradingGuardianService.posture()` | **KEEP** — verified pure read of policy + switches |
| `ActivationApprovalCenter` public reads | **ADAPT** — all mutate |
| `ProviderHealthTracker` public reads | **ADAPT** — all mutate |

## The constraint that shaped the milestone

Discovery confirmed the hazard and then found it was **total**: on both
authorities, *every* public accessor mutates.

- `ActivationApprovalCenter` — `get`, `list`, `decide`, `revoke`, `consume` all
  call `_expire_if_needed()`, which transitions a lapsed PENDING approval to
  EXPIRED, stamps `decided_at` and calls `freeze()`.
- `ProviderHealthTracker` — `get`, `observe_success`, `observe_error`,
  `force_state`, `should_quarantine` all call `_rec()`, which **inserts** a record
  for an unseen provider.

There was no safe read to reuse, so per the brief two narrowly scoped ones were
added:

- **`ActivationApprovalCenter.peek()`** — an immutable view of every approval's
  recorded state. Expires nothing. A caller needing to know which approvals have
  lapsed compares `expires_at` against its own explicit evaluation time, leaving
  the transition to whoever actually acts.
- **`ProviderHealthTracker.peek()` / `.peek_all()` / `.known_provider_ids()`** —
  read a record without creating one; `peek` returns `None` for an unseen
  provider and hands back a copy so a reader cannot mutate tracked state.

Both behaviours remain correct in their own modules — expiry *should* bite the
moment anyone acts, and an observation path *should* default a record into
existence. They are simply wrong for monitoring, and the tests prove the contrast
rather than assert it: **a companion test drives `get()` and asserts it still
expires / still creates**, so the safety tests can never pass vacuously.

## Design

Two layers, deliberately separate:

```
live subsystems -> read_* adapters -> collect_trading_health() -> producers
                                   -> snapshot_from_collection() -> ops snapshot
```

`TradingHealthCollector` is a caller-driven runner: no thread, no daemon, no
process manager, nothing started on construction. It adds two deterministic
guards — a re-entrant tick is **dropped, not queued** (an unbounded queue of
health passes is how a slow subsystem turns a monitor into an outage), and a tick
inside `min_interval_seconds` is coalesced. The in-flight flag is released in a
`finally`, so one bad pass cannot wedge the collector shut.

**Time is explicit.** Freshness genuinely depends on the clock, so the collector
takes `evaluation_time`; the producers stay clock-free. Freshness is derived from
observation *age* against that time and a supplied `max_age_seconds` — never from
connectivity. `NO_CONNECTIVITY_AS_FRESHNESS` is now enforced twice: a source
reporting a live transport but no last-observation time yields no freshness at
all.

**Gateway posture is read from configuration, never by exercising it.** Every
interesting `ExecutionGateway` method (`submit`, `approve_execution`,
`retry_execution`, `recover_after_restart`) advances execution state; there is no
way to ask it how it is without asking it to do something. Likewise
`reconciliation_required` is supplied, because calling a reconciler to discover
whether reconciliation is needed is exactly the mutating read this milestone
exists to prevent.

## Defects found in review

1. **Reading state leaked non-producer keys — twice.** `observation_age_seconds`
   and `kill_switch_engaged` were placed in a reading's `state`, which is splatted
   into the producer. Each raised a `TypeError` that fault isolation dutifully
   converted into INSUFFICIENT_EVIDENCE — so the subsystem **quietly stopped
   reporting while every health test still passed**. This is the most dangerous
   failure mode the collector has, because it is silent and looks like caution.
   Fixed by splitting `state` (strictly producer kwargs) from `diagnostics`, and
   closed as a *class* by a test asserting every reading's state keys are accepted
   by its producer's signature, plus one asserting a healthy pass has zero
   failures and zero insufficient-evidence results.
2. **A vacuous safety test.** The lapsed-approval fixture anchored expiry to real
   time (`expires_in_sec=-1`) while evaluating at a fixed past literal, so nothing
   was actually lapsed and the test proved nothing. Fixed with an evaluation time
   comfortably after any real-time deadline, and the reading is now asserted to
   report `expired == 1`.

## Verification

**43 focused tests.** Fault matrix: all-healthy, connected-but-unknown-freshness,
stale, disconnect, unseen provider, healthy provider, rate-limited, Guardian
healthy, gateway paper-only, unknown execution state, kill switch engaged,
pending approvals, lapsed approval, exploding source, exploding tracker, and
nothing-supplied.

Regression: **559 passed** across collector, producers, trading ops, resilience,
command surface, ops graduation, strategy monitoring/observation, shadow session
and trading, financial numeric, execution gateway, trading guardian, market
observation and provider governance — plus **44** provider runtime, **31**
approval/runtime and **12** paper activation for the two modified modules.

### UNKNOWN reduction, now from live state

| | Producers milestone | This milestone |
|---|---|---|
| Populated | 5, from hand-supplied state | 5, from real objects |

A test passes a real `ProviderHealthTracker`, `TradingGuardianService`,
`KillSwitchStore` and `ActivationApprovalCenter` and asserts all five subsystems
arrive typed in the ops snapshot with a real authority — no manual shaping.

### Root-cause convergence survives real collection

A provider forced UNAVAILABLE with a stale feed and a data-blocked strategy still
converges to **one** incident with two symptoms.

### Restart

A fresh collector fed the same sources reproduces an identical `snapshot_id` and
identical per-subsystem health. No fabricated healthy state on startup.

## Authority counters

| Counter | Value |
|---|---|
| APPROVAL_STATE_TRANSITIONS | 0 |
| PROVIDER_STATE_INSERTIONS | 0 |
| APPROVAL_CONSUMPTIONS | 0 |
| RECONCILIATION_CALLS | 0 |
| RECOVERY_CALLS | 0 |
| KILL_SWITCH_MUTATIONS | 0 |
| REAL_ORDER_ATTEMPTS | 0 |
| PRIVATE_API_CALLS | 0 |
| REAL_LEDGER_MUTATIONS | 0 |
| PARAMETER_MUTATIONS | 0 |

The first three are proven **dynamically** against real objects, not by static
scan alone: a lapsed approval is still PENDING with `decided_at is None` after a
full pass and snapshot; an APPROVED approval is still APPROVED and unconsumed;
and a tracker's cardinality is unchanged after being asked about two providers it
has never seen.

## Security and resources

No credentials, network, subprocess, `eval`/`exec`, pickle, file I/O or
persistence. A test serialises a collected snapshot and asserts no credential
marker. Imports are stdlib plus in-repo only; no broker, venue, Binance,
credential or secret module is importable from here. 200 sequential full passes
complete well inside a five-second bound — the assertion exists to catch an
accidental I/O path, not to benchmark. No Celery, Redis, Kafka, daemon or process
manager introduced.

## Certification, with limitations

**TRADING_HEALTH_COLLECTOR_1_CERTIFIED_WITH_LIMITATIONS.**

1. **Cadence is caller-driven.** `TradingHealthCollector.tick` must be called by a
   host loop or a `pg_scheduler` job; nothing here starts a thread. Deliberate —
   the brief forbids a new process manager, and `pg_scheduler` is paper-scoped and
   disabled by default, so wiring it is a separate decision.
2. **No live crypto market-data supervisor is attached.** The collector accepts
   any source exposing `snapshot()` or a mapping, with the certified vocabulary;
   nothing in the repository currently produces it live.
3. **Gateway and reconciliation state are supplied, not probed** — for the reason
   above: no side-effect-free way to ask exists.
4. **Guardian bypass detection remains an input.** No detector exists; the
   collector would carry one if it did.
5. **NEPSE stays externally licence-blocked**, and the live-browser environmental
   flake is unrelated and untouched.

### Invariants held

`NO_COLLECTOR_EXECUTION_AUTHORITY`, `NO_MUTATING_HEALTH_READ`,
`NO_APPROVAL_EXPIRY_FROM_HEALTH_READ`, `NO_PROVIDER_CREATION_FROM_HEALTH_READ`,
`NO_RECONCILIATION_FROM_HEALTH_READ`, `NO_RECOVERY_FROM_HEALTH_READ`,
`NO_KILL_SWITCH_MUTATION_FROM_HEALTH_READ`, `NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`,
`NO_FALSE_LIVE_LABEL`, `NO_CONNECTIVITY_AS_FRESHNESS`, `NO_LIVE_TRADING`,
`NO_PRIVATE_ACCOUNT_ACCESS`, `NO_LLM_EXECUTION_AUTHORITY`.
