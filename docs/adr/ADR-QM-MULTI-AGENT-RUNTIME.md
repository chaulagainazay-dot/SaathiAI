# ADR: QM Multi-Agent Runtime — Architecture Gap Analysis (M377–M384)

| Field | Value |
| --- | --- |
| **ID** | ADR-QM-MULTI-AGENT-RUNTIME |
| **Date** | 2026-08-06 |
| **Status** | **ACCEPTED_DESIGN_ONLY** (analysis decision; no runtime integration authorized) |
| **Milestone** | M377–M384 |
| **Decision** | **ADAPT_SELECTED_PATTERNS** |
| **Implementation status** | **No QM code in SaathiOS** — conceptual reference only |
| **Authority impact** | Must not replace ExecutionGateway, Approval, RBAC, credentials, or Trading Guardian |
| **Supersedes** | Informal “adopt QM as runtime” speculation |
| **Superseded by** | None for decision; **milestone numbers** M386/M387 in future table superseded by consolidation renumbering (see ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION) |
| **QM source** | https://github.com/yc-software/qm |
| **QM audited tip** | `0f0e0adccce2` (2026-08-05; main) |
| **License** | MIT (`Copyright (c) 2026 QM contributors`) |
| **SaathiOS baseline** | `949afa68a4135aa94dbdaaf9aecfd618e0948c09` on `milestone/m369-m376-local-model-qualification` |
| **Full evidence** | [`docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md`](../agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md) |

---

## Context

SaathiOS is a local-first AI operating system with hard governance: ExecutionGateway,
immutable ToolIntent, fail-closed approval, RBAC, certification, evidence, and
Trading Guardian. QM (yc-software/qm) is a multiplayer TypeScript agent harness
designed for startup teams on Slack and web, with multi-harness support (Pi,
OpenCode, Codex, Claude Code), per-scope sandboxes, and org-level security postures.

M377–M384 asks whether QM concepts should be adopted, adapted, or rejected —
**without** merging, installing, deploying, or modifying production SaathiOS runtime.

---

## Decision

**ADAPT_SELECTED_PATTERNS**

QM is a **conceptual reference only**. SaathiOS must not:

- import or vendor QM source;
- replace ExecutionGateway, Approval, Governance, RBAC, or Trading Guardian;
- deploy QM (Docker/Fly/AWS) into the SaathiOS control plane;
- enable Slack/cloud connectors via QM;
- adopt QM’s `dangerous` security posture or browser-outside-gate model.

SaathiOS **may** independently re-implement selected *patterns* (original code,
Python-native, gateway-bound) in future milestones after separate design ADRs:

1. **AgentHarness session interface** (start/submit/stream/cancel/checkpoint/close)
   as a pluggable **untrusted driver under** `agent_runtime` (see ADR-AGENT-HARNESS-INTERFACE);
   not a second execution authority and not above ExecutionGateway.
2. **Scope composition model** (org floor policies that scopes may only tighten).
3. **Skill promotion lifecycle** (private → grant → admin-gated org promotion).
4. **Security posture composition** mapped to SaathiOS risk/approval floors
   (strict-equivalent only; no dangerous mode).

This matches prior external-reference posture for OpenJarvis and CLI-Anything
(design only; no source copy; preserve SaathiOS authorities).

---

## Alternatives considered

| Option | Outcome |
| --- | --- |
| `REJECT_QM` | Rejected as too absolute; valuable harness/scope/skill patterns would be discarded |
| `USE_QM_AS_REFERENCE` only | True but incomplete; selected patterns may be adapted later under new ADRs |
| **`ADAPT_SELECTED_PATTERNS`** | **Accepted** |
| `ISOLATED_READ_ONLY_EVALUATION` | Satisfied by this analysis milestone; decision goes one step further |
| `LIMITED_PLUGIN_INTEGRATION` | **Rejected** — couples stacks, credentials, deployment; high risk |
| `FULL_ARCHITECTURAL_ALIGNMENT` | **Rejected** — duplicates systems, weakens governance, violates local-first |

### Rejected outcomes (non-negotiable)

- QM as SaathiOS core runtime
- Import/vendor of QM source
- Replace ExecutionGateway, Approval, Governance, RBAC, or Trading Guardian
- Deploy QM (Docker/Fly/AWS) into the SaathiOS control plane
- Dangerous/unrestricted security postures
- Browser or shell activity outside governed tool execution

---

## Implementation status

**Analysis-only.** No runtime types, adapters, providers, or deployment artifacts were
introduced by M377–M384. M385 (AgentHarness interface design) is a **separate
design-only** ADR and does not implement adapters.

---

## Authority boundaries

| Authority | Owner | QM / this ADR |
| --- | --- | --- |
| External action | ExecutionGateway + ToolIntent | Must not replace |
| Approvals / RBAC | Existing SaathiOS systems | Must not replace |
| Credentials | SaathiOS credential governance | Must not materialize agent-owned secrets |
| Trading | Trading Guardian | Must not weaken; remain advisory/fail-closed as today |
| Certification / providers | Existing governance | Must not bypass |

### Security limitations (from QM evidence; why full adopt is unsafe)

QM publishes material limitations (command-policy bypass, browser outside some gates,
plaintext sandbox credentials while in use, incomplete kill switch, heuristic screening).
Those limitations are reasons to **adapt patterns only**, not to integrate QM.

---

## Supersession rules

- This ADR supersedes informal speculation that QM should become the SaathiOS runtime.
- It does **not** supersede ADR-EXECUTIONGATEWAY-SPECIFICATION, Trading Guardian
  policy, or provider/certification ADRs.
- Pattern adaptation requires **child ADRs** (e.g. ADR-AGENT-HARNESS-INTERFACE for
  harness design). Implementation of any pattern requires a further authorized milestone.
- Revising this decision to allow plugin integration or full alignment requires a new
  ADR with stronger security evidence than QM currently publishes.

---

## Explicit non-actions (M377–M384)

- No production code, deploy, credentials, CI, schema, or provider changes
- No QM import, install, or cloud connection
- No M386/M387/M388 work started by this ADR alone
- No claim of production readiness, adapter availability, or QM certification

---

## Rationale (evidence summary)

| Dimension | Finding |
| --- | --- |
| Architecture | Conceptual overlap (core loop, harness adapters, sandbox, memory, skills, cron) but **different substrate** (Node/TS + Postgres multiplayer vs Python + SQLite local-first). Full alignment would fork SaathiOS identity. |
| Superior QM ideas | Multi-harness adapter profile; scope-owned durable computer; org-floor policy composition; skill packs + grant model; deliberate portal-only admin/impersonation/approval walls. |
| Duplication | Agent runtime, sessions, approvals, credentials, memory, skills, scheduler, audit, sandbox/harness, model gateway already exist in SaathiOS. |
| Governance conflict | QM agent acts *as the person*; credentials materialize into sandbox; command policy is regex speed-bump (QM SECURITY.md); browser outside command/HITL gates; incomplete org kill switch; admin content reads without user consent. |
| Never adopt | `dangerous` posture; browser bypass of core gates; Slack-first multiplayer core; Fly/AWS as default control plane; replacing ToolIntent/ExecutionGateway; weakening Trading Guardian. |
| License | MIT — attribution required if code copied; **this milestone copies no code**. |

---

## Consequences

### Positive

- Clear reference boundary: learn from QM without runtime capture.
- Future harness work has a documented interface shape.
- Risk register and security comparison inform red-team priorities.

### Negative / constraints

- No multiplayer Slack workspace product from this decision.
- Multi-harness (Claude Code/Codex/OpenCode) remains **future optional adapters**,
  not a commitment to run those CLIs under SaathiOS.
- Implementation effort for even selected patterns remains Medium–High and must
  stay under ExecutionGateway + Trading Guardian.

### Explicit non-consequences

- No production code changed in M377–M384.
- No credentials, CI, providers, schemas, or deployments changed.
- Governance remains fail-closed and SaathiOS-native.

---

## Scores (terminal)

| Metric | Score |
| --- | --- |
| Architecture Compatibility | **42 / 100** |
| Security Compatibility | **38 / 100** |
| Governance Compatibility | **31 / 100** |
| Implementation Effort (if full align) | **High** |
| Implementation Effort (selected patterns only) | **Medium** |
| Risk Level (full adopt/merge) | **Critical** |
| Risk Level (this decision) | **Low** |

---

## Future milestones (design-only until authorized)

| ID | Scope | Status / gate |
| --- | --- | --- |
| M385 | AgentHarness **interface design** ADR (no adapters) | **Design complete** — ADR-AGENT-HARNESS-INTERFACE; no implementation |
| M386 | Scope/policy floor composition design | Future; org floor only-tighten; **do not auto-start** |
| M387 | Skill promotion lifecycle design | Future; admin-gated; **do not auto-start** |
| M388 | Optional: isolated read-only re-eval if QM tip changes | Analysis-only if needed |
| later | Types / FakeInMemoryHarness / adapters | **Separately authorized**; commercial CLIs blocked by default |

**Do not** schedule FULL_ARCHITECTURAL_ALIGNMENT, LIMITED_PLUGIN_INTEGRATION, or
QM deployment without a new ADR that revises this one with stronger security
evidence than QM currently publishes.

---

## Compliance checklist (M377–M384 success criteria)

| Criterion | Status |
| --- | --- |
| No production code changed | ✓ (docs + ADR only) |
| No runtime replaced | ✓ |
| No deployment performed | ✓ |
| No cloud resources created | ✓ |
| No credentials added | ✓ |
| No governance weakened | ✓ |
| Architecture documented | ✓ |
| Adoption recommendations evidence-based | ✓ |

---

## References

- QM README, SECURITY.md, LICENSE, `src/harness/`, `src/sandbox/`, `src/memory/`,
  `src/skills/`, `src/policy/`, `src/security/`, `src/types.ts` (tip `0f0e0adccce2`)
- SaathiOS: `docs/adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md`, `docs/M28_EXECUTION_GATEWAY.md`,
  `docs/M10_AGENT_RUNTIME_AUDIT.md`, `docs/M17_3_HARNESS_ARCHITECTURE.md`,
  `docs/M30_SANDBOX_HARNESS.md`, `docs/M35_APPROVAL_AND_LEASES.md`,
  `docs/M15_2_AGENT_SECURITY_AUDIT.md`, `docs/adr/ADR-OPENJARVIS-LOCAL-RUNTIME.md`,
  `saathi/agent_runtime/`, `saathi/execution/`, `saathi/tool_runtime/`,
  `saathi/memory/`, `saathi/security/`
- Full package: `docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md`
