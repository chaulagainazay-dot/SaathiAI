# FM-C2 — AgentSessionAdapter ↔ AgentHarness Reconciliation

| Field | Value |
| --- | --- |
| **Status** | DESIGN COMPLETE — documentation only |
| **Date** | 2026-08-06 |
| **Verdict** | `AGENT_SESSION_HARNESS_RELATIONSHIP_APPROVED_WITH_LIMITATIONS` |
| **ADR** | [`docs/adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md`](../adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md) |
| **Baseline SHA** | `f79726d5746ecd485210dee6af12a3ed33a9f01e` |
| **Branch inspected** | `docs/fm-c1-architecture-baseline-freeze` |
| **Selected alternative** | **F — Controller composition + plane separation** |

---

## Integrity statement

This milestone changes **documentation only**. It does **not** implement AgentHarness, modify AgentSessionAdapter, create FakeInMemoryHarness, connect providers/credentials, or alter ExecutionGateway / Approval / RBAC / Trading Guardian / scheduler behavior.

Source claims were verified against the tree at the baseline SHA (working tree may match committed docs branch).

---

# FM-C2.1 — Current source discovery: AgentSessionAdapter

## Inventory

| Item | Path / evidence |
| --- | --- |
| ABC | `saathi/engineering/adapters/base.py` — `class AgentSessionAdapter(ABC)` |
| Launch DTO | `LaunchRequest` (prompt, working_directory, session_id, timeout_sec, env_allowlist, metadata) |
| Result DTO | `saathi/engineering/models.py` — `AgentSessionResult`, `SessionStatus`, `SessionPhase` |
| Mock | `saathi/engineering/adapters/mock.py` — `MockAgentAdapter` |
| Claude Code | `saathi/engineering/adapters/claude_code.py` — `ClaudeCodeAdapter` |
| Registry | `saathi/engineering/adapters/__init__.py` — `ADAPTERS`, `get_adapter` |
| Primary caller | `saathi/engineering/orchestrator.py` — `EngineeringOrchestrator` |
| Pilot | `saathi/engineering/pilot.py` |
| Session persistence | `saathi/engineering/store.py`, `session_ledger.py` |
| Recovery | `saathi/engineering/recovery.py` |
| Package claim | `saathi/engineering/__init__.py`: does **not** replace Mission Engine, EG, Approval, Run Ledger, TG |
| Tests | `tests/test_m20_0_engineering_orchestrator.py` (adapters); M20.4/M20.5/M20.9 engineering suites |
| Production callers outside engineering | Control Center facet only (status aggregation); **not** agent_runtime |

## Interface (actual)

```text
AgentSessionAdapter (ABC)
  start(LaunchRequest, *, allowed_root: str) -> AgentSessionResult
  poll(session_id: str) -> AgentSessionResult
  request_stop(session_id: str, *, force: bool = False) -> AgentSessionResult
  list_active() -> list[str]
  validate_working_directory(path, allowed_root) -> Path
  _redact / _tail helpers
```

**Classification:** abstract base class + process/session facade for **engineering**. Not a Protocol typing.Protocol; not a provider SDK wrapper alone; not an ExecutionGateway; **partial process wrapper** (`ClaudeCodeAdapter` uses `subprocess.Popen`).

## Lifecycle methods

| Method | Behavior |
| --- | --- |
| start | Validates cwd under allowed_root; starts process or mock; returns RUNNING/COMPLETED/CRASHED |
| poll | Harvests status; timeout → TIMED_OUT; detects usage-limit strings |
| request_stop | SIGTERM/SIGKILL process group (claude) or mock STOPPED |

## What it does **not** have

- `submit_turn`, `stream_events`, `describe_capabilities`, checkpoint export API on the adapter
- Tool proposal channel
- ToolIntent construction
- ExecutionGateway calls
- Credential lease APIs
- Platform RBAC / tenancy bind on the adapter itself

## Constructor / dependencies

| Adapter | Dependencies |
| --- | --- |
| Base | max_output_chars; in-memory `_sessions` dict |
| Mock | behavior string; no process |
| ClaudeCode | binary allowlist `claude` only; optional dry_run; subprocess; minimal child env |

## Process ownership

- ClaudeCode: adapter owns `Popen` handle in `_sessions[sid]["proc"]`; `start_new_session=True`; stop uses process group kill.
- Persistence of session **metadata** is EngineeringStore / SessionLedger — not agent_runtime RunStore.

## Access surfaces (security-relevant)

| Surface | AgentSessionAdapter behavior |
| --- | --- |
| Tool registry | **None** |
| Filesystem | Working directory confinement to `allowed_root`; **CLI may mutate files inside root unobserved** |
| Browser | Not mediated |
| Network | Child inherits only stripped env; CLI may still open network if binary allows |
| Credentials | No API keys in LaunchRequest by design; child env strips most secrets; **ambient user CLI auth may still exist on host** |
| Shell | No `shell=True`; fixed argv |

## Error / retry / cancel

| Concern | Owner |
| --- | --- |
| Adapter errors | `AdapterLaunchError`, status FAILED/CRASHED/TIMED_OUT |
| Retry | `RetryController` in EngineeringOrchestrator (not adapter) |
| Stop policy | `StopPolicy` + orchestrator |
| Cancel | `request_stop` only — not cooperative token into ToolIntent |

## Maturity / certification

| Item | Status |
| --- | --- |
| Mock path | Deterministic-tested (M20.0 suite) |
| Claude dry_run | Tested without binary |
| Live Claude write sessions | Optional / approval-gated in orchestrator; **not** platform-certified multi-agent path |
| Package | Engineering disabled by default (`settings`) |

## Is it a hidden control plane?

**No as designed** (docs forbid replacing EG / Mission / Approval). **Risk if expanded** as platform multi-agent entry without ToolIntent — freeze FZ-02 exists to prevent that.

---

# FM-C2.2 — AgentHarness design reconstruction (M385)

## Intended responsibilities (adapter)

1. Session startup / close inside driver
2. Turn submission
3. Pre-normalization event emission
4. Opaque harness-local state refs
5. Cooperative cancel acknowledgment
6. Optional checkpoint export
7. Termination reporting
8. Descriptive capability declaration
9. Health / resource reporting
10. Tool **proposal** emission (not execution)

## Explicit exclusions

Authentication · authorization · approval issuance · credential storage · direct tool execution · FS/browser/network/deploy authority · certification decisions · permission minting · trading · audit bypass · unrestricted shell.

## Core interface (design sketch, not code)

```text
describe_capabilities / health / diagnostics
start_session / resume_session / submit_turn
stream_events | poll_events
request_cancel / create_checkpoint / restore_checkpoint / close_session
```

## Platform composition (M385)

```text
agent_runtime task
  → HarnessSessionController
  → AgentHarness adapter
  → tool_request_proposed
  → ToolIntent → ExecutionGateway
  → redacted result → continue turn
```

**Status:** DESIGN_ONLY — no Python types in `saathi/`.

---

# FM-C2.3 — Responsibility comparison matrix

| Responsibility | AgentSessionAdapter (current) | AgentHarness (intended) | Overlap | Intended owner | Future change | Security significance |
| --- | --- | --- | --- | --- | --- | --- |
| Session creation | start() | start_session() | partial | Plane controller + driver | Map names in docs | Med |
| Session ownership | Eng store + adapter mem | Controller + Run bind | complementary | Controller | Keep separate stores | High |
| Turn submission | N/A (one-shot process) | submit_turn | distinct | AgentHarness | Eng may stay one-shot | Med |
| Process launch | ClaudeCode yes | Optional behind adapter | partial | Driver only | Cert process drivers | **High** |
| Process supervision | poll/stop | health + cancel ack | partial | Driver + controller | — | High |
| Event production | stdout tails via poll | ordered events | partial | Driver raw; controller normalize | Platform events | Med |
| Event normalization | Orchestrator ad hoc | Controller | complementary | **Controller** | Implement later | Med |
| Lifecycle state | SessionStatus | HarnessSessionState | naming-only + partial | Projection | Map tables | Med |
| Run-state mapping | None to RunState | Map to RunState | distinct | agent_runtime | Required for platform | High |
| Tool proposal | **None** | tool_request_proposed | distinct | Driver propose | Eng must not skip | **High** |
| Tool execution | **Indirect via CLI** risk | Forbidden in adapter | **dangerous duplication risk** | **ExecutionGateway only** | Cert / block CLI expansion | **Critical** |
| Approval waiting | Orchestrator for real adapters | Controller surfaces | complementary | Approval systems | — | High |
| Cancel request | request_stop | request_cancel | partial | Controller → driver | Align names later | High |
| Cancel ack | implicit via status | explicit CancelAck | partial | Driver | — | Med |
| Forced termination | force=True kill | fail-closed grace then stop | partial | Controller policy | — | High |
| Checkpoint create | Eng Checkpoint model separate | optional export | complementary | Plane-specific | No merge | Med |
| Checkpoint restore | SessionRecovery eng | optional | complementary | Plane-specific | — | Med |
| Provider selection | adapter name string | model_prefs non-secret | partial | Provider gov / settings | — | Med |
| Model selection | CLI-internal | via inference policy on platform | distinct | Inference | — | Med |
| Credential handling | strip env; ambient CLI risk | forbidden secrets | complementary intent | Credentials package | Block ambient | **Critical** |
| Resource accounting | timeout only | resource_usage_report | partial | Controller aggregate | — | Med |
| Health reporting | poll status | health() | partial | Driver | — | Low |
| Diagnostics | stderr tail | diagnostics() | partial | Driver | — | Low |
| Audit events | eng store / evidence | harness events + EG | complementary | Plane audit + EG | Correlation_id | High |
| Replay | eng recovery | checkpoint/tape | complementary | Plane | — | Med |
| Evidence | eng IntegrityEvidenceStore | EG Evidence + run | complementary | Distinct | — | Med |
| Sandbox binding | allowed_root only | requires_isolated_execution descriptive | partial | EG families | — | High |
| Scope enforcement | allowed_root + settings | actor/org/workspace in start req | complementary | Platform RBAC / eng settings | — | High |
| Concurrency | max_active_sessions eng | budget/controller | complementary | Controllers | — | Med |
| Retry | RetryController eng | bounded by contracts | complementary | Controllers | — | Med |
| Timeout | session_timeout + poll | deadline_at | partial | Controllers | — | Med |
| Crash recovery | SessionRecovery eng | reconcile + new session | complementary | Controllers | — | High |

---

# FM-C2.4 — Alternatives analysis

| Alt | Clarity | Duplication | Migration | Authority safety | Testability | Provider neutral | Eng coupling | Future adapters | Cancel/events | Shadow plane risk | Risk | **Outcome** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A Independent forever | Low long-term | High | Low | Med | Med | Med | Low | Med | Divergent | **High** | Med | Reject long-term |
| B AH wraps ASA | Med | Med | High | **Low** (launders CLI) | Med | Low | High | Med | Confusing | High | High | Reject v1 |
| C ASA implements AH | Med | Low surface | High force-fit | Low | Med | Low | High | Low | Poor fit | High | High | Reject v1 |
| D Extend ASA, reject AH | Med | Low types | Med | Low for tools | Med | Low | High | Poor tool model | Eng-centric | High | High | Reject |
| E Shared protocol now | High aspirational | Low later | Med | Med | High later | High | Med | High | Good later | Med | Med | **Defer** |
| **F Controller + planes** | **High** | Controlled | Low now | **High** | High (fake first) | High platform | Low (eng stays) | High | Clear owners | **Low** if freezes | Low | **Accept** |

### Selected: **F**

Plane-labeled coexistence; platform multi-turn uses AgentHarness + HarnessSessionController; engineering keeps AgentSessionAdapter + EngineeringOrchestrator; neither is a second ExecutionGateway.

---

# FM-C2.5 — Canonical contract boundary (platform)

| Field | Decision |
| --- | --- |
| Name | **AgentHarness** |
| Owning package (future) | `saathi.agent_runtime` (protocol/types); controller may be `saathi.platform` or agent_runtime module |
| Visibility | **Internal** (M385 D5) |
| Shape | Protocol / ABC **design**; not implemented |
| Sync vs async | Sync command API + ordered event stream/poll (M385 D6) |
| Lifecycle | start/resume/submit/close + cancel |
| Health / capabilities / resources | Required profile methods |
| Optional | checkpoints, resume, multimodal, reasoning summary (safe) |
| Errors | Fail-closed; map to public codes later |
| Versioning | Capability profile + adapter version strings (design) |

**Engineering AgentSessionAdapter is not this contract.**

---

# FM-C2.6 — Controller ownership

## Platform: HarnessSessionController (**required** for AgentHarness path)

| Owns | Does not own |
| --- | --- |
| session↔run_id bind | Authorization policy definition (uses contracts) |
| lifecycle validation | Approval decide authority |
| event sequencing / normalize / redact / persist | Tool execution |
| **ToolIntent construction** from proposals | Credential storage |
| approval wait surfacing | Trading veto |
| cancel propagation to driver + EG | Certification issuance |
| timeout / budget checks (orchestration) | Second gateway |
| adapter quarantine (reject bad adapters) | — |
| checkpoint integrity verify | — |

## Engineering: EngineeringOrchestrator (**existing**)

| Owns | Does not own |
| --- | --- |
| eng session store, stop policy, pilot flow | M10 RunState authority |
| adapter selection among allowed list | Platform multi-agent public API |
| eng approval binding for real adapters | ToolIntent for CLI internals |

**No new general Orchestrator type authorized** (FZ-03).

---

# FM-C2.7 — State model reconciliation

| Layer | Machine | Authoritative? |
| --- | --- | --- |
| Multi-agent run | `agent_runtime.models.RunState` | **Yes** for platform multi-agent |
| Platform execution | PlatformExecutionState | Yes for platform tool executions |
| AgentHarness session | HarnessSessionState (design) | **Projection / local** — maps to RunState |
| Engineering session | `SessionStatus` + SessionPhase | **Yes within engineering plane only** |
| Process | OS process state | Local to process drivers |
| Provider session | inference/provider sessions | Separate |

| Question | Decision |
| --- | --- |
| Terminal outcome for multi-agent | **RunState** terminal |
| Adapter session outlive run? | Prefer no; controller closes session with run |
| Resume run with new session? | Allowed only via controller rules + new bind |
| Reuse failed/cancelled session? | **No** as success path |
| Cancel mapping | Run cancel → controller → driver cancel/stop |
| Timeout mapping | Run/controller deadline dominates |
| Crash mapping | Failed/partial run + reconcile; new session if retry |

**Do not introduce another authoritative run state.**

---

# FM-C2.8 — Event model reconciliation

| Concern | Platform (AgentHarness path) | Engineering (AgentSessionAdapter) |
| --- | --- | --- |
| Canonical owner | Controller-normalized events → RunStore ledger | Orchestrator + session ledger |
| IDs | session_id, run_id, correlation_id, seq | session_id, task_id eng |
| Ordering | Monotonic seq per session | Poll-time ordered |
| Tool proposals | First-class events | **Absent** |
| Approval events | Platform approval plane | Eng approval records |
| Cancel events | Durable cancel + ack | stop status |
| Private CoT | **Forbidden** in events | stdout redacted tails only |
| Replay | Run checkpoints / evidence | eng recovery |

---

# FM-C2.9 — Tool mediation boundary

## Only permitted platform flow

```text
AgentHarness adapter
  → tool_request_proposed (normalized)
  → HarnessSessionController
  → ToolIntent (immutable)
  → policy / approval / RBAC
  → ExecutionGateway.submit / execute_registered_tool
  → ToolExecutionService / family handler
  → redacted result event
  → submit_turn continuation
```

## AgentSessionAdapter vs this model

| Question | Finding |
| --- | --- |
| Constructs ToolIntent? | **No** |
| Calls ExecutionGateway? | **No** |
| Can CLI mutate FS? | **Yes (risk)** inside allowed_root |
| Unobserved shell/network? | Possible via `claude` binary capabilities |
| FM-C2 authorization of that pattern for platform? | **No — prohibited as platform pattern** |
| Engineering pilot? | Mock preferred; real CLI expansion **blocked** (FZ-02/07) |
| Direct tool execution authorized by FM-C2? | **No** |

### Sequence diagram (platform target)

```text
┌─────────────┐   propose    ┌──────────────────────┐   ToolIntent   ┌──────────────────┐
│ AgentHarness│ ───────────► │ HarnessSessionCtrl   │ ─────────────► │ ExecutionGateway │
│  (untrusted)│ ◄─────────── │ (trusted platform)   │ ◄───────────── │                  │
└─────────────┘   redacted   └──────────────────────┘   result       └──────────────────┘
                                     │
                                     ▼
                              RunStore events / Evidence
```

---

# FM-C2.10 — Security threat model

| Threat | Affects | Mitigation | Residual | Future cert |
| --- | --- | --- | --- | --- |
| Dual control planes | A, B, C | F + freezes; EG sole side effects | Eng CLI residual | Platform cert before elevating eng |
| Adapter self-execution | CLI adapters | ToolIntent-only for platform; FZ-07 | CLI host ambient | Process isolation cert |
| Tool bypass | ClaudeCode | Block expansion; document risk | Existing binary | Sandbox + mediation |
| Credential leakage | child env / host CLI login | Strip env; forbid secrets in requests | Host keychain/CLI login | Lease-only platform |
| Ambient CLI credentials | ClaudeCode | FZ-08; block commercial expand | Host-dependent | — |
| Forged events | future harness | Controller is sole normalizer | None until impl | Conformance |
| Event reordering | future | Monotonic seq | — | Tests |
| Session hijacking | both | Bind actor/scope; no ownership transfer v1 | — | Authz tests |
| ID confusion | both | Typed IDs run vs session | Multi-store | Correlation docs |
| Confused deputy | controller | No adapter-granted permissions | — | — |
| Cancel failure | process drivers | force kill + run CANCELLED | Remote work (RR-02) | Cancel contracts |
| Orphan processes | ClaudeCode | killpg; monitor | Crash mid-kill | Ops |
| Checkpoint tampering | future | Hash + owner verify | — | — |
| Cross-workspace leak | paths | allowed_root / tenancy | Symlink residual | Path tests |
| Provider coupling | ClaudeCode | name allowlist | Binary behavior | — |
| Command smuggling | stdout | Redact; never exec stdout | — | — |
| Unbounded spawn | eng max sessions | settings max_active | Misconfig | — |
| Resource exhaustion | timeouts | timeout + limits | — | — |
| Malicious adapter | any | Quarantine; cert; internal-only | — | Package cert |
| Commercial CLI hidden SE | Claude/Codex/… | **FZ-07 blocked** | Mock-only safe path | Full threat ADR |
| Direct FS/browser/net | CLI | Platform path via EG tools only | Eng CLI | — |

---

# FM-C2.11 — Migration and compatibility

| Item | Plan |
| --- | --- |
| Current callers | EngineeringOrchestrator, pilot, CLI, tests; CC facet status |
| Compatibility | **No breaking change** in FM-C2 (no code) |
| Deprecation | None immediate; eng adapters not deprecated |
| Versioning | Future AgentHarness capability profile independent of eng adapter names |
| Transition | Eng plane continues; platform harness path additive |
| Tests | Existing M20 tests remain authority for eng |
| Rollback | Docs-only ADR revert |
| Feature flags | Eng orchestrator already disable-by-default |
| Data migration | None |
| Source renames | **Not required** now |
| Historical names | Keep `AgentSessionAdapter` name in eng |

---

# FM-C2.12 — First implementation gate (FM-I1)

| Field | Spec |
| --- | --- |
| Name | **FM-I1 — AgentHarness types + FakeInMemoryHarness + controller test double** |
| Entry | Owner authorization after this ADR; explicit FZ-01 partial unfreeze for **fake only** |
| Deliverables | Design-aligned types; FakeInMemoryHarness; HarnessSessionController skeleton; conformance tests |
| Forbidden | Claude Code, Codex, OpenCode, Pi, Ollama, remote models, credentials, browser, shell, FS mutation tools, network, production missions, trading, new eng commercial adapters |
| Exit | Lifecycle + cancel + proposal-not-execute tests green; no production_certified claim |
| Rollback | Delete package; freezes restore |

**FM-I1 is not started by FM-C2.**

---

# Traceability

| Source | Link |
| --- | --- |
| M385 | ADR-AGENT-HARNESS-INTERFACE; M385 design |
| M386–M393 | Consolidation ADR; review dualism |
| FM-C1 | Freezes FZ-01/02; CX-05; terminology |
| CX-05 | Closed → compose via controller; separate planes |
| Source modules | `saathi/engineering/adapters/*`, `orchestrator.py`, `agent_runtime/*`, `execution/*`, `tool_runtime/*` |
| Tests | `tests/test_m20_0_engineering_orchestrator.py` (+ M20.4/5/9 eng) |

---

# Explicit non-actions

No contract types · no AgentHarness · no AgentSessionAdapter edits · no FakeInMemoryHarness · no commercial/local runtime integration · no EG/approval/RBAC/credential/provider/scheduler/TG changes.

---

**STOP after FM-C2 design documentation.**
