# ADR: SaathiOS AgentHarness Interface (M385)

| Field | Value |
| --- | --- |
| **ID** | ADR-AGENT-HARNESS-INTERFACE |
| **Date** | 2026-08-06 |
| **Status** | **ACCEPTED_DESIGN_ONLY** |
| **Milestone** | M385 |
| **Parent decision** | ADR-QM-MULTI-AGENT-RUNTIME → `ADAPT_SELECTED_PATTERNS` |
| **Full design** | [`docs/agent-runtime/M385_AGENT_HARNESS_INTERFACE_DESIGN.md`](../agent-runtime/M385_AGENT_HARNESS_INTERFACE_DESIGN.md) |
| **Design baseline SHA** | `949afa68a4135aa94dbdaaf9aecfd618e0948c09` |
| **Design baseline branch** | `milestone/m369-m376-local-model-qualification` (docs authored on this tip; publication may use a dedicated M377–M385 branch) |
| **Implementation status** | **Design-only — not implemented** (no `AgentHarness` / `FakeInMemoryHarness` in `saathi/`) |
| **Authority impact** | None while design-only; if later implemented, driver only under orchestration — never EG replacement |
| **Supersedes** | Informal “multi-CLI as control plane” speculation |
| **Superseded by** | Not superseded. **Amended by** ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP (FM-C2): plane separation vs engineering `AgentSessionAdapter`; implementation still **FZ-01** / FM-I1 gated |
| **Explicit non-actions** | No adapters; no commercial CLIs; no gateway bypass; no TG change |

---

## Context

M377–M384 concluded that SaathiOS should **adapt selected patterns** from multi-harness
systems (conceptually, not by importing QM). The approved concept is a session-oriented
**AgentHarness** abstraction so SaathiOS can drive different coding/reasoning drivers
(Claude Code, Codex, OpenCode, local models, future runtimes) behind one interface.

SaathiOS already has:

| Layer | Owner | Role |
| --- | --- | --- |
| Multi-agent run lifecycle | `saathi.agent_runtime` (M10/M48) | Plan, DAG, lease, cancel, checkpoint, ledger |
| Side effects | `saathi.execution.ExecutionGateway` | Sole external-action authority via ToolIntent |
| Tools | `saathi.tool_runtime` | Governed tool execution |
| Inference | ModelRouter / provider governance (M21–M25) | Model selection & provider policy |
| Application harness | M17.3 `application_harness` | Argv-only structured CLI adapters (media/tools) — **not** multi-turn agent drivers |
| Approvals / credentials | M35 + existing gates | Fail-closed human gates; secret handles/leases |
| Trading | Trading Guardian + contract PROHIBITED financial execution | Finance safety |

Without a harness abstraction, each future coding CLI would invent its own session,
event, cancel, and tool paths — risking gateway bypass and authority drift.

---

## Decision

### D1 — AgentHarness becomes a SaathiOS abstraction

**Yes.** AgentHarness is an **approved internal design contract** for multi-turn
coding/reasoning **drivers**. It is **not** a second runtime, not a second orchestrator,
and **not** an authority layer.

### D2 — Architectural placement

```text
Surface / Mission / Chat
        ↓
agent_runtime (Orchestrator + RunLifecycle + contracts)   ← run authority
        ↓
HarnessSessionController (future; platform-owned mediator) ← binds run ↔ harness session
        ↓
AgentHarness adapter (driver only: model loop, stream text) ← untrusted driver
        ↑ tool proposals only (never direct execution)
        ↓
ToolIntent (immutable) → ExecutionGateway → tool_runtime / connectors / browser / CLI
        ↓
Evidence + RunStore ledger + provider governance
```

AgentHarness sits **beside/under** agent_runtime as a **pluggable driver**, not above
ExecutionGateway. ApplicationHarness (M17.3) remains a **separate** contract for
structured single-action CLI tools.

### D3 — What AgentHarness may control

- Declaring **descriptive** capabilities (streaming, checkpoints, etc.)
- Harness-local session/driver state **references** (opaque to callers except via events)
- Emitting **normalized events** and **tool proposals**
- Cooperative cancel acknowledgment and health/diagnostics
- Optional checkpoint **export** of harness-local state (integrity-checked by platform)

### D4 — What AgentHarness must never control

- Authorization, approval issuance, or RBAC grants
- Credential storage, materialization, or secret values
- Direct tool, shell, browser, filesystem, or network execution
- Provider secret access or provider policy
- Trading Guardian decisions or financial execution
- Certification, package trust, or deployment authority
- Self-promotion of capabilities into permissions
- Audit suppression, event forgery acceptance, or replay bypass
- Kill-switch authority beyond acknowledging cancel requests

### D5 — Visibility

**Internal first.** Not a public SDK or external plugin market in v1.
Callers: agent_runtime mediator, certified internal tests, future operator CLI only after
conformance. Public API requires a later ADR.

### D6 — Sync vs streaming

**Both required** in the contract:

- **Synchronous command API:** start/submit/cancel/close/health return structured results
  (TurnHandle, SessionSnapshot).
- **Streaming/observation API:** ordered event stream (or poll of durable events) for
  text deltas, tool proposals, waits, errors.

Streaming is the primary UX path; sync without event durability is non-conformant.

### D7 — Checkpoints

**Optional capability**, not mandatory for minimum adapter conformance.

- Capability id: `checkpoints`
- Minimum adapters may omit restore
- When claimed, checkpoint integrity (hash, owner, session binding) is **mandatory**
- Platform stores checkpoint **metadata + payload refs**; harness must not be sole durable home

### D8 — Sandbox

**Sandbox is a separate contract**, not part of AgentHarness.

- Harness may declare `requires_isolated_execution` (descriptive)
- Isolation is provided only via ExecutionGateway families (tool_runtime, application
  harness, computer agent, GovernedBrowser)
- No unrestricted shell/browser/fs/network is implied by any harness capability

### D9 — Minimum adapter capabilities (required)

| Capability id | Required? |
| --- | --- |
| `session_lifecycle` | **Yes** |
| `submit_turn` | **Yes** |
| `event_stream` | **Yes** |
| `cooperative_cancel` | **Yes** |
| `tool_proposals` | **Yes** (even if adapter only proposes empty set) |
| `health` | **Yes** |
| `resource_usage_report` | **Yes** (may report zeros; must not lie about known usage) |
| `checkpoints` | Optional |
| `resume_session` | Optional |
| `multimodal_input` | Optional |
| `reasoning_summary` | Optional (safe summaries only; never private CoT) |

### D10 — First future evaluation order (implementation **not** authorized here)

1. **FakeInMemoryHarness** (conformance driver)
2. **LocalModelHarness** (read-only / advisory turns; local inference only)
3. Bounded coding adapter (later, gated) — not Claude Code first

**First real-world candidate after fake + local:** a **bounded local coding adapter**
under strict tool allowlist — **not** Claude Code / Codex / OpenCode first, because
those expand process and credential surface. Commercial CLI harnesses require separate
security ADRs and package certification.

### D11 — Explicit rejections (carry forward from M377–M384)

- QM as core runtime; import of QM source
- Dangerous / unrestricted modes
- Browser or shell outside governed tool execution
- Plaintext credential ownership by agents
- Replacing ExecutionGateway, approvals, RBAC, certification, provider governance,
  or Trading Guardian

---

## Alternatives considered

| Option | Outcome |
| --- | --- |
| Do not introduce AgentHarness; keep ad-hoc CLI integrations | Rejected — risks dual tool paths and gateway bypass |
| Treat commercial coding CLIs as the authority surface | Rejected — violates ExecutionGateway / credential / TG model |
| Make AgentHarness a public SDK in v1 | Rejected — internal-first (D5) until conformance exists |
| Fold AgentHarness into ApplicationHarness (M17.3) | Rejected — different concerns (multi-turn driver vs argv tool) |
| Implement adapters in the same milestone as the interface | Rejected — design-only gate |
| **Approve internal AgentHarness design contract** | **Accepted** (this ADR) |

### Rejected claims (must not be inferred from this ADR)

- Runtime implementation or adapter availability
- Provider connectivity or commercial CLI certification
- Production readiness or public SDK stability
- Sandbox certification or QM integration
- Authority to start M386/M387/implementation without new authorization

---

## Implementation status

**Design documentation only.** No Python/TS types package, no FakeInMemoryHarness,
no LocalModelHarness, no commercial CLI adapter, no CI suite, and no behavioral
change to `saathi.agent_runtime` or ExecutionGateway were authorized by M385.

---

## Authority boundaries

| Concern | Authority |
| --- | --- |
| Run lifecycle | `agent_runtime` (Orchestrator, RunLifecycle, contracts) |
| Side effects | ExecutionGateway via immutable ToolIntent |
| Approvals / RBAC | Existing approval and identity systems |
| Credentials | Credential governance / leases (never harness-owned) |
| Trading | Trading Guardian + FINANCIAL_EXECUTION PROHIBITED |
| Providers | Provider governance / ModelRouter |
| Harness | Untrusted driver: events + **tool proposals only** |

### Security limitations

- Untrusted model output can still propose malicious tools; mediation and deny paths are mandatory.
- Cooperative cancel may need process isolation for non-conformant foreign CLIs (future).
- Optional checkpoints require integrity hashing; harness must not be sole durable store.
- Commercial CLI adapters expand process and credential surface — blocked until dedicated security ADR + certification.

---

## Supersession rules

- This ADR is a **child** of ADR-QM-MULTI-AGENT-RUNTIME (`ADAPT_SELECTED_PATTERNS`).
- It does **not** supersede ExecutionGateway, ToolIntent, M48 contracts, ApplicationHarness
  (M17.3), provider governance, or Trading Guardian ADRs/policies.
- Implementation milestones may refine operation names and types without changing D1–D11
  authority boundaries unless a new ADR revises this one.
- Public SDK, commercial CLI adapters, or sandbox-as-harness would require **new ADRs**.

---

## Explicit non-actions (M385)

- No M386, M387, types package, FakeInMemoryHarness, adapters, tests, or providers
- No QM source import
- No production code or runtime behavior change
- No claim that AgentHarness is available to operators or certified for production

---

## Consequences

### Positive

- Single driver contract for multi-turn agents without dual authority
- Clear composition with M10/M48 lifecycle and ToolIntent path
- Conformance suite can gate adapters before any live CLI
- Aligns with OpenJarvis/CLI-Anything external-reference posture (design-only)

### Negative / constraints

- Implementation effort remains Medium–High and multi-milestone
- Commercial coding CLIs remain blocked until security + certification gates
- Operators must not confuse ApplicationHarness (M17.3) with AgentHarness

### Non-consequences (this milestone)

- No production code, adapters, tests, providers, credentials, CI, or runtime behavior changes
- No Trading Guardian engagement change
- No QM import

---

## Success criteria (M385)

| Criterion | Status |
| --- | --- |
| No production code changed | ✓ |
| No adapter implemented | ✓ |
| No provider connected | ✓ |
| No credentials added | ✓ |
| No runtime behavior changed | ✓ |
| No ExecutionGateway bypass introduced | ✓ |
| No approval authority moved | ✓ |
| No Trading Guardian authority changed | ✓ |
| No QM source imported | ✓ |
| Lifecycle deterministic (documented) | ✓ |
| Tool mediation explicit | ✓ |
| Event protocol defined | ✓ |
| Cancellation fail-closed (documented) | ✓ |
| Threats and residual risks documented | ✓ |
| Conformance requirements specified | ✓ |
| Future implementation separately gated | ✓ |

---

## Future milestones (do not auto-start)

| ID | Scope | Gate |
| --- | --- | --- |
| M386 | Scope/policy floor composition design | Separate design ADR |
| M387 | Skill promotion lifecycle design | Separate design ADR |
| M389+ | AgentHarness **types + FakeInMemoryHarness + conformance** | Human authorization; docs→code only after review |
| later | LocalModelHarness (read-only) | Conformance green; local provider cert |
| later | Bounded coding adapter | Tool allowlist + TG freeze + security cert |
| never by default | Unrestricted Claude Code/Codex/OpenCode | Requires dedicated security ADR + certification |

---

## References

- `docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md`
- `docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md`
- `docs/agent-runtime/M48_1_*`, `M48_2_*`, `M48_3_*`
- `docs/adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md`, `docs/M28_EXECUTION_GATEWAY.md`
- `docs/M17_3_HARNESS_ARCHITECTURE.md` (ApplicationHarness — distinct)
- `saathi/agent_runtime/{models,contracts,lifecycle,gateway_exec,orchestrator}.py`
- `saathi/execution/{toolintent,gateway,universal}.py`
- Full design: `docs/agent-runtime/M385_AGENT_HARNESS_INTERFACE_DESIGN.md`
