# M10 Multi-Agent Runtime — Audit (Phase 1)

**Date:** 2026-07-10 · **Branch:** `milestone/m7-security-engine` @ `da46a5a`

## Existing agent-related code

| Location | Role | M10 disposition |
|----------|------|-----------------|
| `saathi/agents/` (master.py, bus.py, harness.py, router.py, sub_agents) | **IELTS "BMA"** coaching agent — MasterAgentLoop calls **Groq directly**, skill detection, pedagogy/bias harness | **KEEP, do not touch.** Domain-specific; Groq-direct so cannot be a general runtime. Not modified. |
| `saathi/chat/engine.py` `AGENT_ROLES` (planner/researcher/coder/reviewer/architect/writer/ceo) + `run_agent`/`delegate` + `agent_run` table | M8 single-agent runs, gateway-routed | **REUSE + extend.** The 7 roles seed the M10 registry; ChatEngine's gateway path is the inference bridge. |
| `saathi/execution/` (ToolIntent w/ `RiskLevel` L0–L4, `ApprovalLevel`, gateway `authorize/classify_risk/check_approval`) | ExecutionGateway | **REUSE.** Every agent action = ToolIntent through this gateway. Risk L0–L4 maps to M10 Risk 0–4. |
| `saathi/memory/engine/` (M9) | scoped memory, `retrieve_for_chat`, namespaces | **REUSE.** Agent memory scopes = M9 namespaces; delegation narrows namespace lists. |
| `saathi/events/bus.py` (repaired) | fabric event bus | **REUSE.** `run.*`/`agent.*`/`tool.*` events via `bus.publish_sync`. |
| `saathi/repair/` (critical manifest, baseline) | reliability | Add M10 checks only; internals untouched. |

## Findings

- **Duplicate risk:** M8 `run_agent` is a thin single-turn helper; M10 needs a
  durable orchestrator + DAG. Resolution: build `saathi/agent_runtime/` and
  have M8's `run_agent` remain (back-compat) while chat multi-agent mode calls
  the new orchestrator.
- **Direct-provider risk:** `saathi/agents/master.py` calls Groq directly — it
  is domain IELTS code, **out of M10 scope**, left as-is. M10 agents never call
  providers directly; they route through a gateway-backed `execute_fn`.
- **No existing DAG / delegation / approval-for-agents / checkpoints** — built
  fresh in `agent_runtime/`.
- **Gateway risk ladder present** (L0–L4) — reused rather than reinvented.

## Migration path (chosen)

New package `saathi/agent_runtime/` (`data/agent_runtime.db`):
models · registry · store · graph · policy · gateway_exec · orchestrator ·
api · cli. Reuses ChatEngine gateway inference, M9 memory, gateway ToolIntent,
event bus. M8 `agent_run` table preserved; new richer schema is additive.

## Compatibility constraints

- Do not modify M8/M9/gateway/repair internals (only additive manifest entry).
- Chat interface stays stable; multi-agent activates only when selected/justified.
- No agent bypasses ExecutionGateway; permissions narrow-only through delegation.
