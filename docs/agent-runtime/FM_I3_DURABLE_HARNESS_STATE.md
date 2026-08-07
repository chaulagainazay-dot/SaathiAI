# FM-I3 — Durable Session, Event, and Replay Persistence

**Status:** Internal non-production durability proof  
**Date:** 2026-08-07  
**Authorized baseline:** FM-I2 @ `dd09ca033dd335694975b42102d11b0375a4e53e`  
**Branch:** `implementation/fm-i3-durable-harness-state`  
**Production certified:** **False**

---

## Primary success question

Can SaathiOS safely persist and recover harness sessions, normalized events,
execution/approval **references**, cancellation, quarantine, resource snapshots,
and terminal outcomes while preserving RunState, ExecutionGateway, Approval,
audit, and evidence as existing authoritative systems?

**Yes — with limitations** (isolated SQLite only; inspection replay only; no auto-resume).

---

## Source-of-truth matrix (summary)

| Concern | Authority | FM-I3 stores |
| --- | --- | --- |
| Run lifecycle | `RunState` / RunStore | projection snapshot only |
| Harness session state | Controller projection | durable projection |
| Normalized events | Controller normalize path | immutable append log |
| Event watermark | Durable store | transactional with events |
| ToolIntent | Controller + EG | **nothing** |
| Execution record | ExecutionGateway store | `pending_execution_id` only |
| Approval status | Approval / EG bindings | `pending_approval_reference` only |
| Audit / evidence / cert | Existing systems | **nothing** |

Full matrix: `saathi.agent_runtime.harness.persistence.SOURCE_OF_TRUTH`.

---

## Store architecture

| Component | Path |
| --- | --- |
| Models / integrity / recovery enums | `saathi/agent_runtime/harness/persistence.py` |
| SQLite store | `saathi/agent_runtime/harness/durable_store.py` (`HarnessDurableStore`) |
| Controller injection | `HarnessSessionController(durable_store=...)` |

- No process-default singleton DB.
- Tests use isolated `tmp_path` databases.
- Schema version `1.0` with fail-closed unsupported versions.

---

## Transaction boundaries

`append_event` is atomic:

1. validate session integrity + scope + sequence
2. insert event
3. advance watermark + projection fields
4. re-seal session integrity hash
5. commit (or full rollback)

---

## Recovery dispositions

`RECOVER_READY` · `RECOVER_RUNNING_AS_PAUSED` · `RECOVER_WAITING_FOR_APPROVAL` ·
`RECOVER_CANCELLED` · `RECOVER_TERMINAL` · `QUARANTINE_STALE` · `QUARANTINE_CORRUPT` ·
`QUARANTINE_AUTHORITY_CONFLICT` · `ABANDON_ORPHANED`

**`can_continue` is always False for automatic work.** No auto tool execution, no auto model resume.

---

## Replay

`replay_timeline` / `controller.replay_session` — **inspection only**:

- ordered events, state reconstruction, resource timeline
- `can_execute=False`
- never calls ExecutionGateway handlers

---

## Explicit non-actions

No FM-I4 · no providers · no credentials · no shared production DB · no scheduler ·
no AgentSessionAdapter change · no second RunStore/Approval/Audit store.

## Freeze disposition

FZ-01 remains partially unfrozen for internal proof; FZ-02 / FZ-07 fully retained.
