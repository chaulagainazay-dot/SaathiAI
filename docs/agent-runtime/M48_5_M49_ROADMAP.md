# M48.5 — Recommended M49 Roadmap

**Status:** Planning only — **M49 not started**  
**Date:** 2026-07-23  
**Based on:** M48 residual risks + architecture review  

---

## Intent

After M48 establishes a single canonical agent runtime baseline, M49 should improve **depth of execution quality** without re-forking orchestration, authority, approval, or RunStore.

**Non-goals for early M49:**

- Live trading autonomy  
- Weakening Trading Guardian  
- Replacing ExecutionGateway with a second gateway  
- Silent multi-host production without lease redesign  

---

## Ranked themes (engineering value)

| Rank | Theme | Value | Why now | Depends on | Residual closed |
|---|---|---|---|---|---|
| 1 | **Tool execution framework** | Highest | Cancel/retry/evidence parity incomplete | M48 CancellationToken | RR-02, RR-10 |
| 2 | **Observability** | High | Provider honesty + ops visibility | Provider status contracts | RR-05 |
| 3 | **Run creation / idempotency maturity** | High | Client retry safety | start_agent_run + budget keys | RR-07 |
| 4 | **Chat dual-record consolidation** | Medium-High | Single evidence model in UI | M8 wrap | RR-04 |
| 5 | **Workflow engine (bounded)** | Medium-High | Multi-step business automations on canonical runtime | lifecycle + strategies | — |
| 6 | **Memory evolution** | Medium | Stronger isolation + project scopes | memory boundaries | — |
| 7 | **Agent collaboration** | Medium | Multi-agent handoff quality beyond linear DAG | registry/orchestrator | — |
| 8 | **Scheduler maturity** | Medium | Integrate harness/mission schedules safely | do not duplicate mission engine | RR-01 partial |
| 9 | **Plugin framework** | Medium | Controlled extension without bypass | contracts + capability registry | — |
| 10 | **Domain adapters (IELTS/engineering)** | Medium | Explicit wrap or permanent isolation ADR | inventory | RR-01, RR-08 |
| 11 | **Distributed execution** | Medium-Low short term | Multi-host only if needed | lease redesign | RR-03 |
| 12 | **Business automation surfaces** | Medium-Low | Product value after tool framework | workflows + approvals | — |
| 13 | **Voice runtime convergence** | Lower (product path) | Optional if voice uses agent tools | product design | RR-09 |

---

## Suggested M49 slices (bounded)

### M49.0 — Planning & backlog formalization (docs only)

- Import this roadmap into `docs/AUTONOMOUS_ROADMAP.md`  
- File residual risks as tracked debt  
- Define success metrics (cancel coverage %, dual-ID elimination)

### M49.1 — Tool execution framework (primary)

- Mandatory cancel/timeout contracts for adapters  
- Uniform evidence records for tool outcomes  
- No silent success for unknown tools (already partially true — harden)  
- Regression tests for cancel-during-tool

### M49.2 — Observability & provider health

- Structured metrics/events for run lifecycle  
- Optional non-paid health probes behind flags  
- Dashboards read-only (Control Center reuse)

### M49.3 — Idempotent run creation

- Documented idempotency keys on API/chat  
- Deterministic reuse vs conflict behavior  
- Tests for concurrent duplicate creates

### M49.4 — Chat evidence consolidation

- Prefer RunStore as source of truth  
- Reduce dual agent_run bookkeeping  
- Preserve M8 API shape if required

### Later (M49.5+)

- Workflow engine on canonical runtime  
- Plugin capability registration with fail-closed contracts  
- Domain adapters or explicit permanent isolation  
- Distributed lease only with multi-host requirement  
- Voice path convergence if product demands it  

---

## Explicitly out of M49 without separate authorization

```text
LIVE_TRADING
LEVERAGE_ENABLEMENT
WITHDRAWAL_PERMISSIONS
REMOVE_TRADING_GUARDIAN
AUTO_MERGE_WITHOUT_REVIEW
PRODUCTION_DEPLOY_WITHOUT_GATE
```

---

## Success definition for “M49 started”

M49 starts only when owner authorizes a new milestone branch/slice **after** human disposition of Draft PR #3 (merge or continue).

```text
M49_NOT_STARTED
ROADMAP_DOCUMENTED_ONLY
```
