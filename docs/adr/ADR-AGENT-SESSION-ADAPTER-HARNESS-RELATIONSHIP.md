# ADR: AgentSessionAdapter ↔ AgentHarness Relationship (FM-C2)

| Field | Value |
| --- | --- |
| **ID** | ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP |
| **Date** | 2026-08-06 |
| **Status** | **ACCEPTED_DESIGN_ONLY** |
| **Milestone** | FM-C2 |
| **Baseline SHA** | `f79726d5746ecd485210dee6af12a3ed33a9f01e` (`docs/fm-c1-architecture-baseline-freeze`) |
| **Full design** | [`docs/architecture/FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md`](../architecture/FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md) |
| **Parents** | ADR-AGENT-HARNESS-INTERFACE · ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION · FM-C1 freezes |
| **Implementation status** | Design accepted; **FM-I1** (separately authorized) landed internal FakeInMemoryHarness + controller proof only — not production |
| **Authority impact** | Clarifies dual-plane relationship; does **not** weaken ExecutionGateway, Approval, RBAC, credentials, or Trading Guardian |
| **Supersedes** | Ambiguous “two harnesses” reading of CX-05; informal plans that would elevate engineering adapters to platform control plane |
| **Amends** | ADR-AGENT-HARNESS-INTERFACE (placement confirmed; relationship to engineering adapters decided); freezes FZ-01 / FZ-02 (prerequisites updated, freezes **retained**) |
| **Superseded by** | None |

---

## Context

M385 accepted an internal **AgentHarness** design contract (unimplemented) for multi-turn coding/reasoning drivers under a future platform controller, with tools only via ToolIntent → ExecutionGateway.

Separately, M20 engineering implemented **`AgentSessionAdapter`** (`start` / `poll` / `request_stop`) with `MockAgentAdapter` and `ClaudeCodeAdapter`, called by `EngineeringOrchestrator`. That path launches a process and polls stdout; it is **not** the M48 multi-agent runtime and is **not** mediated as ToolIntent proposals.

FM-C1 registered **CX-05** (partial duplication / dual design risk) and freezes **FZ-01** (AgentHarness implementation) and **FZ-02** (new AgentSessionAdapter variants) until this relationship ADR.

### Primary decision question

**What is the correct SaathiOS-native relationship between existing `AgentSessionAdapter` and proposed `AgentHarness`?**

---

## Decision

### Primary selection: **ALTERNATIVE F — Controller composition (with plane separation)**

| Decision | Choice |
| --- | --- |
| **Canonical platform multi-turn driver contract** | **AgentHarness** (design remains accepted; still unimplemented) |
| **Canonical engineering process-session adapter** | **AgentSessionAdapter** (implemented; **engineering-scoped only**) |
| **Relationship** | **Neither wraps nor implements the other today.** Both are **untrusted drivers** in different planes, composed only through **plane-owned controllers** — never as peer control planes. |
| **Platform controller** | Future **`HarnessSessionController`** (name retained from M385) owns platform run↔session bind, event normalize, ToolIntent construction, cancel propagation |
| **Engineering controller** | Existing **`EngineeringOrchestrator`** retains engineering session supervision; must **not** be treated as platform multi-agent authority or second ExecutionGateway |
| **Shared lower-level protocol** | **Not required in v1.** Optional later only after FakeInMemoryHarness + controller exist |
| **Rename** | No production renames in this milestone. Docs must always qualify **engineering AgentSessionAdapter** vs **platform AgentHarness** |
| **AgentHarness abandoned?** | **No** — retained for governed multi-turn + tool-proposal model |
| **AgentSessionAdapter rejected?** | **No** — retained for engineering pilot process sessions (mock primary; commercial CLI still blocked for expansion) |

### D-series (required decisions 1–16)

| # | Decision |
| --- | --- |
| **1. Canonical abstraction name (platform multi-turn)** | **AgentHarness** |
| **2. Canonical owning package (future types)** | `saathi.agent_runtime` (driver protocol + future types) with platform-owned **HarnessSessionController** mediator (may live under `saathi.platform` or `saathi.agent_runtime` — package split is an implementation detail; **controller is platform-trusted**, adapter is not) |
| **3. AgentHarness remains accepted?** | **Yes** — `ACCEPTED_DESIGN_ONLY` |
| **4. AgentSessionAdapter remains?** | **Yes** — engineering-only active ABC |
| **5. Wrap / implement?** | **Neither in v1.** Future optional **bridge** may adapt a *certified* process driver under AgentHarness only after security ADR |
| **6. Shared protocol needed?** | **No for v1.** Conceptual “untrusted driver” role only |
| **7. Controller required?** | **Yes** for platform AgentHarness path: HarnessSessionController. Engineering keeps EngineeringOrchestrator |
| **8. Authoritative state machine** | Platform: **`agent_runtime.RunState`**. Adapter/harness local state is **projection only**. Engineering: engineering `SessionStatus` + store (not RunStore) |
| **9. Authoritative event model** | Platform: harness events **normalized by controller** into run ledger. Engineering: orchestrator + session ledger (engineering-only; not M10 RunStore) |
| **10. ToolIntent construction** | **Controller / orchestrator / platform binding only** — never AgentHarness adapter, never AgentSessionAdapter |
| **11. Cancellation propagation** | Platform: RunLifecycle / kill switch → controller → harness `request_cancel` + EG cancel. Engineering: StopPolicy → `request_stop` |
| **12. Checkpoints** | Optional on AgentHarness; engineering has separate Checkpoint model — **not unified** in this ADR |
| **13. Sandboxes** | **Separate contract** (unchanged from M385 D8) |
| **14. Commercial CLI adapters** | **Remain blocked** (FZ-07, FZ-02) |
| **15. First implementation milestone** | **FM-I1 (separately authorized):** contract types + **FakeInMemoryHarness** + minimal HarnessSessionController tests only — no CLI, no Ollama, no tools that mutate FS |
| **16. Prior ADRs** | Amends placement of AgentHarness relative to engineering; does **not** supersede ADR-EG, ToolIntent, M385 acceptance, or consolidation freezes |

### Answers to mandatory questions (condensed)

| # | Answer |
| --- | --- |
| 1 | AgentSessionAdapter: governed start/poll/stop of an engineering coding-agent process/session for M20 orchestrator pilots |
| 2 | AgentHarness: multi-turn driver with tool **proposals**, events, cancel ack, optional checkpoints under platform authority |
| 3 | Overlap: session lifecycle, cancel/stop, health-ish status, process-ish supervision concepts, “driver” role |
| 4 | Distinct: turn model, tool proposal mediation, event stream, capability profile, RunState mapping, platform tenancy bind |
| 5 | **Yes, both needed** — different planes and maturity |
| 6 | No wrap today |
| 7 | No shared implementable protocol in v1 |
| 8 | No source rename; document qualification required |
| 9 | No — do not reject AgentHarness |
| 10 | **Yes** — AgentSessionAdapter remains engineering-specific |
| 11 | Platform multi-turn: AgentHarness + HarnessSessionController under agent_runtime/platform |
| 12 | Session lifecycle authority: controller/orchestrator; adapter only local process/session refs |
| 13 | Tool-proposal normalization: **HarnessSessionController** (platform) only |
| 14 | Cancel: runtime/controller request; adapter cooperative ack / process stop |
| 15 | Event normalization: controller (platform); engineering orchestrator for eng plane |
| 16 | Checkpoints: optional harness export; platform verifies; eng checkpoints stay eng-local |
| 17 | Provider details: behind adapter implementations; never credentials in requests |
| 18 | Orchestration sees: AgentHarness (platform) or EngineeringOrchestrator APIs (eng) — not raw process handles as authority |
| 19 | Adapters see: opaque session requests; no ToolIntent minting |
| 20 | First: FakeInMemoryHarness + controller scaffold (FM-I1), not commercial CLIs |

---

## Alternatives considered

| Alt | Outcome |
| --- | --- |
| A — Keep both independent forever | **Rejected** as long-term posture (dual expansion risk); short-term coexistence accepted only with freezes |
| B — AgentHarness wraps AgentSessionAdapter | **Rejected for v1** — interfaces mismatch; wrapping would launder process side effects as “governed turns” |
| C — AgentSessionAdapter implements AgentHarness | **Rejected for v1** — start/poll/stop ≠ turn+tool_proposal contract; security gap on CLI side effects |
| D — Extend AgentSessionAdapter; reject AgentHarness | **Rejected** — loses ToolIntent-first multi-turn model |
| E — Shared DriverProtocol now | **Deferred** — premature until fake platform driver exists |
| **F — Controller composition + plane separation** | **Accepted** |

---

## Authority boundaries (reaffirmed)

```text
Engineering plane (existing):
  EngineeringOrchestrator → AgentSessionAdapter (process driver)
  → engineering store / session ledger
  Must NOT mint ToolIntent or claim M10 run authority

Platform multi-agent plane (future harness path):
  agent_runtime / PlatformAgentRuntime
    → HarnessSessionController
      → AgentHarness adapter (untrusted)
      → tool proposals only
    → ToolIntent → ExecutionGateway → tool_runtime / handlers
  RunStore / RunState authoritative for multi-agent runs

Execution plane (all):
  ExecutionGateway sole external side-effect authority
```

**ClaudeCodeAdapter residual risk:** the `claude` CLI process may perform **unobserved** filesystem (and potentially other) actions inside `allowed_root` without ToolIntent mediation. FM-C2 **does not authorize** this as a platform pattern. Commercial CLI expansion remains **blocked**. Engineering dry_run/mock paths are the preferred pilot path.

---

## Implementation status

**Documentation only.** FM-C2 does **not** authorize:

- AgentHarness types or FakeInMemoryHarness
- AgentSessionAdapter modifications
- New commercial CLI adapters
- HarnessSessionController production code
- Any change to ExecutionGateway, approvals, RBAC, credentials, providers, Trading Guardian, or schedulers

---

## Consequences

### Positive

- CX-05 closed with an explicit relationship
- Clear freezes for what may expand where
- AgentHarness design remains available for governed multi-turn work
- Engineering adapters not falsely elevated to platform gateway peers

### Negative / constraints

- Two driver-shaped concepts remain in the monorepo (by design, plane-labeled)
- Engineering CLI residual side-effect risk remains until isolation/certification
- Shared protocol deferred

### Explicit non-consequences

- No production readiness claim
- No commercial CLI certification
- No FM-I1 auto-start

---

## Freeze disposition (FZ-01 / FZ-02)

| Freeze | Disposition |
| --- | --- |
| **FZ-01** AgentHarness implementation | **PARTIALLY UNFROZEN for FM-I1 only** (2026-08-07 owner authorization): types + FakeInMemoryHarness + HarnessSessionController proof. All other AgentHarness expansion remains frozen. |
| **FZ-02** New AgentSessionAdapter variants | **RETAINED / AMENDED.** No new commercial or product ABC adapters. Mock remains allowed for engineering tests. Future platform drivers implement **AgentHarness**, not new engineering ABC variants. |

---

## First future implementation gate (FM-I1 — not started)

| Gate | Requirement |
| --- | --- |
| Entry | This ADR accepted; FZ-01 unfreeze explicitly authorized for **FakeInMemory only** |
| Scope | Types + FakeInMemoryHarness + HarnessSessionController test double; in-process only |
| Forbidden | Claude Code, Codex, OpenCode, Pi, Ollama, credentials, browser, shell, FS mutation tools, network, trading, production missions |
| Exit | Conformance tests for lifecycle, cancel, tool **proposal** (not execute), event seq; production_certified remains false |

---

## Compliance checklist

| Criterion | Status |
| --- | --- |
| AgentSessionAdapter source/tests inspected | ✓ |
| AgentHarness design reconstructed | ✓ |
| Alternatives evaluated | ✓ |
| One relationship selected | ✓ F |
| No second gateway | ✓ |
| No implementation | ✓ |
| Freezes retained/amended | ✓ |
| CX-05 disposition | ✓ Closed (see contradiction register) |
| Commercial CLIs blocked | ✓ |

---

## References

- Full reconciliation: `docs/architecture/FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md`
- Source: `saathi/engineering/adapters/{base,mock,claude_code}.py`, `orchestrator.py`, `tests/test_m20_0_engineering_orchestrator.py`
- M385: ADR-AGENT-HARNESS-INTERFACE, M385 design
- FM-C1 freezes and CX-05
