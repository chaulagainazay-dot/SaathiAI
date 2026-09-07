# TRADING-RUNTIME-INSTANCE-WIRING-1 — real instances, or real reasons

Track B. Branch `feature/nepse-completion`, start `78921d75` (recovered from
repository reality, clean). Track A runs in a separate pinned worktree and is
untouched by this work.

## Discovery — why three subsystems reported nothing

Not a scheduling defect. A timer over absent instances produces fresh
insufficient evidence.

| Subsystem | Canonical owner | Reality | Verdict |
|---|---|---|---|
| **Approval** | `default_paper_gov().approvals` | a real process-wide `ActivationApprovalCenter`, the same one governed paper flows use | **WIRED** |
| **Guardian** | `default_tg_service()` | already wired | KEEP |
| **Kill switch** | `default_tg_service().kill_switches` | owned by Guardian — one owner, not two | KEEP |
| **ExecutionGateway** | Guardian's `posture()` | declares `live_order_capable`, `paper_only`, `require_approval` as read-only facts | **WIRED** |
| **Market data** | `default_market_observation()` | exists, but is a *validation harness* — fixture-sourced, `"purpose": "validation_not_trading"`, no transport, heartbeat or last-observation clock | **NOT WIRED**, reason reported |
| **Provider** | `ProviderExecutionRuntime.health` | nothing constructs one at process level — only the providers CLI and an external verify path do | **NOT WIRED**, reason reported |

## The two things deliberately not built

**No fake market-data supervisor.** `market_observation` is a fixture-sourced
validation service. Presenting it as feed health would misrepresent a fixture as
a live feed — the false-live label this program forbids. It reports
`PUBLIC_FEED_DISABLED` with that reason in words.

**No monitoring-only provider tracker.** One could be created in a line, and the
panel would go green. It would report the health of an object no request ever
touches. It reports `NOT_CONFIGURED` instead.

The objective is real evidence, not green evidence.

## Gateway posture without exercising the gateway

Every interesting `ExecutionGateway` method — `submit`, `approve_execution`,
`retry_execution`, `recover_after_restart` — advances execution state. There is
no side-effect-free way to ask it how it is. Guardian already publishes the
gateway-relevant configuration as verified read-only facts, so posture is read
there. Live execution off by policy surfaces as a **capability**, not a fault.

## Evidence before and after

| Subsystem | Before | After |
|---|---|---|
| MARKET_DATA | insufficient evidence (generic) | `PUBLIC_FEED_DISABLED: no live public feed supervisor started in this process…` |
| PROVIDER | insufficient evidence (generic) | `NOT_CONFIGURED: no process-wide ProviderExecutionRuntime…` |
| GUARDIAN | HEALTHY | HEALTHY (unchanged) |
| EXECUTION_GATEWAY | insufficient evidence | **HEALTHY — paper only ready** |
| APPROVAL | insufficient evidence | **HEALTHY — real approval centre** |

Three subsystems now report real runtime evidence; the other two report *why
not*. A wiring gap and a subsystem fault no longer read the same, which a single
UNKNOWN merged. `runtime_wiring` also travels beside health in the payload.

## Defect found and closed in review

**A leak I introduced.** Carrying the collector's `reading.error` into the
subsystem detail put exception text — filesystem paths, and anything else an
exception message happens to contain — into a payload served to a browser. Now
only the caller's **authored** reason can replace a detail; the raw exception
stays in `failures` for local diagnostics. Two tests pin it: one drives an
exception containing `/Users/…` and `token=` and asserts neither reaches the
health payload, one asserts the producer's own wording stands when no authored
reason exists.

A test from CENTRAL-COMMAND-TRADING-OPS was legitimately superseded — it asserted
the route wires *only* Guardian and the kill switch. Updated to assert the half
that still matters: market data and provider are still not wired.

## Verification

**27 focused tests**; **364 passed** across wiring, Central Command, collector,
producers, trading ops, paper activation, approval runtime, provider runtime,
market observation, trading guardian, platform API, strategy observation and
shadow session.

### Instance identity

Proven by `is`, not by shape: the observed approval centre **is**
`default_paper_gov().approvals`; the observed Guardian **is**
`default_tg_service()`; the kill switch **is** that service's own store.
Resolution is stable across calls, so no duplicate singleton appears.

### Safe reads survive

| Counter | Value |
|---|---|
| APPROVAL_STATE_TRANSITIONS | 0 |
| APPROVAL_CONSUMPTIONS | 0 |
| PROVIDER_STATE_INSERTIONS | 0 |
| KILL_SWITCH_MUTATIONS | 0 |
| REAL_ORDER_ATTEMPTS / PRIVATE_API_CALLS / REAL_LEDGER_MUTATIONS | 0 |

Now proven against the **real** centre rather than a fixture: a lapsed approval
in the live `ActivationApprovalCenter` is still PENDING with `decided_at is None`
after a status read at a far-future evaluation time. Server boot resolves twice
and expires nothing.

A static check bans mutating accessors **by receiver**, not by method name —
`dict.get` is ubiquitous and harmless, while `center.get()` expires and
`tracker.get()` creates.

## Certification, with limitations

**TRADING_RUNTIME_INSTANCE_WIRING_1_CERTIFIED_WITH_LIMITATIONS.**

1. **Market data and provider remain unwired** — truthfully. No live public feed
   supervisor and no process-wide provider runtime exist to observe. Standing up
   either is a separate decision with its own connectivity and configuration
   surface, not something to fake here.
2. **Gateway posture is Guardian's declaration**, not a probe of the gateway
   itself, because no side-effect-free probe exists.
3. **No host loop was added.** Request-driven, freshness-aware collection remains
   sufficient; discovery surfaced no requirement it cannot meet.
4. **NEPSE licence-blocked, no live trading, no real broker** — unchanged.

### Invariants held

`NO_FABRICATED_RUNTIME_INSTANCE`, `NO_RUNTIME_WIRING_AUTHORITY_EXPANSION`,
`NO_MUTATING_HEALTH_READ`, `NO_APPROVAL_EXPIRY_FROM_STATUS_READ`,
`NO_PROVIDER_CREATION_FROM_STATUS_READ`, `NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`,
`NO_FALSE_LIVE_LABEL`, `NO_LIVE_TRADING`, `NO_PRIVATE_ACCOUNT_ACCESS`.
