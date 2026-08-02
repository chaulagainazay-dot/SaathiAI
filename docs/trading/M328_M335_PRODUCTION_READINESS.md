# M328–M335 — Production Readiness, Observability & Operational Resilience

**Verdict:** `PRODUCTION_READINESS_AND_OPERATIONAL_RESILIENCE_CERTIFIED_WITH_LIMITATIONS`
**Browser verdict:** `PRODUCTION_READINESS_OPERATIONAL_RESILIENCE_BROWSER_CERT_PASSED_WITH_LIMITATIONS`
**Maximum state:** `OPERATIONALLY_READY_OFFLINE`
**Maturity:** `OPERATIONALLY_READY_OFFLINE`
**Branch:** `milestone/m328-m335-production-readiness`
**Base SHA:** `5b505f1a119989ec78856f969cb9fe3184bc784f`

---

## Objective

Make SaathiOS operationally reliable *before* any real connectivity work. This
milestone adds observation, diagnosis and resilience verification. It adds no
capability to reach a provider, hold a credential, read an account, or place an
order — and it is designed so that no amount of operational signal can create one.

---

## Architectural stance

The operations layer is a **composition**, not a new subsystem. It reads the
existing governance, authority, approval, certification, replay, provider-contract,
audit, evidence and maturity surfaces and folds them into a single operational view.

Three invariants shape every module:

1. **Observation never grants authority.** A `FAILED` component, a breached metric
   threshold, or a `CRITICAL` alert changes nothing except what an operator sees.
   There is no remediation path, no auto-restart, no escalation, no unlock.
2. **Everything stays on the machine.** No telemetry exporter, no cloud monitoring
   agent, no email/SMS/push transport, no cloud backup target. An AST scan over the
   package enforces this, and the browser certification confirms localhost-only
   traffic at runtime.
3. **Everything is deterministic.** No module reads the wall clock or a random
   source. Trace identifiers are content-derived, load is modelled in closed form,
   and percentiles use nearest-rank. Two runs in two processes produce byte-identical
   evidence hashes.

### Determinism

`DeterministicClock` (`models.py`) is the only time source. It starts at a fixed
epoch and advances by a fixed tick when an artefact is emitted. `Date`/`time.time()`
is never consulted. This is what makes the certification evidence hash stable across
processes and across a clean clone — verified below.

---

## M328 — System Health Framework

One `HealthEngine`. Each domain registers a probe; the engine reduces child states
into a parent verdict.

**States:** `HEALTHY`, `WARNING`, `DEGRADED`, `FAILED`, `MAINTENANCE`.

**Rollup ranking** (worst wins): `HEALTHY(0) < MAINTENANCE(1) < WARNING(2) <
DEGRADED(3) < FAILED(4)`. `MAINTENANCE` deliberately ranks above `HEALTHY` but below
`WARNING`: a component under planned maintenance is not healthy, but it is not an
incident either.

**Domains covered:** platform, module, dependency, storage, scheduler, replay engine,
provider registry.

A probe that raises is itself a `FAILED` signal rather than a crash. `force_state`
and `set_maintenance` exist so degradation paths are provable in drills; the
certification uses them to demonstrate that a `DEGRADED` platform still reports every
authority lock false.

## M329 — Observability

Structured logging, event correlation, trace IDs, operation timelines, execution
history and audit visualization — all in a local in-process ring buffer.

- **Trace IDs are content-derived**, not random: the same operation, component and
  correlation key always yields the same trace ID. Child spans inherit the parent
  trace and record the parent span.
- **Redaction happens at write time.** Any field named in
  `FORBIDDEN_OBSERVABILITY_FIELDS` (tokens, credentials, accounts, balances,
  positions, orders) is replaced with `[REDACTED]` recursively, including inside
  nested maps and lists. `redaction_scan()` proves no forbidden value survived.
- **"Execution history" means engine operations**, never orders. The surface reports
  `order_execution_records == 0` and every entry carries `order_execution: false`.

No OpenTelemetry, Sentry, Datadog, Prometheus client, or statsd import exists.

## M330 — Metrics

Seven kinds, all local: API latency, task duration, queue depth, cache performance,
replay performance, UI performance, database performance.

Percentiles use the **nearest-rank** method — no interpolation, so a sample set
always yields identical numbers. Thresholds are **advisory**: crossing one colours a
dashboard cell and may raise an offline alert. `autoscaling_triggered` is
structurally `false`; nothing is throttled, scaled, or restarted.

Cache performance is a *below*-threshold metric; the classifier respects direction.

## M331 — Alert Framework

Three severities (`INFORMATIONAL`, `WARNING`, `CRITICAL`) and exactly three
destinations: control centre, local log, audit history.

`email`, `sms`, `push`, `webhook`, `slack`, `pagerduty`, `opsgenie`, `telegram` and
`discord` are rejected with a normalized `forbidden_destination` error — the engine
has no transport that could deliver to them.

Lifecycle is append-only: `OPEN → ACKNOWLEDGED → RESOLVED`, and `RESOLVED` is
terminal. A recurrence raises a new alert rather than reopening history.

Alerts carry `triggers_execution: false`. Raising one never acts.

## M332 — Backup & Recovery

Content-addressed local snapshots in three kinds: configuration, replay snapshot,
database manifest.

- **Integrity** is a digest recomputation plus a serialized-size match.
- **Recovery is simulated.** The engine proves a snapshot would restore
  byte-identically; live state is never mutated and nothing is applied to production.
  Every recovery record asserts `restored_credentials/accounts/orders == 0`.
- **Corruption surfaces, it does not silently heal.** A damaged payload yields
  `INTEGRITY_MISMATCH`, and the certification runs that drill against a scratch engine
  so the live snapshot store is never left damaged.
- A snapshot payload containing a forbidden field is rejected at capture.

No S3, GCS, Azure Blob, or remote sync target is reachable.

## M333 — Operational Diagnostics

One entry point, one unified report, seven subsystems: provider contracts, replay
engine, authority system, approval engine, storage, configuration, browser
certification history.

The report is content-addressed (`report_id`, `report_digest`) and deterministic:
repeated runs produce the same digest. `auto_remediation` is `false` and each result
carries `remediates_automatically: false`.

Browser certification history is **read**, never written.

## M334 — Performance & Load Validation

Five dimensions: concurrent users, multiple agents, replay workload, dashboard
refresh, API concurrency.

Load is **modelled, not generated**. Each profile is a closed-form deterministic
queueing model: a virtual request is assigned to a service slot, queue depth follows
from concurrency over capacity, and a small bounded phase term keeps the distribution
non-degenerate. No threads are spawned, no sockets opened, no sleeps taken.

`prove_repeatability()` runs the full suite N times and asserts the fingerprints are
identical — the deterministic-repeatability requirement made explicit.

## M335 — Operations Control Center

A read-only dashboard with eight panels: system health, metrics, alerts, diagnostics,
backups, replay health, authority summary, certification history.

`execution_controls`, `deployment_controls` and `mutating_operational_controls` are
all structurally `0`. The forbidden-control list includes credential and API-key
inputs, OAuth and login buttons, provider-connect and account-link controls, order
and transfer forms, canary activation, deployment control, service restart/scale, and
kill-switch override.

The only operator actions are read, acknowledge, resolve, verify, simulate, certify.

---

## Surfaces

**API** — `/api/v1/platform/tg/operations/*`, 28 routes, all gated on
`PAPER_SAFETY_READ`. No route name contains deploy, restart, scale, connect, login,
oauth, credential, order, execute, canary, transfer, or withdraw.

**CLI** — `prod-*` (21 commands). The prefix is `prod-` rather than `ops-` because
`ops-*` is already owned by the M208 ops-graduation surface.

**UI** — `/trading/operations` plus `health`, `metrics`, `alerts`, `diagnostics`,
`backups`.

---

## Hard authority boundary

All eleven remain **FALSE**, asserted in code, in tests, in the API payloads, in the
rendered UI, and in the browser certification:

`REAL_CONNECTIVITY_AUTHORIZED` · `BROKER_CONNECTIVITY_AUTHORIZED` ·
`OAUTH_AUTHORIZED` · `CREDENTIAL_PROVISIONING_AUTHORIZED` ·
`ACCOUNT_ACCESS_AUTHORIZED` · `BALANCE_READ_AUTHORIZED` · `POSITION_READ_AUTHORIZED` ·
`ORDER_SUBMISSION_AUTHORIZED` · `ORDER_EXECUTION_AUTHORIZED` ·
`CANARY_ACTIVATION_AUTHORIZED` · `LIVE_TRADING_AUTHORIZED`

The inherited M320–M327 locks (credential validation, authentication, order history,
transfer, withdrawal, automated investment authority) are also carried forward and
re-asserted false.

---

## Limitations

- Offline operational observation only; no external telemetry or cloud monitoring.
- Alerts reach the control centre, local logs and audit history only.
- Recovery is simulated against local snapshots; live state is never mutated.
- Load validation is a deterministic model, not generated traffic.
- The operations dashboard is read-only; it exposes no execution or deployment control.
- No provider connectivity, credential, OAuth, account, order, canary or live-trading
  path exists or is created by this milestone.

---

## Evidence

`docs/trading/m328_m335_evidence/`
