# STRATEGY-MONITORING-1 — strategy health, degradation & observation governance

Branch `feature/nepse-completion`, from `a31a0c8e` (verified HEAD, clean, in sync).

## Discovery — what already existed

| Component | Verdict |
|---|---|
| `paper_activation/ops/models.HealthClass` (HEALTHY/WARNING/DEGRADED/CRITICAL/FAILED_SAFE) | **REUSE** — the canonical taxonomy; strategy states map onto it |
| `OperationalMonitor` (313 lines, 13 component checks) | **KEEP** — operational health: "are the workers up?" |
| `OperationalMonitor._component_strategy` | **KEEP** — counts ACTIVE/HALTED activations, not behaviour |
| `GraduationEngine` (312 lines) | **KEEP** — terminal campaign classification and the promotion authority |
| `regime.py` / `regime_classifier.py` / `regime_validation.py` | **REUSE** — `MarketRegimeEngine` already fails closed to UNKNOWN |
| `PERFORMANCE-ATTRIBUTION-V2`, `SHADOW-TRADING-1` | **CONSUME** — the observation inputs |

**The gap.** `_component_strategy` answers "are activations running?". `GraduationEngine`
answers "what was this campaign worth?" once it is COMPLETED. Neither answers
"is this strategy inside its operating envelope, right now?" — continuous,
in-flight, against thresholds frozen at qualification. That is the only thing
this milestone adds.

No second monitoring framework and no second health vocabulary: `StrategyHealth`
maps onto `HealthClass` through `HEALTH_CLASS_OF`, so `OperationalMonitor` can
keep aggregating with its existing `_worst`.

## The three rules the design is built around

1. **Monitoring is never authority.** It classifies and explains. `MonitorVerdict`
   carries `authorizes_execution=False` and `mutates_parameters=False` as
   non-init fields, and the module imports nothing execution-, network- or
   clock-capable.
2. **Bad data is never charged to the strategy.** A stale feed, a gap or a failed
   reconciliation yields `DATA_QUALITY_BLOCKED` and makes **no** performance
   claim — a 90% drawdown on untrustworthy data reports as blocked, not degraded.
3. **Not having watched long enough dominates.** `INSUFFICIENT_EVIDENCE` beats
   any mild performance verdict, so a strategy is never NORMAL merely because two
   trades happened not to lose. An unambiguous DEGRADED still surfaces through it.

## Point-in-time safety

Proven structurally rather than asserted: the module performs no lookup and holds
no clock. A test walks its AST and fails if `time`, `datetime`, `sqlite3`,
`requests`, `httpx` or `urllib` ever appear among its imports. Everything it
knows arrives in the `Observation` the caller supplies, so a future price,
revision, regime or outcome has no path in.

## Freezing the goalposts

Every threshold lives in a versioned `MonitorPolicy` with a content fingerprint
that travels in the verdict. Changing a threshold changes the fingerprint **and**
the `verdict_id`, so goalposts cannot be moved invisibly after seeing a result.
Hysteresis is explicit and versioned: recovering from WATCH requires clearing the
band by a margin, so a value parked on a threshold cannot flap.

## Limitations

- **Advisory only, by design.** `SUSPEND` authority already belongs to paper
  activation governance; monitoring does not duplicate or shortcut it, and emits
  no recommendation that any component consumes automatically.
- **No persistence layer added.** Verdicts are deterministic functions of their
  inputs and the policy, so they recompute identically rather than needing a
  store. Persisting a history is a separate decision, deliberately not taken here
  to avoid a second financial-truth store.
- **The observation adapter is not built.** Populating `Observation` from a live
  shadow session plus an attribution report is a thin mapping, but it is not
  written or certified in this milestone — the classification layer is.
- **Signal-behaviour health is coarse.** It watches count against an expected
  rate; direction distribution, conflicts and expiries are representable but not
  yet evaluated.
- **NEPSE remains unexercised**, as with attribution: no execution data exists.
