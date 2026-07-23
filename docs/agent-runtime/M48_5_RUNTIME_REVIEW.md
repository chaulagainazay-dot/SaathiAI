# M48.5 — Runtime Architecture Review

**Milestone:** M48.5 (review / certification only — no merge, no deploy)  
**Review date:** 2026-07-23  
**Branch:** `milestone/m48-agent-runtime-baseline`  
**Verified HEAD:** `68de21690c257c961a483c85c0c086db197e61d1`  
**Draft PR:** [#3](https://github.com/chaulagainazay-dot/SaathiAI/pull/3)  
**Note on expected SHA:** Prompt listed `370ef40` (M48.3 tip). M48.4 advanced HEAD to `68de216`; PR head matches local HEAD. `370ef40` is an ancestor of current HEAD.

---

## 1. Series scope reviewed

| Milestone | Commit | Deliverable |
|---|---|---|
| M48.1 | `c1b2a8e` | Contracts, inventory, authority/approval vocabulary |
| M48.2 | `4ba2dda` | `start_agent_run` façade, wire validation at create_run |
| M48.3 | `370ef40` | `RunLifecycleController`, lease/cancel/timeout/recover |
| M48.4 | `68de216` | M8 `run_agent` wrap, skip_contract test-only, CancellationToken |
| M48.5 | (this review) | Closure review, residual risk, merge readiness |

---

## 2. Canonical runtime path (supported)

```text
Caller (API / CLI / chat orchestration / M8 run_agent wrap)
  → start_agent_run (service.py)
      → validate_run_request / ensure_run_request_allowed (fail-closed)
      → capability + authority + approval + provider honesty
  → Orchestrator.create_run (pre-persist contract gate unless TEST_ONLY skip)
  → RunStore (single durable run + events + lifecycle columns)
  → RunLifecycleController (lease, heartbeat, cancel, timeout, recover, reconcile)
  → Orchestrator.run
  → AgentExecutor (+ CancellationToken cooperative checks)
  → ExecutionGateway / tool path (side effects)
  → terminal state + evidence in RunStore
```

### Single-owner claims (M48 series)

| Concern | Single owner | Evidence |
|---|---|---|
| Public entry | `start_agent_run` | `saathi/agent_runtime/service.py` |
| Lifecycle ops | `RunLifecycleController` | `saathi/agent_runtime/lifecycle.py` |
| Multi-agent orchestration | `Orchestrator` | `saathi/agent_runtime/orchestrator.py` |
| Authority model | `contracts.AuthorityClass` + validators | `contracts.py` |
| Approval model | `ApprovalRequirement` + record validation | `contracts.py` + M10 task approval |
| Durable runs | `RunStore` | `saathi/agent_runtime/store.py` |
| Events / evidence | `RunStore.event` + lifecycle fields | store + lifecycle |
| Side-effect tools | ExecutionGateway / gateway_exec | existing M10/M17 path |

---

## 3. Path classification inventory

| Path | Classification | Notes |
|---|---|---|
| `start_agent_run` | **CANONICAL** | Only supported façade for new callers |
| API `POST /agents/runs` | **CANONICAL** | Via `start_agent_run` |
| CLI `run` / `run-team` | **CANONICAL** | Via `start_agent_run` |
| Chat `start_orchestration` | **CANONICAL** | Via `start_agent_run` |
| Chat `run_agent` (M8) | **WRAPPED** | Preserves M8 API; executes via `start_agent_run` + lease |
| Chat `delegate` | **WRAPPED** | Via `run_agent` |
| `Orchestrator.create_run` (default) | **CANONICAL** (internal) | Validates contracts pre-persist |
| `Orchestrator.create_run(skip_contract=True)` | **TEST_ONLY** | Requires `PYTEST_CURRENT_TEST`; else raises |
| `RunStore.create_run` | **LEGACY / low-level** | Persistence primitive; not a supported product entry |
| `AgentExecutor` / gateway turns | **CANONICAL** (internal) | After lease / run ownership |
| IELTS `saathi.agents` | **LEGACY** (deferred domain) | Out of general multi-agent runtime |
| EngineeringOrchestrator | **LEGACY** (deferred) | Separate engineering domain |
| Finance `execution/trade` | **PROHIBITED** for agent façade | Trading Guardian advisory-only |
| `saathi.agent.SaathiAgent` voice path | **LEGACY** (deferred product path) | Not M48 product entry |
| Direct FINANCIAL_EXECUTION | **BLOCKED / PROHIBITED** | Contract layer |

**Supported runtime bypass:** none found on production entry paths (API, CLI, chat orchestration, M8 wrap).

**Residual non-converged domains:** IELTS agents, engineering orchestrator, voice product path — classified LEGACY/deferred, not alternate supported multi-agent runtimes.

---

## 4. Lifecycle ownership

`RunLifecycleController` owns:

- cancel request / propagate / complete (idempotent)
- kill switch (run / mission / all active local runs)
- lease acquire / heartbeat / release semantics
- timeout / deadline enforcement hooks
- recover / reconcile surfaces (CLI exposed)

`Orchestrator.run` integrates controller for pre-run cancel, mid-run cancel, wall clock / deadline, lease + heartbeat.

---

## 5. Event and evidence model

- Validation emits `validation.passed` (or rejects before persist).
- Lifecycle emits `cancel.*`, `lease.*`, timeout/recovery-related events.
- Tasks, artifacts, checkpoints remain RunStore-owned.
- Outcome honesty: rejected `start_agent_run` returns `ok=False` / `status=rejected` (no false success).

---

## 6. Convergence verdict

```text
RUNTIME_CONVERGED_WITH_BOUNDED_LEGACY
M8_WRAPPED_BY_CANONICAL_RUNTIME
SINGLE_CANONICAL_ENTRY_ACTIVE
SINGLE_LIFECYCLE_OWNER
SINGLE_AUTHORITY_MODEL
SINGLE_APPROVAL_MODEL
SINGLE_RUNSTORE
```

Limitations that prevent absolute “fully converged everything in monorepo”:

1. Domain runtimes (IELTS / engineering / voice) remain deferred.
2. Tool cancellation is cooperative / partial for many adapters.
3. Distributed multi-host locking is not implemented (single-process lease model).

---

## 7. Reviewer conclusion

Architecture of M48.1–M48.4 is **internally consistent** for the agent multi-agent runtime. There is **one supported orchestration path**. Residual legacy is **bounded and documented**, not a silent parallel product runtime.
