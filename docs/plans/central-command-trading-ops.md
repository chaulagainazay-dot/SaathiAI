# CENTRAL-COMMAND-TRADING-OPS — deterministic trading status in Central Command

Branch `feature/nepse-completion`, start `94ff9cf6` (recovered from repository
reality, clean, in sync). The end-to-end chain was verified present before any UI
work: SHADOW-TRADING-1 → PERFORMANCE-ATTRIBUTION-V2 → STRATEGY-MONITORING-1 →
STRATEGY-OBSERVATION-1 → TRADING-OPS-1 → TRADING-HEALTH-PRODUCERS-1 →
HEALTH-COLLECTOR-1.

## Discovery

| Surface | Verdict |
|---|---|
| `app/command/page.jsx` (1084 lines) — the live Central Command page | **ADAPT** — one panel added, nothing redesigned |
| `lib/command-authority.js` — `TruthState` vocabulary, `truthStateToBadgeStatus`, "never fabricates healthy/green without evidence" | **KEEP** — mapped into, not forked |
| `components/command/SystemHealthPanel.jsx` | **KEEP, unused** — an orphan from an earlier milestone; its row grammar is reused, the component is not resurrected |
| `lib/platform-client.js::plat()` — authenticated platform fetch | **KEEP** — the one transport |
| `/tg/paper/ops/health`, `/tg/operations/health` | **REJECT as source** — different services (paper monitor, production-readiness ops); neither serves the canonical snapshot |
| `pg_scheduler` | **DEFER** — paper-scoped and disabled by default |

No second Central Command trading surface was created.

## Collector hosting decision

**Request-driven, coalesced.** The status route calls `service.status(now=…)`,
which ticks the collector; the collector's own minimum interval means a burst of
page loads produces one collection. No thread, no daemon, no new scheduler — the
brief forbids a process manager, and `pg_scheduler` is the wrong scope.

The honest consequence is that cadence is visible rather than hidden: freshness
travels in the payload, so an operator can see the collector's behaviour instead
of trusting an invisible background loop.

## The two states this milestone exists to keep apart

```
SUBSYSTEM_INSUFFICIENT_EVIDENCE   the collector ran; a subsystem could not be judged
SNAPSHOT_STALE                    the collector has not run; NOTHING here is current
```

The second is the dangerous one. **A monitor that stops collecting keeps serving
its last cheerful answer forever**, and a frozen green panel is indistinguishable
from a live one. So freshness is recomputed at *read* time — never cached
alongside the snapshot, because a snapshot that was fresh when collected becomes
stale by sitting still — and `reflects_current_state` gates the entire display.

`tradingOpsView` renders `displayState: "STALE"` and every subsystem row as
`STALE` when that flag is false, whatever the recorded values say. A payload
missing the flag is treated as not current, so an older server cannot read fresh.

## What was built

| Layer | File |
|---|---|
| Serving edge | `saathi/platform/tg/ops_status.py` (181) |
| Route | `GET /api/v1/platform/tg/operations/trading-ops`, `PAPER_SAFETY_READ` |
| View model (pure) | `saathi-os/lib/trading-ops-view.js` (201) |
| Fetch hook | `saathi-os/lib/useTradingOps.js` (59) |
| Panel | `saathi-os/components/command/TradingOpsPanel.jsx` (117) |

**One route, one snapshot.** The five producers are never called from React and
no subsystem authority is reachable from the browser. The UI maps
`HealthClass → TruthState` and lays out; it computes no health, merges no states,
and ranks no severity. A test proves the overall state is *read* from the
snapshot even when the rows disagree with it — otherwise the UI would be a second
aggregator with its own precedence.

The route wires only subsystems with verified safe reads — Guardian and the kill
switch. Market data, provider and approval report INSUFFICIENT_EVIDENCE, which is
the truth: this process holds no live feed supervisor, and handing the collector
a fabricated stand-in would be worse than reporting nothing. A test pins the
wiring list so a future edit cannot quietly add an invented source.

## Verification

- **22 backend tests**, **19 Node tests** (registered in `package.json`)
- **223 passed** across the backend trading suites; **1006 passed** frontend
- **`next build` exit 0** — `/command` compiled, panel present in the built chunk
- **`npm run lint`: 0 errors** (3 pre-existing warnings in unrelated cert scripts)
- **Browser-validated** on the real dev server at desktop and mobile (375×812)

### Browser evidence

Unauthenticated, the panel renders `TRADING OPERATIONS — UNKNOWN`, `Mode UNKNOWN`,
`Live trading not authorised`, `Not collected yet — no trading health is being
reported`. That is the safety assertion made visible: **no green without
evidence**, and no operator can mistake an unconfigured panel for a healthy
system. Mobile keeps the badge and text legible.

## Zero mutation from a status read

| Counter | Value |
|---|---|
| APPROVAL_STATE_TRANSITIONS | 0 |
| APPROVAL_CONSUMPTIONS | 0 |
| PROVIDER_STATE_INSERTIONS | 0 |
| RECONCILIATION_CALLS | 0 |
| RECOVERY_CALLS | 0 |
| KILL_SWITCH_MUTATIONS | 0 |
| REAL_ORDER_ATTEMPTS | 0 |
| PRIVATE_API_CALLS | 0 |
| REAL_LEDGER_MUTATIONS | 0 |
| PARAMETER_MUTATIONS | 0 |

Proven dynamically against real objects: a lapsed approval is still PENDING with
`decided_at is None` after a status read; an APPROVED approval is unconsumed;
five simulated page loads leave the provider registry's cardinality unchanged;
an engaged kill switch is byte-identical afterwards.

## Security

No credentials, tokens, cookies, URLs, subprocess or `eval` in any new file. A
test serialises the payload and asserts no credential marker; another drives an
exception carrying a filesystem path and asserts neither the path nor a traceback
reaches the response.

## Certification, with limitations

**CENTRAL_COMMAND_TRADING_OPS_CERTIFIED_WITH_LIMITATIONS.**

1. **LLM narration was deliberately NOT built.** The certification list asks for
   optional governed narration; the deterministic copy delivers the entire
   safety-critical requirement without a model, and adding an LLM call would
   introduce a provider dependency that adds no operational truth. The governed
   path (`tools_llm_helper`) is available when narration is genuinely wanted.
   Recorded as not-built rather than claimed.
2. **Cadence is request-driven.** No background loop refreshes the snapshot; a
   page nobody opens collects nothing. Freshness makes this visible instead of
   hiding it.
3. **Three of five subsystems report insufficient evidence in this process** —
   market data, provider and approval have no safely-readable live instance at
   the route. Truthful, and the operator is told to verify manually.
4. **No screenshot artefacts were committed.** Browser evidence was captured
   interactively; the repository's `cert:*` script convention was not extended,
   as a new cert script would be scope this milestone does not need.
5. **NEPSE licence-blocked, no live trading, no real broker** — unchanged.

### Invariants held

`NO_UI_HEALTH_AUTHORITY`, `NO_UI_EXECUTION_AUTHORITY`, `NO_STATUS_READ_MUTATION`,
`NO_APPROVAL_EXPIRY_FROM_STATUS_READ`, `NO_PROVIDER_CREATION_FROM_STATUS_READ`,
`NO_RECONCILIATION_FROM_STATUS_READ`, `NO_RECOVERY_FROM_STATUS_READ`,
`NO_KILL_SWITCH_MUTATION_FROM_STATUS_READ`, `NO_STALE_SNAPSHOT_AS_CURRENT_HEALTH`,
`NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`, `NO_FALSE_LIVE_LABEL`, `NO_LIVE_TRADING`,
`NO_LLM_EXECUTION_AUTHORITY`.
