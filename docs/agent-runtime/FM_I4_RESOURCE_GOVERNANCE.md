# FM-I4 — Harness Resource Governance and Session Scheduling

**Status:** Internal non-production governance proof  
**Date:** 2026-08-07  
**Authorized baseline:** FM-I3 @ `4ebcd71c9489823bd7c53a44822d0bb572abf012`  
**Branch:** `implementation/fm-i4-resource-governance`  
**Production certified:** **False**

---

## Scheduler ownership decision

| Component | Owner | Relation to FM-I4 |
| --- | --- | --- |
| `application_harness.MissionScheduler` | M17.14 mission scheduling | **Separate** — creates mission occurrences only; never runs AgentHarness |
| `application_harness.MonitorScheduler` / `SchedulerRunner` | Host/mission monitors | **Separate** — no AgentHarness admission |
| TG `ExperimentScheduler` | Trading research | **Separate** — TG domain |
| Platform cluster scheduler_plan | Platform control plane | **Separate** |
| `execution.queue` | ExecutionGateway pipeline | **Separate** — tool intents only |
| **`HarnessSessionGovernor`** | `saathi.agent_runtime.harness` | **New, scoped** — in-process admission/queue/limits for AgentHarness only |

FM-I4 does **not** create a second general-purpose OS/cloud scheduler.

---

## Resource source-of-truth (summary)

| Resource | Policy owner | Live enforcement | Durable snapshot |
| --- | --- | --- | --- |
| Global/org/workspace active slots | `HarnessResourcePolicy.admission` | `HarnessSessionGovernor` | export metadata / active map |
| Queue capacity | `HarnessQueuePolicy` | Governor | queue entries |
| Turns/events/tokens/output/tools | `HarnessResourcePolicy` session fields | Governor + controller | harness durable usage snapshot (FM-I3) |
| Timeouts | `HarnessTimeoutPolicy` | Governor `check_timeouts` | deadlines in metadata export |
| Reservations | Governor | atomic reserve/release | reservation records |
| Run lifecycle | RunState | platform | not owned by governor |

---

## Components

| Module | Role |
| --- | --- |
| `governance_policy.py` | Frozen policies + decision enums |
| `governance.py` | `HarnessSessionGovernor` |
| Controller injection | `governor=` / `resource_policy=` / `enable_governance=` |

---

## Explicit non-actions

No FM-I5 · no Ollama/providers/CLIs · no Redis/Celery/Kafka · no background auto-continue · no production workers · no AgentSessionAdapter change · no EG replacement.

## Freeze disposition

FZ-01 partial unfreeze retained; FZ-02 / FZ-07 fully retained.
