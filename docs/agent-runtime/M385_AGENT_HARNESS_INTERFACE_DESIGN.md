# M385 — SaathiOS AgentHarness Interface Design

**Status:** DESIGN COMPLETE — no production code, adapters, providers, or runtime changes
**Date:** 2026-08-06
**Verdict:** `AGENT_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS`
**Branch:** `milestone/m369-m376-local-model-qualification`
**Baseline SHA:** `949afa68a4135aa94dbdaaf9aecfd618e0948c09`
**Formal ADR:** [`docs/adr/ADR-AGENT-HARNESS-INTERFACE.md`](../adr/ADR-AGENT-HARNESS-INTERFACE.md)
**Parent:** M377–M384 `ADAPT_SELECTED_PATTERNS` · ADR-QM-MULTI-AGENT-RUNTIME

---

## Integrity statement

This milestone changes **documentation only** under `docs/adr/`, `docs/agent-runtime/`,
and (if needed) `docs/AUTONOMOUS_ROADMAP.md`.

It does **not**:

- implement adapters or production types;
- import QM or any third-party harness source;
- connect providers or add credentials;
- change ExecutionGateway, Approval, RBAC, audit, certification, provider governance,
  or Trading Guardian behavior;
- introduce an ExecutionGateway bypass.

---

# M385.1 — Current-state discovery

## Existing contracts (compose; do not duplicate)

| Concern | Existing owner | Key artifacts |
| --- | --- | --- |
| Agent runtime / multi-agent runs | `saathi.agent_runtime` | Orchestrator, RunStore, service, strategies |
| Run request contract | `contracts.py` (M48.1) | `AgentRunRequest`, AuthorityClass, KNOWN_CAPABILITIES |
| Run state machine | `models.RunState` | CREATED…PARTIALLY_COMPLETED; illegal transitions enforced |
| Lifecycle / lease / cancel | `lifecycle.py` (M48.3) | leases, cancel, timeout, recovery classes |
| Missions | missions / platform / graph | Layered; must not replace M10 |
| Sessions (credential/browser) | M35/M36/M38 session models | Distinct from harness sessions |
| Providers / model routing | ModelRouter, M21–M25, M32 | Provider selection, quarantine, kill switches |
| Tool requests | `gateway_exec` + policy.check_tool | Allow/deny, risk ceiling |
| ExecutionGateway | `execution/gateway.py`, universal boundary | Sole external-action authority |
| ToolIntent | `execution/toolintent.py` | Immutable; correlation_id; idempotency_key |
| Approvals | M10 approval_request + M35 envelopes | Fail-closed; no agent self-approve |
| Audit / evidence | RunStore events + Evidence | Append-oriented |
| Replay | Application harness / tape concepts elsewhere; run checkpoints | RunStore.checkpoint |
| Cancellation | lifecycle + CancellationToken (cooperative) | Kill switch run/mission/all |
| Idempotency | ToolIntent idempotency_key; durable tool_runtime | No blind retry of mutations |
| Streaming | Chat/eventstream surfaces | Run events ordered by created_at |
| Certification | M25/M30/M36 package cert | Adapters must certify later |
| Workspace / org scope | project_id, workspace_id, business_unit | RBAC + ownership |
| Trading Guardian | M48.1 boundary + platform TG | FINANCIAL_EXECUTION PROHIBITED |
| ApplicationHarness | M17.3 | **Different**: argv CLI tools, not multi-turn agent drivers |

## Canonical flow today (M48.1)

```text
Intent → Orchestrator.create_run → PLANNING → [AWAITING_APPROVAL] → QUEUED → RUNNING
      → AgentExecutor (gateway_llm / tools) → ExecutionGateway(ToolIntent)
      → RunStore events/checkpoints → terminal
```

## Composition point for AgentHarness

AgentHarness **replaces neither** Orchestrator nor AgentExecutor’s authority path.
It provides a **pluggable multi-turn driver** invoked from a future platform-owned
**HarnessSessionController** when a run task needs a coding/reasoning harness:

```text
Orchestrator task (capability code|review|…)
  → HarnessSessionController.start(bound to run_id, actor, scope, authority_class)
  → AgentHarness adapter session loop
  → tool_request_proposed events
  → platform normalizes → ToolIntent → ExecutionGateway
  → redacted result fed back as turn continuation
```

**Do not invent parallel:** second RunStore, second approval system, second credential
store, second risk ladder, or second kill switch.

### Naming disambiguation

| Name | Meaning in SaathiOS |
| --- | --- |
| **AgentHarness** (this ADR) | Multi-turn coding/reasoning **driver** interface |
| **ApplicationHarness** (M17.3) | Single-action structured CLI adapter for tools/media |
| **Sandbox harness** (M30) | Conformance sandbox for connectors |
| **agent_runtime** | Multi-agent orchestration authority |

---

# M385.2 — Responsibility boundary

## 3. Responsibility matrix

| Responsibility | AgentHarness adapter | HarnessSessionController (platform) | agent_runtime | ExecutionGateway | Approvals | Credentials | Trading Guardian | Provider governance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Session startup / close | Execute driver open/close | Owns handle, scope bind, audit | Binds run/task | — | — | — | — | — |
| Turn submission | Run model loop | Validates actor/scope/budget | Authority class | — | — | — | — | Model path policy |
| Event streaming | Emit raw driver signals | Normalize, sequence, redact, persist | Ledger | — | — | — | — | — |
| Harness-local state refs | Opaque driver state | Stores refs + integrity meta | Checkpoint links | — | — | — | — | — |
| Cancel handling | Cooperative stop | Durable cancel request; fail-closed | Kill switch | Abort in-flight tools | — | — | — | Abort model calls |
| Checkpoint export | Optional dump | Verify hash, owner, store | run_checkpoint | — | — | — | — | — |
| Capability declaration | Descriptive profile | Verify claims; degrade | Capability allowlist | — | — | — | — | Provider caps |
| Health / diagnostics | Report | Aggregate | Provider health | — | — | — | — | Health APIs |
| Authorization decisions | **Forbidden** | Enforce via contracts | contracts.py | Authorizer | — | — | — | — |
| Approval issuance | **Forbidden** | Surface approval_required | approval_request | ApprovalGate | **Own** | — | — | — |
| Credential storage | **Forbidden** | Never pass secrets to adapter | — | Lease at exec | — | **Own** | — | Keys via gov |
| Direct tool execution | **Forbidden** | Mediate proposals only | policy.check_tool | **Execute** | Gate | Lease | Block finance | — |
| Trading authority | **Forbidden** | Fail closed on finance ops | PROHIBITED caps | trade family | — | — | **Own** | — |
| Certification decisions | **Forbidden** | Read cert status | — | Package cert | — | — | — | Provider cert |
| Filesystem / network / deploy authority | **Forbidden** | — | — | Via tools only | — | — | — | — |

### Owned by AgentHarness (adapter)

1. Session startup inside driver
2. Turn submission inside driver
3. Output/event production (pre-normalization)
4. Harness-local state references
5. Cancellation **acknowledgment** (cooperative)
6. Checkpoint **export** (if capability claimed)
7. Termination reporting
8. Capability declaration (descriptive)
9. Health reporting

### Explicitly excluded

Authorization · approval issuance · credential storage · direct tool execution ·
direct provider-secret access · trading authority · deployment authority ·
filesystem authority · network authority · certification decisions · permission minting ·
audit/replay bypass · unrestricted shell/browser.

---

# M385.3 — Core interface design

## Design sketch (documentation only — not production code)

Typed sketch uses SaathiOS vocabulary. Names are **design targets**, not frozen APIs.

```text
# Conceptual protocol — Python-shaped; not implemented in M385

class AgentHarness(Protocol):
    def describe_capabilities(self) -> HarnessCapabilityProfile: ...
    def health(self) -> HarnessHealth: ...
    def diagnostics(self, session_id: str | None) -> HarnessDiagnostics: ...

    def start_session(self, req: HarnessSessionStartRequest) -> HarnessSessionHandle: ...
    def resume_session(self, req: HarnessSessionResumeRequest) -> HarnessSessionHandle: ...
    def submit_turn(self, req: HarnessTurnSubmitRequest) -> HarnessTurnHandle: ...
    def stream_events(self, session_id: str, after_seq: int = 0) -> Iterator[HarnessEvent]: ...
    # Alternative durable path: poll_events(session_id, after_seq) -> list[HarnessEvent]

    def request_cancel(self, session_id: str, reason: str) -> CancelAck: ...
    def create_checkpoint(self, session_id: str, label: str) -> CheckpointExport: ...
    def restore_checkpoint(self, session_id: str, checkpoint_id: str) -> HarnessSessionHandle: ...
    def close_session(self, session_id: str, reason: str) -> SessionCloseResult: ...
```

Platform **always** wraps the adapter. Callers never treat adapter output as authorized action.

## Operation specifications

### `describe_capabilities`

| Field | Spec |
| --- | --- |
| Purpose | Return descriptive capability profile + versions |
| Inputs | none (or adapter config id) |
| Outputs | `HarnessCapabilityProfile` |
| Preconditions | Adapter constructed |
| Transitions | none |
| Auth | Caller must be platform controller; profile is public metadata |
| Failures | Adapter unavailable → health degraded; profile empty is fail-closed for registration |
| Audit | `harness.capabilities_described` |
| Idempotency | Pure read |
| Timeout | Short (≤ 5s design target) |
| Cancel | N/A |

### `start_session`

| Field | Spec |
| --- | --- |
| Purpose | Create harness session bound to platform scope |
| Inputs | `session_id` (platform-minted), `run_id?`, `mission_id?`, `actor_id`, `organization_id?`, `workspace_id?`, `project_id?`, `authority_class`, `allowed_tool_names[]` (descriptive filter only), `budget`, `model_prefs` (non-secret), `correlation_id`, `deadline_at` |
| Outputs | `HarnessSessionHandle{session_id, state=READY\|FAILED, harness_id, capabilities}` |
| Preconditions | Controller validated `AgentRunRequest` / actor / scope; authority ≠ FINANCIAL_EXECUTION |
| Transitions | CREATED → INITIALIZING → READY \| FAILED |
| Auth | **Assumed already enforced by controller**; adapter must not re-decide allow |
| Failures | init error → FAILED; timeout → TIMED_OUT; cancel during init → CANCELLED |
| Audit | `harness.session_started` / `harness.session_failed` |
| Idempotency | Same `session_id` → return existing handle or conflict (no dual init) |
| Timeout | Bound by `deadline_at` and controller wall budget |
| Cancel | Cooperative; fail-closed if adapter cannot confirm stop within grace |

**Forbidden inputs:** API keys, tokens, raw credentials, approval minting rights.

### `resume_session`

| Field | Spec |
| --- | --- |
| Purpose | Resume READY/PAUSED session or from approved checkpoint |
| Inputs | `session_id`, optional `checkpoint_id`, `correlation_id` |
| Outputs | Handle in READY |
| Preconditions | Session not terminal; owner match; resume capability if claimed |
| Transitions | PAUSED → READY; FAILED/CANCELLED **forbidden** (no resurrection) |
| Auth | Owner/scope check in controller |
| Failures | TERMINAL_RESTART → reject; missing checkpoint → fail |
| Audit | `harness.session_resumed` |
| Idempotency | Safe re-call if already READY |
| Timeout / Cancel | Same as start |

### `submit_turn`

| Field | Spec |
| --- | --- |
| Purpose | Submit user/platform turn content; start model loop |
| Inputs | `session_id`, `turn_id` (platform-minted), `input` (text + attachment **refs** only), `correlation_id`, `causation_id` |
| Outputs | `HarnessTurnHandle{turn_id, state=RUNNING}` |
| Preconditions | state ∈ {READY, WAITING_TOOL after result injected by controller} |
| Transitions | READY → RUNNING; after tool result: WAITING_TOOL → RUNNING |
| Auth | Actor must own session |
| Failures | Invalid state, budget exceeded, cancel, timeout |
| Audit | `harness.turn_submitted` |
| Idempotency | Same `turn_id` → no double model start |
| Timeout | Turn wall clock from budget; then TIMED_OUT path |
| Cancel | request_cancel may target session (and thus active turn) |

Attachments are **content refs** resolved by platform (no arbitrary path traversal by harness).

### `stream_events` / durable poll

| Field | Spec |
| --- | --- |
| Purpose | Observe ordered, normalized events |
| Inputs | `session_id`, `after_seq` |
| Outputs | Iterator or page of `HarnessEvent` |
| Preconditions | Session exists; caller authorized |
| Auth | Owner or audited admin-read policy (existing SaathiOS admin rules) |
| Failures | Unknown session; redaction errors fail closed on sensitive fields |
| Audit | Optional `harness.events_read` for admin |
| Idempotency | Reads are idempotent |
| Ordering | Strictly increasing `sequence_number` per session |

### `request_cancel`

| Field | Spec |
| --- | --- |
| Purpose | Cooperative cancel of session/active turn |
| Inputs | `session_id`, `reason`, `correlation_id` |
| Outputs | `CancelAck{status: requested\|acknowledged\|already_terminal}` |
| Preconditions | Any non-CLOSED |
| Transitions | * → CANCELLING → CANCELLED (terminal) |
| Failures | If adapter does not stop within grace → platform marks CANCELLED and isolates driver process (**fail-closed**) |
| Audit | `harness.cancellation_requested`, `harness.cancellation_acknowledged` |
| Idempotency | Re-request safe |
| Timeout | Cancel grace (align M48.3 DEFAULT_CANCEL_GRACE) |

**Fail-closed rule:** After cancel requested, **no new tool proposals accepted**; in-flight
gateway ops receive cancel propagation; partial work remains observable in ledger.

### `create_checkpoint` / `restore_checkpoint`

| Field | Spec |
| --- | --- |
| Purpose | Optional durable harness-local snapshot |
| Inputs | session_id, label / checkpoint_id |
| Outputs | CheckpointExport with content hash |
| Preconditions | Capability `checkpoints`; session not CANCELLING |
| Forbidden | Restoring into different owner/scope; restoring terminal sessions as “success” without new session |
| Audit | `harness.checkpoint_created` / `restored` |
| Integrity | Platform verifies hash + session binding before restore |

### `close_session`

| Field | Spec |
| --- | --- |
| Purpose | Release driver resources after terminal or forced close |
| Inputs | session_id, reason |
| Outputs | SessionCloseResult |
| Transitions | terminal → CLOSED; READY → CANCELLED → CLOSED if forced |
| Audit | `harness.session_closed` |
| Idempotency | close on CLOSED is no-op success |

### `health` / `diagnostics`

| Field | Spec |
| --- | --- |
| Purpose | Liveness and safe diagnostic bundle (no secrets) |
| Failures | Unhealthy → controller must not start new sessions |
| Audit | On demand / periodic |

---

# M385.4 — Session state machine

## 4. State-transition table

Harness sessions use **HarnessSessionState**, distinct from `RunState` but mappable.

| State | Meaning |
| --- | --- |
| `CREATED` | Platform minted id; adapter not yet started |
| `INITIALIZING` | Adapter starting |
| `READY` | Accepts submit_turn |
| `RUNNING` | Turn active (model/driver work) |
| `WAITING_TOOL` | Proposal accepted by platform; awaiting gateway result |
| `WAITING_APPROVAL` | Platform blocked on human approval (adapter idle) |
| `PAUSING` | Pause requested |
| `PAUSED` | No new turns until resume |
| `CANCELLING` | Cancel in flight |
| `CANCELLED` | Terminal cancel |
| `COMPLETED` | Terminal success |
| `FAILED` | Terminal failure |
| `TIMED_OUT` | Terminal timeout |
| `CLOSED` | Resources released (post-terminal) |

### Valid transitions

| From | To |
| --- | --- |
| CREATED | INITIALIZING, CANCELLED, FAILED |
| INITIALIZING | READY, FAILED, TIMED_OUT, CANCELLED, CANCELLING |
| READY | RUNNING, PAUSING, CANCELLING, COMPLETED, FAILED, TIMED_OUT |
| RUNNING | WAITING_TOOL, WAITING_APPROVAL, READY, PAUSING, CANCELLING, COMPLETED, FAILED, TIMED_OUT |
| WAITING_TOOL | RUNNING, WAITING_APPROVAL, READY, CANCELLING, FAILED, TIMED_OUT, CANCELLED |
| WAITING_APPROVAL | RUNNING, READY, CANCELLING, CANCELLED, TIMED_OUT, FAILED |
| PAUSING | PAUSED, CANCELLING, FAILED |
| PAUSED | READY, CANCELLING, TIMED_OUT, CANCELLED |
| CANCELLING | CANCELLED, FAILED (if cancel path errors; still terminal) |
| CANCELLED, COMPLETED, FAILED, TIMED_OUT | CLOSED |
| CLOSED | ∅ |

### Forbidden transitions

- Any terminal → RUNNING / READY / INITIALIZING (**no resurrection**)
- CANCELLED → COMPLETED
- CLOSED → anything
- WAITING_APPROVAL → COMPLETED without platform approval resolution
- READY → WAITING_TOOL (must pass RUNNING and proposal path)

### Terminal states

`CANCELLED`, `COMPLETED`, `FAILED`, `TIMED_OUT` then optionally `CLOSED`.

### Recovery / restart / ownership

| Topic | Rule |
| --- | --- |
| Recovery | Controller may **resume** PAUSED or recreate **new** session from checkpoint; never flip FAILED/CANCELLED to RUNNING |
| Restart | New `session_id`; link `prior_session_id` in audit |
| Ownership transfer | **Forbidden** in v1 (no impersonation); future requires dual-control ADR |
| Stale session | Lease/heartbeat (align M48.3); stale → reconcile to TIMED_OUT or CANCELLED |
| Orphan detection | Session without live adapter process → mark FAILED/TIMED_OUT; no silent continue |
| Crash recovery | Durable events + optional checkpoint; in-flight tool ops reconcile via gateway before retry |

### Mapping to RunState (informative)

| HarnessSessionState | Typical RunState |
| --- | --- |
| INITIALIZING / READY / RUNNING | RUNNING |
| WAITING_APPROVAL | AWAITING_APPROVAL |
| WAITING_TOOL | RUNNING (tool_request open) |
| PAUSED | PAUSED |
| CANCELLED / COMPLETED / FAILED / TIMED_OUT | same-named run terminals |

---

# M385.5 — Event protocol

## 5. Event-envelope specification

```text
HarnessEvent
  event_id            # uuid
  session_id          # platform id
  turn_id             # optional
  run_id              # optional bind
  mission_id          # optional
  organization_id     # optional
  workspace_id        # optional
  project_id          # optional
  actor_id            # owner principal
  harness_id          # adapter id + version
  sequence_number     # uint64, monotonic per session
  event_type          # enum below
  timestamp           # UTC ISO-8601
  correlation_id      # ties to request
  causation_id        # prior event or turn
  payload_ref         # inline small or blob ref
  classification      # PUBLIC | INTERNAL | SENSITIVE | RESTRICTED
  redaction_state     # NONE | REDACTED | REDACTION_FAILED
  integrity           # { content_hash?, prev_seq_hash? }
```

### Event types

| event_type | Notes |
| --- | --- |
| `session_started` | |
| `session_ready` | |
| `text_delta` | Safe assistant text chunks |
| `reasoning_summary` | **Safe summary only** — never private chain-of-thought |
| `tool_request_proposed` | Proposal payload → mediation |
| `tool_request_accepted` | Platform accepted into gateway path |
| `tool_request_denied` | Policy/approval/auth denial |
| `tool_result_delivered` | Redacted result to adapter |
| `approval_required` | Human gate |
| `approval_resolved` | Approved/rejected/expired |
| `checkpoint_created` | |
| `resource_usage` | Tokens/calls/time reports |
| `warning` | |
| `error` | |
| `cancellation_requested` | |
| `cancellation_acknowledged` | |
| `session_completed` | |
| `session_failed` | |
| `session_timed_out` | |
| `session_closed` | |

### Privacy

- No private CoT in events or logs.
- `reasoning_summary` is optional, size-capped, classifier-safe.
- Secret-shaped fields rejected (align `contracts._SECRET_KEY_RE`).
- `REDACTION_FAILED` → drop payload, emit error, fail closed for sensitive classes.

---

# M385.6 — Tool request mediation

## 6. Tool mediation sequence

```text
┌────────────┐   propose    ┌─────────────────────────┐
│ AgentHarness│ ──────────► │ HarnessSessionController │
│  (driver)   │             │ (platform, untrusted in) │
└────────────┘             └───────────┬─────────────┘
                                       │ normalize + schema validate
                                       │ capability match (agent allowlist)
                                       │ policy.check_tool
                                       │ build immutable ToolIntent
                                       │   correlation_id, causation_id,
                                       │   idempotency_key, actor, bu
                                       ▼
                            ┌──────────────────────┐
                            │ Approval evaluation  │
                            │ (existing system)    │
                            └──────────┬───────────┘
                         deny│         │ allow / token
                             ▼         ▼
                      tool_request   ExecutionGateway.submit
                      _denied              │
                                           ▼
                                    tool_runtime /
                                    connectors / browser /
                                    application_harness
                                           │
                                           ▼
                                    sanitize + evidence
                                           │
                                           ▼
                            tool_result_delivered (redacted)
                                           │
                                           ▼
                                      AgentHarness continue
```

### Rules

| Topic | Rule |
| --- | --- |
| Normalization | Map driver tool name → SaathiOS tool id; unknown → deny |
| Capability matching | AgentDefinition.allowed/denied + authority_class |
| Schema validation | Fail closed on invalid params |
| Approval lookup | Existing approval_request / M35; harness cannot approve |
| Idempotency | ToolIntent.idempotency_key required; same key no double side effect |
| Retry | Transient only; non-idempotent external mutation never blind-retried (M48.1) |
| Denial | Emit `tool_request_denied`; adapter may continue or complete |
| Result redaction | Gateway ResultSanitizer before adapter sees data |
| Timeout | Gateway + turn deadline; partial result marked uncertain → reconcile |
| Cancel | If cancel requested, reject new proposals; cancel in-flight intents |
| Audit linkage | tool_request row + gateway Evidence + harness event seq |

**Harness must not call tools directly.** Any adapter that spawns shell/network outside
proposal path is **non-conformant** and must be rejected at certification.

---

# M385.7 — Capability model

## 7. Capability model

Capabilities are **descriptive**, never authoritative.

### Identifiers (v1 catalog)

| id | Kind | Meaning |
| --- | --- | --- |
| `session_lifecycle` | required | start/close states |
| `submit_turn` | required | |
| `event_stream` | required | ordered events |
| `cooperative_cancel` | required | |
| `tool_proposals` | required | |
| `health` | required | |
| `resource_usage_report` | required | |
| `checkpoints` | optional | |
| `resume_session` | optional | |
| `restore_checkpoint` | optional | implies checkpoints |
| `multimodal_input` | optional | images via platform refs |
| `reasoning_summary` | optional | safe summaries |
| `token_accounting` | optional | detailed tokens |
| `context_window_reporting` | optional | |
| `deterministic_replay_support` | optional | |
| `local_execution_support` | optional | **descriptive only** |
| `remote_provider_support` | optional | **descriptive only** |

### Versioning

```text
HarnessCapabilityProfile {
  harness_id: str
  harness_version: semver
  protocol_version: "1.0"
  capabilities: list[{ id, version, optional_notes }]
  required_platform_protocol: ">=1.0,<2.0"
}
```

### Negotiation

1. Adapter declares profile.
2. Controller intersects with **platform allowlist** and run authority.
3. Missing **required** platform needs → refuse start.
4. Optional missing → degraded mode (feature off).
5. **False claim** (claims checkpoints but create_checkpoint fails systematically) →
   cert failure; runtime marks adapter untrusted / quarantine.

**A declared capability never grants permission** to tools, network, secrets, or trading.

---

# M385.8 — Provider and harness separation

```text
┌──────────── Mission / Persona / Objective ────────────┐
│  (what the user wants; agent role; risk ceiling)      │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌──────────── agent_runtime Session/Run ────────────────┐
│  RunState, budget, lease, cancel, ledger              │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌──────────── AgentHarness (driver) ────────────────────┐
│  ClaudeCode | Codex | OpenCode | LocalModel | Fake    │
│  Owns: model loop, text, tool PROPOSALS only          │
└───────┬───────────────────────────┬───────────────────┘
        │                           │
        ▼                           ▼
┌───────────────┐           ┌──────────────────────────┐
│ Model Provider│           │ Tool proposal bus        │
│ (Anthropic,   │           │ → ToolIntent             │
│  OpenAI,      │           │ → ExecutionGateway       │
│  Ollama, …)   │           └──────────┬───────────────┘
│ via ModelRouter│                     ▼
│ & provider gov │           ┌──────────────────────────┐
└───────────────┘           │ Tool runtime / sandbox / │
        ▲                   │ browser / connectors     │
        │                   │ (separate contracts)     │
   model weights            └──────────────────────────┘
   ≠ harness product
```

| Concept | Is | Is not |
| --- | --- | --- |
| Harness | Driver loop product (e.g. “Claude Code” UX/agent loop) | Not the model weights; not the API key owner |
| Model provider | API/local inference backend | Not tool executor |
| Model | Specific model id | Not permission set |
| Tool runtime | Executes allowlisted tools via gateway | Not a chat model |
| Sandbox | Isolation substrate for tools | Not AgentHarness itself |
| Agent persona | Role, memory scopes, risk ceiling | Not a provider |
| Mission | Business objective / project work | Not a session driver |
| Session | Bound harness conversation instance | Not org-wide authority |

---

# M385.9 — Security model

## 8. Security threat model

| Threat | Mitigation | Residual risk |
| --- | --- | --- |
| Prompt injection | Untrusted content treated as data; tool proposals re-validated; no instruction-as-auth | Model may still attempt malicious proposals |
| Tool-request spoofing | Platform rebuilds ToolIntent; adapter names mapped; signatures on events optional later | Compromised adapter process |
| Forged events | Only controller persists canonical events; adapter stream is untrusted input | Memory-only forgeries if controller bug |
| Replay attacks | sequence_number + idempotency_key + turn_id uniqueness | Clock skew low impact |
| Session hijacking | Owner actor_id bind; no ownership transfer v1 | Stolen operator credentials |
| Confused deputy | Gateway authorizer uses **user** actor, not harness id, for side effects | Mis-set actor_id in controller |
| Capability overclaiming | Conformance + runtime verify; quarantine | Delayed detection |
| Credential leakage | No secrets in start_session; redaction; secret key rejection | Model stdout exfil of previously leaked data |
| Output command smuggling | Tools only via gateway; no shell from text | Human copy-paste risk |
| Path traversal | Attachment refs only; gateway path policy | Adapter local FS if non-conformant binary |
| Unauthorized workspace access | workspace_id/project_id RBAC at controller | Cross-scope memory bugs |
| Cross-session leakage | Session isolation; no shared mutable driver global | Adapter global cache bugs |
| Cancellation failure | Grace then isolate/kill driver; fail-closed no new tools | Stuck foreign child process |
| Checkpoint tampering | content_hash + owner bind | Weak hash storage |
| Event-order manipulation | Controller assigns seq | Adapter reordering ignored |
| Unbounded retries | max_retries contract; non-idempotent deny | Misclassified transient |
| Resource exhaustion | Budgets (M385.10); concurrent session caps | Kernel-level fork bomb if non-conformant |
| Malicious adapter | Certification, sandbox process, allowlist tools, no secrets | Supply-chain of adapter binary |

### Residual risk summary

AgentHarness **reduces** dual-path risk but cannot make untrusted model output safe.
Security depends on gateway, approvals, redaction, and adapter process isolation.
Residual risk is **accepted with limitations** for design; live adapters need red-team
extension (M15.2 style) before production cert.

---

# M385.10 — Resource governance

Harness **reports**; SaathiOS **enforces**.

| Resource | Report | Enforce |
| --- | --- | --- |
| Tokens / model calls | `resource_usage` events | Budget on session/run; stop turns |
| Wall-clock | timestamps | deadline_at → TIMED_OUT |
| CPU / memory / disk | optional diagnostics | OS cgroup / process limits (future) |
| Network | not directly | Only via gateway tools |
| Tool calls | count events | max_tool_calls; deny beyond |
| Concurrent sessions | health | controller cap per actor/workspace |
| Retries | adapter internal | max_retries; contract fail |
| Checkpoints | count/size | max checkpoints; max payload size |
| Output size | text_delta sizes | cap; truncate with warning |

### On limit reached

1. Emit `warning` + `resource_usage`.
2. Reject new `submit_turn` / tool proposals.
3. Transition to `TIMED_OUT` or `FAILED` with explicit code (`BUDGET_EXCEEDED`).
4. Cancel in-flight tools fail-closed where non-idempotent uncertainty requires review.
5. Preserve ledger; no silent success.

---

# M385.11 — Adapter conformance

## 9. Adapter conformance checklist

Future suite (not implemented in M385) must cover:

| Suite | Required tests |
| --- | --- |
| Lifecycle | start → ready → turn → complete → close; illegal transitions raise |
| Cancellation | request during RUNNING and WAITING_TOOL; no tools after cancel; idempotent re-request |
| Event ordering | monotonic seq; no gaps on durable poll; correlation/causation present |
| Tool mediation | proposal never executes side effect without gateway mock; deny path |
| Timeout | deadline forces TIMED_OUT; no success |
| Checkpoint integrity | hash mismatch refuse restore; cross-session restore fail |
| Scope isolation | session A cannot read B events |
| Failure recovery | FAILED not resurrected; new session from checkpoint only |
| Audit completeness | start/turn/tool/cancel/close events present |
| Capability accuracy | claimed optional features work; unclaimed return capability error |
| Resource reporting | usage events; budget exceeded path |
| Secret non-disclosure | start/turn with secret-like fields rejected; results redacted |
| Authority freeze | FINANCIAL_EXECUTION / trade tools never accepted |
| No direct I/O | suite fails adapter if it opens network/fs outside test doubles |

### Named future adapters (not built)

- `FakeInMemoryHarness` — conformance gold
- `LocalModelHarness` — local inference, tool proposals limited
- `ClaudeCodeHarness` / `CodexHarness` / `OpenCodeHarness` — **blocked** until dedicated security ADR + process isolation + cert

---

# M385.12 — Migration and rollout plan

## 10. Future phased implementation roadmap

| Phase | Milestone theme | Deliverable | Gate to next |
| --- | --- | --- | --- |
| 0 | M385 (this) | ADR + design | Human review |
| 1 | Contract types only | Internal types/protocol module (no adapters) | Design freeze; tests for types/state matrix only |
| 2 | FakeInMemoryHarness | In-memory driver | Conformance suite green |
| 3 | Conformance CI | Automated checklist | Required for any real adapter PR |
| 4 | LocalModelHarness | Read-only / advisory local turns | Local provider cert; no external mutation tools |
| 5 | Bounded coding adapter | Allowlisted local tools via gateway | Security review + red-team probes |
| 6 | Operator validation | Manual ops runbook | Evidence package |
| 7 | Certification | Production cert flags still default off | Explicit owner approval |
| 8 | Optional broader rollout | More adapters | Per-adapter security ADR |

**Safest first adapter path:** Fake → LocalModel (read-only) → bounded coding.
**Not first:** Claude Code / Codex / OpenCode.

---

# 11. Risk register

| ID | Risk | L | I | Mitigation |
| --- | --- | --- | --- | --- |
| H1 | Adapter becomes shadow ExecutionGateway | M | C | Mediation rule; conformance; code review |
| H2 | Confusion with ApplicationHarness | M | M | Naming + docs; separate packages later |
| H3 | Commercial CLI credential sprawl | H | H | Block until security ADR; no secrets in session |
| H4 | Cancel not honored by foreign process | M | H | Grace + isolate; fail-closed proposals |
| H5 | Event log becomes secret sink | M | H | Redaction; classification; secret field reject |
| H6 | Scope bleed across sessions | L | H | Owner bind; isolation tests |
| H7 | Premature public SDK | M | M | Internal-only D5 |
| H8 | Implementation starts without gates | M | H | Roadmap gates; this ADR |
| H9 | TG weakened via “coding” tools | L | C | PROHIBITED finance; tool denylist |
| H10 | Design drift from M48 contracts | M | M | Traceability map; reuse RunState mapping |

---

# 12. Traceability map (M377–M384 → M385)

| M377–M384 finding | M385 decision |
| --- | --- |
| Adapt harness session interface | D1–D3; full operation specs |
| Harness not execution authority | D2–D4; tool mediation M385.6 |
| Multi-harness capability profiles | M385.7 descriptive capabilities |
| Reject QM core / import | Integrity; no QM code; no attribution change needed |
| Reject dangerous modes | No unrestricted capability; fail-closed budgets |
| Reject browser/shell outside gates | Sandbox separate; tools via gateway only |
| Reject plaintext agent credentials | Forbidden inputs; credential column N/A |
| Preserve ExecutionGateway / TG | Explicit exclusions; TG freeze |
| First future M385 design | This document |
| Optional checkpoints | D7 optional |
| Org floor policies | Deferred to M386 (not in harness interface) |
| Skill promotion | Deferred to M387 |

---

## ADR decision summary (answers)

| Question | Answer |
| --- | --- |
| Become SaathiOS abstraction? | **Yes** (internal design contract) |
| Where it belongs | Under agent_runtime via controller; beside not above gateway |
| May control | Driver loop, events, proposals, health, optional checkpoints |
| Must never control | AuthZ, approvals, secrets, tools exec, TG, cert, deploy, FS/net |
| Internal or public? | **Internal** first |
| Sync + streaming? | **Both required** |
| Checkpoints? | **Optional** capability |
| Sandbox in contract? | **No — separate** |
| Minimum capabilities | lifecycle, turn, events, cancel, tool_proposals, health, resource report |
| First adapter to evaluate | **FakeInMemoryHarness**, then **LocalModelHarness** |

---

## Explicit non-actions (M385)

- No M386/M387 implementation
- No adapters, tests, runtime code, migrations
- No provider connections
- No credentials, CI, deploy, dependency changes
- No QM source import
- No weakening of ExecutionGateway, Approval, RBAC, certification, provider governance, or Trading Guardian

---

## Recommended next milestone

**Not auto-started.** After human review of this ADR:

- Prefer **M386** (scope/policy floors) or a gated **M389 types + Fake harness** only with explicit authorization.
- Do **not** jump to Claude Code/Codex/OpenCode adapters.
