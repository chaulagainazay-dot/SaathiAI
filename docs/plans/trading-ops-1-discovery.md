# TRADING-OPS-1 — discovery map (before any code)

Branch `feature/nepse-completion`, HEAD `d206af05` (verified from repository
reality, clean tree, in sync with origin).

## Verdict table

| Component | Location | Lines | Verdict |
|---|---|---|---|
| `HealthClass` — HEALTHY/WARNING/DEGRADED/CRITICAL/FAILED_SAFE | `paper_activation/ops/models.py` | 83 | **KEEP** — the canonical health vocabulary. Do not invent another. |
| `OperationalMonitor` — 15 components, `_worst` precedence, persists `pg_ops_health` | `paper_activation/ops/monitoring.py` | 313 | **KEEP + CONSUME** — the paper-subsystem health authority |
| `resilience` — `FailureMode`/`Response`/`degrade`/`worst` | `tg/resilience.py` | 122 | **KEEP + CONSUME** — the canonical degradation policy |
| `KillSwitchStore` — activate/deactivate/is_blocked/status/audit | `tg/kill_switch.py` | 161 | **KEEP** — the kill-switch authority |
| `StrategyHealth` + `HEALTH_CLASS_OF` | `tg/strategy_monitor.py` | 527 | **KEEP + CONSUME** — the strategy authority |
| `observation_from_shadow` | `tg/strategy_observation.py` | 353 | **KEEP + CONSUME** — certified last milestone |
| `ShadowSessionStore.reconcile/resume` | `tg/shadow_session.py` | 576 | **KEEP + CONSUME** — the shadow authority |
| `IncidentResponse` — 13 security incident types, 10 workflow steps | `connectivity_governance/incident_response.py` | 116 | **KEEP** — security incident authority, separate concern |
| paper store `list_incidents(status=...)` | `paper_activation/durable/store.py` | — | **KEEP** — ops incident persistence |
| `playbook_for` / `list_playbooks` | `private_alpha/incidents.py` | 221 | **KEEP** — runbook references |
| `run_recovery_suite` | `tg/recovery.py` | 237 | **KEEP** — recovery authority |
| `CommandSurface` / `PanelStatus` | `tg/command_surface.py` | 173 | **ADAPT** — see below |
| A cross-stack operations snapshot | — | — | **MISSING — this milestone** |

Counts confirm the brief's warning: incident-related ~35 files, recovery ~75,
kill-switch ~39. **No new incident system, recovery framework or kill switch is
being built.**

## The two findings that define the work

### 1. `CommandSurface` is a renderer wired to nothing

It already aggregates five panels read-only with precedence-based overall status
— genuinely good, and its `READ_ONLY` flag is test-asserted. But every input is a
caller-supplied keyword: `provider_health=`, `guardian=`, `kill_switch=`, `oms=`,
`reconciliation=` … thirteen of them. Nothing in the repository assembles those
arguments from the actual authorities. So no caller can answer *"is trading safe
right now?"* without hand-building the answer first — which is precisely the
question this milestone exists to make answerable.

### 2. Two health vocabularies already coexist

- `HealthClass` — HEALTHY / WARNING / DEGRADED / CRITICAL / FAILED_SAFE
- `PanelStatus` — OK / DEGRADED / BLOCKED / UNKNOWN

`strategy_monitor` already maps into `HealthClass`. `HealthClass` is therefore
canonical, and `PanelStatus` is a presentation vocabulary. TRADING-OPS-1 speaks
**only** `HealthClass` and maps to `PanelStatus` explicitly at the render edge —
it does not fork a third vocabulary, and does not introduce colour names.

### 3. `OperationalMonitor` sees only the paper store

Its fifteen components all read `gov.store` (the paper governance sqlite). It has
no view of market data, Guardian, shadow sessions, strategy verdicts, or the kill
switch store. It is the right authority for paper, and the wrong place to add the
rest — extending it would make a paper-scoped monitor pretend to global scope.

## Conclusion — the smallest missing canonical layer

One typed, derived `TradingOperationsSnapshot` that **binds existing authorities**:

```
KillSwitchStore ─┐
OperationalMonitor ─┤
strategy_monitor ─┤→ trading_ops.snapshot() → TradingOperationsSnapshot
shadow_session ─┤     (one HealthClass, explicit precedence,
resilience ─┘          typed operator actions, explicit cutoff)
```

It computes no health an authority already computes, owns no threshold, persists
nothing, and holds no execution authority.
