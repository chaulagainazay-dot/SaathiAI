# TRADING-HEALTH-PRODUCERS-1 — typed health for five safety-critical subsystems

Branch `feature/nepse-completion`, start `71d92bd5` (recovered from repository
reality, clean, in sync). Discovery map: `trading-health-producers-1-discovery.md`.

Closes the gap TRADING-OPS-1 certified as its own principal limitation: the ops
snapshot typed five fields correctly and nothing populated them.

## Discovery corrected a claim I had made

TRADING-OPS-1 certified these five domains as having "no typed producer". The
brief was right to insist on searching harder — **four of five already had typed
state contracts, and provider health already had a full producer**:

| Domain | Reused | Verdict |
|---|---|---|
| Market data | `DataFreshness` (FRESH/STALE/FROZEN/UNKNOWN), `ObservationSource`, `ExchangeStatus` | ADAPT |
| Provider | `ProviderHealthState` (9 states), `ProviderHealthTracker`, `ProviderErrorCode`, `CapabilityAccess` | ADAPT — producer existed |
| Guardian | `service.posture()`, `AuthorityMode` (LIVE absent), `GateStatus`, `PolicyEngine` | ADAPT |
| ExecutionGateway | `execution/gateway.py`, `_GATEWAY_OK` guard, `ProposalStatus` | ADAPT |
| Approval | `ActivationApprovalCenter`, `ActivationApprovalStatus` (6 states) | ADAPT |

`connectors/providers/health.py` already stated this milestone's Rule 2 in its own
docstring: *"A healthy provider does not imply authorized execution."* What was
missing was never the state — it was the **mapping into `HealthClass` and the
wiring into the snapshot**.

## Two mutating reads, isolated rather than inherited

1. `ActivationApprovalCenter.get()`/`.list()` lazily expire approvals — setting
   `status=EXPIRED`, stamping `decided_at`, calling `freeze()`.
2. `ProviderHealthTracker.get()` **inserts** a record for an unseen provider.

Neither is a defect in its own module. But a health read must not be what triggers
them, so **every producer takes plain state, never the live object** — enforced by
a test asserting no parameter names a centre, tracker or store, and every
parameter is keyword-only.

## The three rules that decide every mapping

**Health is not readiness.** `live_execution_enabled=False` is HEALTHY with a
`LIVE_EXECUTION_DISABLED` capability — this program's designed posture, not a
fault. Reporting the intended configuration as CRITICAL would make the panel red
forever by construction and train the operator to ignore it. Same for a
policy-disabled provider, and for public market data that never implies a trading
account.

**Missing evidence is never healthy.** `HealthClass` has no UNKNOWN member and
this milestone would not fork the vocabulary to add one, so insufficient evidence
is `WARNING` + `evidence_sufficient=False` + `INSUFFICIENT_EVIDENCE` +
a `MANUAL_OPERATOR_VALIDATION` action. All five producers are parametrised
against this.

**Containment is not collapse.** Exhausted reconnection *under containment* is
FAILED_SAFE; without containment it is CRITICAL — still nominally live while
unable to refresh is the dangerous case. Same split for the approval store and the
gateway.

### Guardian: blocking is not failing

The subtlest rule and the one most worth stating. `blocked_count` is accepted,
recorded for the operator, and **deliberately not an input to classification** — a
Guardian refusing a hundred unsafe trades is working perfectly, and any path that
let a block count drag health down would teach an operator to want fewer refusals.
Pinned two ways: parametrised over 0…10,000 blocks all returning HEALTHY, and an
**AST test asserting no branch condition in `guardian_health` references
`blocked_count`**.

A detected bypass is CRITICAL and explicitly **not** FAILED_SAFE — nothing is
contained if the gate can be walked around, and the system looks protected while
it is not.

## Defects found in adversarial review

1. **Connectivity was treated as freshness.** `market_data_health(connected=True)`
   with no freshness reported returned `HEALTHY / FEED_FRESH`. That is the classic
   silent feed failure — socket up, no rows arriving — reported as fine on the
   strength of a TCP connection, and a direct breach of
   `NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`. Now insufficient evidence. The fault
   branches were deliberately left ahead of the check: a disconnect or sequence
   gap is *positive* evidence of a problem and must not be softened into
   "unknown". Three tests pin the distinction.
2. **Count metrics were unvalidated.** `unknown_state_count` gates a branch, and
   `True` is an int in Python while NaN is truthy — either would have read as
   "there is at least one approval in an unknown state", a fabricated fact. Added
   `_count()` applying FINANCIAL-NUMERIC-1's discipline to counts: bool, non-finite,
   fractional, negative and non-numeric all refused; **None stays None** and never
   becomes zero.
3. **Doubled detail strings** (`feed feed_stale`) — cosmetic, fixed.

## Verification

**74 focused tests.** Fault matrices for all five: market data (fresh / stale /
frozen / gap / disconnect / reconnecting / exhaustion / replay / fixture),
provider (9 states + licence / DNS / environment / auth), Guardian (healthy allow,
healthy blocking ×5 volumes, missing input, invalid policy, bypass), gateway
(paper-only, disabled-by-policy, reconciliation, unknown execution state, kill
switch), approval (healthy, pending ×4, expired, store unavailable, duplicate-guard
broken, unknown state).

Focused regression: **400 passed** across producers, trading ops, resilience,
command surface, ops graduation, strategy monitoring, strategy observation, shadow
session, shadow trading, financial numeric, execution gateway, trading guardian
and market observation.

### UNKNOWN reduction — proven, not asserted

| | Before | After |
|---|---|---|
| Subsystems populated | 0 | 5 |

A test builds a bare snapshot (zero subsystems), then the same snapshot fed by the
producers, asserting all five appear with a canonical `HealthClass` and a real
authority. Remaining UNKNOWNs are genuine missing evidence, not missing wiring.

### Root-cause correlation survives the wiring

A provider outage that stales market data and blocks a strategy still converges to
**one** incident with two symptoms, and the strategy is still not blamed for the
feed. TRADING-OPS-1's convergence is not defeated by real producers.

## Authority containment

| Counter | Value |
|---|---|
| REAL_ORDER_ATTEMPTS | 0 |
| PRIVATE_API_CALLS | 0 |
| REAL_LEDGER_MUTATIONS | 0 |
| **APPROVAL_CONSUMPTIONS** | **0** |
| PARAMETER_MUTATIONS | 0 |
| RISK_POLICY_MUTATIONS | 0 |
| GUARDIAN_POLICY_MUTATIONS | 0 |

Approval consumption is proven **dynamically**, not statically: a real
`ActivationApprovalCenter` is driven to produce a genuinely APPROVED approval, all
five producers plus a full snapshot run, and the approval is asserted still
APPROVED and not CONSUMED.

Statically: no call to `submit`, `place`, `execute`, `cancel`, `reserve`,
`consume`, `approve`, `decide`, `revoke`, `activate`, `force_state`,
`observe_error`, `observe_success`, `set_policy`, `commit`, `freeze` or
`transition`; no import of any approvals, broker, ledger, execution, OMS, venue,
kill-switch or policy module; no `retry`/`reconnect`/`recover` call, which is
`NO_UNKNOWN_AUTO_RETRY` made structural; and no clock.

## Security and resources

No credentials, network, subprocess, `eval`/`exec`, pickle, file I/O or
persistence. A test serialises an auth-blocked provider snapshot and asserts no
credential marker appears. Dependencies are stdlib (`dataclasses`, `enum`) plus two
in-repo imports. Pure dictionary lookups and branches — microseconds per producer.
No service, database, Docker, Redis, Kafka or Prometheus introduced.

## Certification, with limitations

**TRADING_HEALTH_PRODUCERS_1_CERTIFIED_WITH_LIMITATIONS.**

1. **Producers classify supplied state; they do not poll.** The subsystems are
   read by the caller and handed in — deliberately, because the two mutating reads
   above mean a producer that reached for live objects would transition state
   during a health check. A scheduled collector is the natural next step and is
   not in this milestone.
2. **INSUFFICIENT_EVIDENCE maps to WARNING, not DEGRADED.** Not knowing is a
   monitoring gap rather than a proven fault. It is never HEALTHY and always
   carries an operator action, but it sits below the incident threshold, so a
   subsystem nobody reports raises no incident. Recorded as a deliberate choice.
3. **Guardian bypass detection is an input, not a detector.** This milestone
   classifies a reported bypass as CRITICAL; nothing here detects one.
4. **Market-data evidence has no live crypto supervisor wired to it.** The typed
   inputs (gap, exhaustion, resync) match the certified crypto work's vocabulary,
   but connecting that supervisor is collector work, per limitation 1.
5. **NEPSE stays externally limited** — no commercial feed licence, no live
   execution. A missing licensed provider reports `EXTERNAL_LICENSE_REQUIRED`, and
   the operator is explicitly told retry will not resolve it.

Not falsely closed: real live trading, private Binance connectivity, broker
connectivity, commercial NEPSE feed, long-duration strategy observation, NEPSE
execution attribution, and the live-browser environmental flake.

### Invariants held

`NO_HEALTH_PRODUCER_EXECUTION_AUTHORITY`, `NO_HEALTH_PRODUCER_APPROVAL_CONSUMPTION`
(dynamically proven), `NO_HEALTH_PRODUCER_LEDGER_MUTATION`,
`NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`, `NO_FALSE_LIVE_LABEL` (no LIVE member in
`HealthMode`; replay is HEALTHY+REPLAY), `NO_UNKNOWN_AUTO_RETRY`,
`NO_GUARDIAN_BYPASS`, `NO_RECONCILIATION_BYPASS`, `NO_LIVE_TRADING`,
`NO_LLM_EXECUTION_AUTHORITY`, `NO_INVALID_FINANCIAL_VALUE_TO_ZERO` (extended to
counts), `NO_DATA_FAILURE_CLASSIFIED_AS_STRATEGY_FAILURE`.
