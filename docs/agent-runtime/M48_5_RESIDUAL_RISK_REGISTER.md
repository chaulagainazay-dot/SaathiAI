# M48.5 — Residual Risk Register

**Date:** 2026-07-23  
**HEAD:** `68de21690c257c961a483c85c0c086db197e61d1`  
**Classification vocabulary:** `ACCEPTED` | `NOT_ACCEPTED` | `BLOCKING`

---

## Summary

| ID | Title | Severity | Blocks merge? | Blocks deploy? | Classification |
|---|---|---|---|---|---|
| RR-01 | Bounded legacy domain runtimes | Medium | No | N/A (no deploy) | **ACCEPTED** |
| RR-02 | Partial cooperative tool cancellation | Medium | No | Yes for unattended long tools | **ACCEPTED** |
| RR-03 | Single-host lease (no distributed lock) | Medium | No | Yes for multi-host | **ACCEPTED** |
| RR-04 | M8 bridge dual records (chat + RunStore) | Low | No | No | **ACCEPTED** |
| RR-05 | Provider health not live-probed by default | Low | No | Context-dependent | **ACCEPTED** |
| RR-06 | Thin M48.3/M48.4 narrative docs | Low | No | No | **ACCEPTED** |
| RR-07 | Platform idempotency incomplete | Low–Med | No | Yes for multi-client retries | **ACCEPTED** |
| RR-08 | Deferred EngineeringOrchestrator | Low | No | No | **ACCEPTED** |
| RR-09 | Voice / SaathiAgent path not converged | Low | No | No | **ACCEPTED** |
| RR-10 | Streaming cancel incomplete for all media | Low | No | UX only | **ACCEPTED** |

**Blocking residual risks:** none identified for Draft PR review/merge decision under owner constraints (merge remains human-only; deploy not authorized).

---

## RR-01 — Bounded legacy domain runtimes

| Field | Value |
|---|---|
| Description | IELTS agents, engineering orchestrator, and some product voice paths are not full M10/M48 multi-agent runtime participants. |
| Impact | Parallel execution models remain in monorepo; risk of future callers reinventing entry points. |
| Likelihood | Medium (domain teams keep using local paths) |
| Severity | Medium |
| Mitigation | Inventory + classification; agent façade is canonical for multi-agent; finance path PROHIBITED |
| Future milestone | M49+ domain adapters or explicit permanent isolation ADRs |
| Blocks merge? | No |
| Blocks deployment? | No for agent-runtime-only scope |
| Classification | **ACCEPTED** |

---

## RR-02 — Partial cooperative tool cancellation

| Field | Value |
|---|---|
| Description | `CancellationToken` checked at agent/tool boundaries; many adapters are TIMEOUT_ONLY; hard abort of remote work not guaranteed. |
| Impact | Cancelled runs may leave external side effects mid-flight if tools ignore tokens. |
| Likelihood | Medium under long tool calls |
| Severity | Medium |
| Mitigation | Durable run CANCELLED state; no blind retry of uncertain mutations; kill switch for local active runs |
| Future milestone | M49 tool execution framework with mandatory cancel contracts |
| Blocks merge? | No |
| Blocks deployment? | Yes for unattended high-side-effect autonomy without extra gates |
| Classification | **ACCEPTED** |

---

## RR-03 — Single-host lease model

| Field | Value |
|---|---|
| Description | Lease ownership is durable in SQLite RunStore but not a distributed lock across hosts. |
| Impact | Two workers on different hosts could race if sharing the same DB without external coordination. |
| Likelihood | Low on single Mac / single process; higher if multi-host shares DB naively |
| Severity | Medium (architecture) |
| Mitigation | Document local-first model; recovery/reconcile for stale leases |
| Future milestone | Distributed execution / locking milestone |
| Blocks merge? | No |
| Blocks deployment? | Yes for multi-host active-active without redesign |
| Classification | **ACCEPTED** |

---

## RR-04 — M8 dual record bridge

| Field | Value |
|---|---|
| Description | Chat still records M8 `agent_run` rows for UI while also creating canonical RunStore runs. |
| Impact | Two IDs to correlate; possible drift if finish paths diverge. |
| Likelihood | Low–medium |
| Severity | Low |
| Mitigation | `canonical_run_id` linked in chat message meta; wrap uses start_agent_run |
| Future milestone | M49 chat UI consolidation on RunStore only |
| Blocks merge? | No |
| Blocks deployment? | No |
| Classification | **ACCEPTED** |

---

## RR-05 — Provider honesty without live probe

| Field | Value |
|---|---|
| Description | Default provider status is injectable / configuration-based; no paid live probes in M48. |
| Impact | Misconfigured “available” assumptions if callers pass optimistic flags. |
| Likelihood | Low with defaults; medium if mis-wired |
| Severity | Low |
| Mitigation | Fail-closed provider statuses; honesty helpers; tests for unavailable ≠ success |
| Future milestone | Observability / provider health service |
| Blocks merge? | No |
| Blocks deployment? | Depends on environment gates |
| Classification | **ACCEPTED** |

---

## RR-06 — Thin historical documentation slices

| Field | Value |
|---|---|
| Description | Several M48.3/M48.4 markdown files are short stubs relative to M48.1 depth. |
| Impact | Onboarding friction; incomplete narrative without reading code/tests. |
| Likelihood | Certain (observed) |
| Severity | Low |
| Mitigation | M48.5 certification pack consolidates review; tests encode contracts |
| Future milestone | Doc hardening optional in M49 |
| Blocks merge? | No |
| Blocks deployment? | No |
| Classification | **ACCEPTED** |

---

## RR-07 — Platform-level idempotency incomplete

| Field | Value |
|---|---|
| Description | Cancel is idempotent; full cross-request create_run idempotency keys for all entry paths are not a complete platform. |
| Impact | Duplicate runs possible under client retries without keys. |
| Likelihood | Medium for chatty clients |
| Severity | Low–Medium |
| Mitigation | Optional idempotency_key budget field; store-level patterns exist elsewhere (harness) |
| Future milestone | M49 workflow / run creation semantics hardening |
| Blocks merge? | No |
| Blocks deployment? | Yes for multi-client production without client discipline |
| Classification | **ACCEPTED** |

---

## RR-08 — EngineeringOrchestrator deferred

| Field | Value |
|---|---|
| Description | Engineering domain remains separate; optional façade deferred. |
| Impact | Two mental models for “orchestration” in engineering vs agent_runtime. |
| Likelihood | Medium for engineers reading both |
| Severity | Low |
| Mitigation | Documented DEFER_WITH_REASON; no agent façade claim of ownership |
| Future milestone | Optional M49 adapter |
| Blocks merge? | No |
| Blocks deployment? | No |
| Classification | **ACCEPTED** |

---

## RR-09 — Voice / SaathiAgent path not converged

| Field | Value |
|---|---|
| Description | Product voice agent path not rewritten through start_agent_run. |
| Impact | Voice may bypass multi-agent contracts if used for agent-like work. |
| Likelihood | Low in current M48 scope |
| Severity | Low |
| Mitigation | Deferred classification; do not market as M48 runtime |
| Future milestone | Voice runtime theme in M49 roadmap |
| Blocks merge? | No |
| Blocks deployment? | No for agent_runtime PR |
| Classification | **ACCEPTED** |

---

## RR-10 — Streaming cancel incomplete

| Field | Value |
|---|---|
| Description | Streaming/media tools often timeout-only; cooperative cancel not universal. |
| Impact | UX stop may lag actual stream end. |
| Likelihood | Medium during media generation |
| Severity | Low |
| Mitigation | Run-level cancel + documented streaming contract |
| Future milestone | M49 tool framework |
| Blocks merge? | No |
| Blocks deployment? | No |
| Classification | **ACCEPTED** |

---

## Acceptance statement

All residual risks above are **ACCEPTED** for M48 series **review/merge readiness with limitations**. None are **BLOCKING** for Draft PR human review. None authorize silent production go-live.

```text
RESIDUAL_RISKS_CLASSIFIED
NO_BLOCKING_RESIDUALS_FOR_REVIEW
```
