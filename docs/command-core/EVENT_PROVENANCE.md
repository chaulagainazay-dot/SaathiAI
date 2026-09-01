# Command Core — Event Provenance Map

MOTION REFLECTS TRUTH. MOTION NEVER CREATES TRUTH.

Phase 4 audit of `feature/central-command-core`, base `b390d51`. Every conceptual
Command Core event is traced to a real producer in this repository, or marked
UNAVAILABLE. Nothing here was invented to complete the table.

## Decision: no new event bus

SaathiOS already has one. `saathi/events.py` is the Event Fabric bus
(`subscribe`, `publish`, `publish_sync`). `saathi/eventstream.py` subscribes with
a wildcard and relays every event over SSE at `GET /api/events/stream` as
`{name, dept, payload, ts}`. The frontend already consumes it through
`components/live/LiveProvider.jsx` (`useLive`).

Decisively: `saathi/agent_runtime/store.py::event()` writes each run event to the
`run_event` table **and mirrors it to the fabric bus as `agentrun.<name>`**. The
run-level lifecycle is therefore already reachable from the browser over the
existing SSE transport, and also by polling `GET /runs/{rid}/events`.

**A second event bus is unnecessary and is not being built.**

## Authority classes

- **AUTHORITATIVE** — the system that owns the decision emitted it.
- **TRUSTED_RUNTIME** — real runtime fact, not an authority decision.
- **DERIVED** — computed from other truth; not itself a backend assertion.
- **ADVISORY** — informational; must never gate execution.
- **UNAVAILABLE** — no producer exists in this repository.

## Ordering sources

| Source | Ordering | Isolation |
|---|---|---|
| `run_event` table | `created_at`, `ORDER BY created_at`; row `id` for dedupe | `run_id` |
| Fabric bus / SSE | `ts` stamped in `enrich()` | `payload.run_id` on `agentrun.*` |
| Voice session | in-process provider state; no sequence number | single owner |
| REST snapshots | response-time only; no version or ETag | resource id |

**Limitation, recorded rather than papered over:** the fabric bus provides no
sequence number or version, only a wall-clock `ts` stamped at relay time. Two
events published inside the same clock tick are not orderable, and the backend
offers no monotonic counter. The adapter therefore treats `created_at`/`ts` as a
partial order and additionally dedupes by row `id`. It does not claim total
ordering.

## The map

| Conceptual event | Real producer | Existing channel | Payload used | Authority class | Command Core mapping | Fallback |
|---|---|---|---|---|---|---|
| `voice.capture.started` | `VoiceSessionManager` via `VoiceSessionProvider` | React context (`useVoiceSession`) | `session.state` → `LISTENING` | TRUSTED_RUNTIME | LISTENING | none needed; provider is always mounted in `Shell.jsx` |
| `voice.energy.changed` | `lib/voice-session/energy-vad.js` (`frameRms`) | in-process, surfaced as `view.rms` in `VoiceDiagnosticsPanel` | `rms` | TRUSTED_RUNTIME | LISTENING amplitude (CONTINUOUS) | omit amplitude; LISTENING still renders from state |
| `voice.transcript.partial` | `VoiceSessionManager` | context | `session.transcriptPartial` | TRUSTED_RUNTIME | growing user turn | render committed text only |
| `voice.transcript.final` | `VoiceSessionManager` | context | `session.transcriptFinal` | TRUSTED_RUNTIME | UNDERSTANDING | — |
| `assistant.processing.started` | `VoiceSessionManager.setThinking()` | context | `session.state === "THINKING"` | TRUSTED_RUNTIME | THINKING | — |
| `assistant.speaking.started` | `VoiceOutputProvider` / session | context | `session.state === "SPEAKING"` | TRUSTED_RUNTIME | SPEAKING | — |
| `assistant.speaking.ended` | same | context | state leaves `SPEAKING` | TRUSTED_RUNTIME | exit SPEAKING | — |
| `agent.delegated` | `agent_runtime/store.py` | `run_event` + `agentrun.delegation.created` | `run_id`, `created_at` | TRUSTED_RUNTIME | DELEGATING | — |
| `agent.started` | `agent_runtime/store.py` | `run_event` + `agentrun.agent.started` | `run_id`, `created_at` | TRUSTED_RUNTIME | SUPERVISING once Saathi is quiet | — |
| `agent.completed` | **no direct producer** | closest: `run.state`, `review.completed` | `run.state` payload | DERIVED | leave SUPERVISING when no run is active | treat as unknown; never assume completion |
| `approval.requested` | `agent_runtime/store.py`; `platform/service.py` | `run_event` + `agentrun.approval.requested`; REST `/api/v1/control/approvals` | `run_id`, approval id | AUTHORITATIVE | WAITING_APPROVAL | REST pending-approvals poll |
| `approval.granted` | `approval.resolved` / `platform/service.py::approval.decided` | `run_event` + REST decide endpoint | outcome field in payload | AUTHORITATIVE | leaves WAITING_APPROVAL; sets `approvalGranted` | — |
| `approval.denied` | same | same | outcome field | AUTHORITATIVE | leaves WAITING_APPROVAL; no execution grant | — |
| `guardian.blocked` | **no producer on the agent-runtime path** | `agent_runtime/contracts.py:494` pins `"trading_guardian": "ADVISORY_ONLY_UNENGAGED"` | — | UNAVAILABLE | BLOCKED cannot be produced from agent runtime | adapter accepts an explicit `guardian` input from the trading path; absent that, BLOCKED never asserts |
| `execution.started` | **no producer** on the run event log | nearest is `tool.requested`, which is a REQUEST, not a start | — | UNAVAILABLE | not mapped | `tool.requested` surfaces as "requested", never as "executing" |
| `execution.completed` | `saathi/execution/trade.py` (`execution.filled`, `execution.failed`, `execution.partial_fill`) | trading execution path, separate from the run log | fill state | AUTHORITATIVE | EXECUTING → VERIFYING when supplied | unmapped for non-trading runs |
| `verification.completed` | `agent_runtime/store.py` | `run_event` + `agentrun.verification.passed` / `.failed` | outcome, `run_id` | AUTHORITATIVE | VERIFYING, then verified/failed | **never synthesised** — absence renders "verification unavailable" |
| `system.degraded` | infra health via `fetchInfraHealth()`; `command-read-model.js:444` | REST poll | `system.models.status`, `system.gateway.status` | ADVISORY | orthogonal `degraded` flag | `degraded: false` with `UNKNOWN` provenance |

## Findings that change the design

1. **`agent.delegated` is real, not derived.** `delegation.created` is a first-class
   run event. It is labelled TRUSTED_RUNTIME, not DERIVED.
2. **`agent.completed` has no producer.** Only `run.state` and `review.completed`
   exist. Completion is DERIVED and must never be asserted from silence or elapsed
   time.
3. **`verification.passed` / `verification.failed` are real.** SaathiOS already
   distinguishes execution from verification. `EXECUTION COMPLETE — VERIFICATION
   UNAVAILABLE` is a reachable, honest state and the adapter models it.
4. **`guardian.blocked` is UNAVAILABLE from the agent runtime, by design.** The
   agent runtime declares Trading Guardian `ADVISORY_ONLY_UNENGAGED`. The Command
   Core must not manufacture BLOCKED; it accepts a Guardian verdict only when the
   trading path supplies one.
5. **`execution.started` does not exist on the run log.** `tool.requested` is a
   request. Presenting it as EXECUTING would be exactly the fabrication this
   milestone forbids.

## DEGRADED: orthogonal, not exclusive

Saathi can truthfully be SPEAKING while a provider is degraded. Forcing one state
to erase the other would lose a fact. `deriveCommandCoreState()` therefore returns
`degraded` as a flag on every snapshot, and resolves the state to `DEGRADED` only
when no more specific state is active.

## Precedence (final)

Authority preempts presentation, always:

```
BLOCKED > WAITING_APPROVAL > VERIFYING > EXECUTING
        > SPEAKING > DELEGATING > THINKING > UNDERSTANDING > LISTENING
        > SUPERVISING > DEGRADED > IDLE
```

`degraded` and `supervising` remain true on the snapshot regardless of the
resolved state, so the mission and health panels never lose their truth just
because the central presence is showing something else.
