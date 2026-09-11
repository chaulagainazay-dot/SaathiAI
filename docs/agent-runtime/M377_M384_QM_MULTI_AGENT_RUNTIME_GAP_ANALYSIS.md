# M377–M384 — QM Multi-Agent Runtime Architecture Gap Analysis

**Status:** ANALYSIS COMPLETE — no production code changed
**Date:** 2026-08-06
**Branch:** `milestone/m369-m376-local-model-qualification`
**Starting SaathiOS commit:** `949afa68a4135aa94dbdaaf9aecfd618e0948c09`
**QM repository:** https://github.com/yc-software/qm
**QM audited tip:** `0f0e0adccce2` (2026-08-05T22:59:13Z, main)
**QM license:** MIT — Copyright (c) 2026 QM contributors
**QM language / scale (public):** TypeScript · ~11.9k stars · multiplayer agent harness
**Formal ADR:** [`docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md`](../adr/ADR-QM-MULTI-AGENT-RUNTIME.md)
**Decision:** **ADAPT_SELECTED_PATTERNS**

---

## Constraints observed (fail-closed analysis)

This milestone did **not**:

- modify SaathiOS production architecture or runtime code;
- replace ExecutionGateway, Approval, Governance, RBAC, or Trading Guardian;
- import, vendor, submodule, or install QM;
- deploy QM (local Docker, Fly, AWS);
- connect Slack, email, AWS, Fly.io, or other cloud services;
- add credentials or change CI / providers / database schemas;
- weaken governance or Trading Guardian.

Evidence is from **public** QM GitHub content (README, SECURITY.md, LICENSE, source paths)
and **local read-only** inspection of SaathiOS trees and existing ADRs.

---

## Primary questions — answers

### 1. Can QM improve SaathiOS?

**Yes, as a design reference; no, as a replacement runtime.**

QM demonstrates mature product thinking for multiplayer agent work (scopes, multi-harness,
durable per-scope computers, skill packs, posture floors). SaathiOS already owns a deeper
governance spine for local-first, fail-closed, certified execution. The improvement path is
**selective pattern adaptation in original SaathiOS code**, not QM integration.

### 2. Which QM ideas are genuinely superior?

| Idea | Why superior (for SaathiOS learning) | Evidence |
| --- | --- | --- |
| **Harness adapter surface** | Single `Harness` with `turns.runTurn`, model utilities, tool name mapping, capability profile (`abort`, `steer`, `images`, …) across Pi / OpenCode / Codex / Claude Code | `src/harness/harness.ts`, adapters `pi-harness.ts`, `opencode-harness.ts`, `codex-harness.ts`, `claude-harness.ts` |
| **Runtime choice resolution** | Org-approved harnesses; scope can select within floor; invalid request non-retryable | `src/harness/harness-router.ts` |
| **Scope-owned durable sandbox** | Layers (`ro`/`rw`), provision/run/teardown, process sessions, multiple backends (local, docker, AWS microVM, sprites) | `src/sandbox/sandbox.ts`, backends under `src/sandbox/` |
| **Org security posture floor** | Org posture; scopes may only **tighten** (`composeSecurityPosture`) | `src/security/security-posture.ts` |
| **Command policy org floor** | Recursive rm / force-push / DROP TABLE / pipe-to-shell rules; scopes compose | `src/policy/command-policy.ts` |
| **Portal-only privilege walls** | Admin grants, impersonation, command-approval decisions excluded from agent self-API | QM `SECURITY.md` |
| **Skill pack + grant model** | Scope-owned skills, packs from git, admin-gated org promotion | README + `src/skills/*` |
| **Durable-by-default discipline** | Blue-green multi-instance; no RAM-only audit/queue | QM `AGENTS.md` |

### 3. Which QM ideas duplicate existing SaathiOS systems?

| QM concept | SaathiOS counterpart | Evidence |
| --- | --- | --- |
| Headless core / agent loop | `saathi/agent_runtime/` (orchestrator, lifecycle, store, graph, policy) | M10 audit; `orchestrator.py`, `lifecycle.py` |
| Model gateway | `saathi/execution/orchestrators/model_gateway.py`, inference stack, provider governance M21–M25 | docs/M21_*, M22–M25 |
| Execution / tools | ExecutionGateway + ToolIntent + `tool_runtime` | ADR-EXECUTIONGATEWAY; `gateway.py`; M28 |
| Approvals | ApprovalGate, M35 leases, agent_runtime approve API | M35; `api.py` approve |
| Credentials / keychain | `saathi/credentials/`, secret handles, M31–M35 | M35 docs |
| Memory | `saathi/memory/` hierarchical + engine + promotion | M2 audit; hierarchical/platform |
| Skills | `saathi/skills/`, `skills_library/` | SKILL.md trees + SkillStore |
| Sandbox / harness | Application harness M17.3–17.4; connector sandbox M30; browser M17.24–26 | M17.3, M30 |
| Scheduling | `saathi/scheduler.py`, platform scheduler foundation (Brain.md M-series) | scheduler.py |
| Audit / evidence | Evidence packages, run ledger, security store, red-team harness | M15.2; evidence/ |
| Identity / RBAC | platform identity M50+, RBAC, ownership checks | Brain.md; M15.2 ISO-001 fix |
| Computer agent | `saathi/computer_agent/` | M17 series |
| CLI harness adapters | Application harness + OpenJarvis-as-adapter precedent | ADR-OPENJARVIS |

### 4. Which QM ideas conflict with SaathiOS governance?

| QM idea | Conflict |
| --- | --- |
| Agent acts **as the user** with their credentials in sandbox | SaathiOS leases secrets through gateway; credentials must not live in agent-visible ambient form |
| Default **Auto** posture (classifier, not always HITL) | SaathiOS fail-closed approval for risk/mutation; classifier ≠ authorization (QM itself admits this) |
| **Dangerous** posture exists | Incompatible with SaathiOS production safety culture |
| Command policy is **text regex**, admitted bypassable | SaathiOS requires gateway + side-effect class + certification, not shell classification alone |
| Browser actions **outside** command policy / HITL | Conflicts with GovernedBrowser path (M17.23–26) and ExecutionGateway browser family |
| Incomplete **org kill switch** / provider token revocation | SaathiOS kill-switch matrix (M21.4) and residual-exception discipline are harder requirements |
| Admin content reads **without user consent** (audited only) | Stronger privacy / dual-control expectations for financial and personal OS data |
| Multiplayer Slack/web as primary surface | SaathiOS local-first; Telegram/CEO surfaces exist but cloud multiplayer is not the control plane |
| Postgres + Fly/AWS deployment as product default | SaathiOS SQLite/local durability and independent deploy story |

### 5. Which QM ideas should never be adopted?

1. Replacing ExecutionGateway / ToolIntent / UniversalBoundary.
2. Replacing Trading Guardian or weakening advisory/approval defaults.
3. Enabling **dangerous** (or equivalent “no screening, no pauses”) production mode.
4. Materializing long-lived plaintext secrets into agent sandboxes as the primary model.
5. Browser runners that skip command policy and human approval for side effects.
6. Agent-reachable admin grant, impersonation, or approval-decision APIs.
7. Full QM core as SaathiOS runtime (stack, deployment, identity model).
8. Slack-coupled ambient judge paths that bypass ModelGateway-equivalent controls.
9. Bearer capability links for public agent control plane access.
10. Importing QM npm package into the SaathiOS production dependency tree without a
    separate, stronger security ADR and isolation plan.

### 6. What architectural patterns deserve independent implementation?

1. **AgentHarness** interface (session-oriented) on top of SaathiOS authorities.
2. **Policy floor composition** (org/global floor; scopes only tighten).
3. **Skill promotion workflow** (private → shared grant → admin org promotion + evidence).
4. **Harness capability profiles** (declare abort/stream/images without coupling to one CLI).
5. **Workspace layer mounts** (read-only shared + read-write personal) for multi-project work —
   mapped to SaathiOS project/workspace model, not Slack rooms.
6. **Explicit portal-only privilege walls** catalog (already partially present; formalize).

---

# 1. Architecture comparison report

## A. Overall architecture

### QM

```
Postgres (sessions · memory · queue · grants · audit)
        ↕
Headless core (TypeScript / Node / Fastify)
  · identity · policy · scheduler · API
  · agent loop (Pi | OpenCode | Codex | Claude Code)
        ↕
Per-scope sandbox (files · tools · logged-in services)
        ↕
Optional plugins: Slack, web UI, admin, portal
```

- **Runtime:** Node running TypeScript; durable state in Postgres.
- **Services:** core API, workers/runs (`src/runs/`), sandbox backends, model gateway,
  credentials/keychain, cron, monitors/watches, delivery.
- **Boundaries:** scope resolution → grants → command policy → security posture → sandbox.
- **Layering:** substrates behind interfaces (harness, session store, sandbox, memory);
  deployment directory for org-specific config (`deploy/layers/`, `qm init`).
- **Lifecycle:** turn-based (`HarnessTurnInput` → `runTurn` → `HarnessTurnResult`);
  runs/workers for concurrency; blue-green multi-instance.
- **Orchestration:** `src/core/orchestrator*` + turn resume/wake envelopes; background
  cron/monitor triggers with delivery provenance.

### SaathiOS

```
Operator / chat / API / CLI
        ↓
Agent runtime (plan → DAG → gateway_exec → checkpoint)
        ↓
ExecutionGateway.submit(ToolIntent)
  · validate · authorize · risk · approval · credentials
  · family handlers (connector / CLI / local / MCP / browser)
  · evidence · sanitize · events
        ↓
Adapters (connectors, application harness, computer agent, inference)
        ↓
Local durable stores (SQLite family) + evidence packages
```

- **Runtime:** Python process(es); local-first.
- **Authorities that must not be replaced:** ExecutionGateway, Approval, RBAC,
  Trading Guardian, certification gates.
- **Lifecycle:** durable runs with leases, cancel, timeout classification, stale
  reconciliation (`lifecycle.py`).
- **Orchestration:** multi-agent DAG + strategies; missions/platform modules for
  business domains; Trading Guardian for financial path.

### Comparison judgment

| Aspect | QM | SaathiOS | Winner for SaathiOS goals |
| --- | --- | --- | --- |
| Multiplayer collab product | Strong | Partial (workspace, CEO, chat roles) | QM product shape |
| Local-first / 8 GB Mac | Secondary | Primary | SaathiOS |
| Fail-closed external action | Partial | Strong | SaathiOS |
| Multi-harness coding CLIs | Strong | Partial (harness + inference adapters) | QM pattern |
| Financial / TG safety | Not designed for it | First-class | SaathiOS |
| Deployment multiplayer cloud | First-class | Optional / constrained | Independent (keep SaathiOS) |

---

## B. Agent runtime comparison

| Concern | QM | SaathiOS | Gap |
| --- | --- | --- | --- |
| Agent lifecycle | Sessions + runs + workers; turn resume; reaper | RunStore + LifecycleController (leases, cancel, stale classes) | Different durability models; SaathiOS already rich |
| Conversations | Session entries (user/assistant/tool/approval types); Slack/web | Chat engine + agent_runtime conversation_id | QM multi-surface session model is richer product-wise |
| Execution loop | Harness `runTurn` with tools + screening hooks | Orchestrator plan→execute→verify→retry + gateway_exec | SaathiOS loop is governance-first |
| Checkpoints | Tape/replay (`harness/replay.ts`, tape-fold) | `RunStore.checkpoint` | Both have; different semantics |
| Cancellation | `AbortSignal` on turn input | `cancel` API + cancel grace + cancel status | Both; SaathiOS more classification-heavy |
| Recovery | Multi-instance durable stores; reaper | StaleClass / RecoveryAction / ReconcileAction | SaathiOS more explicit recovery taxonomy |
| Concurrency | Workers, instance registry, task protection | Run leases / worker_id | Both |
| Ownership | Scope + principal per turn; no agent impersonation | Actor + account ownership (M15.2 engine fix) | Both care; SaathiOS ownership bug history informs rigor |

---

## C. Scope architecture

### QM scopes

From `src/types.ts`:

- Scope kinds include **user, org, channel, group, team** (parsed `kind:ref`).
- Shared scopes: channel/group.
- Conversations: dm / channel / group with audience principals.
- **Resolution** yields workspace layers, system prompt, egress, command policy,
  security policy, approval grant modes, granted handles.
- Grants: ownerScope → granteeScope with read/write on resources
  (file, skill, deploy, cron, service-cred).

### SaathiOS workspace model

- Mission/project/workspace oriented (`workspace.py`, platform projects).
- Business-unit isolation on ExecutionGateway.
- Memory namespaces / engine scopes (M9/M10).
- Not Slack-room-native; multi-user RBAC via platform identity.

### Recommendation

Do **not** adopt Slack room semantics as the core tenancy model.
**Do** consider a SaathiOS-native scope tuple, e.g.:

```text
(org|solo) → business_unit → project → agent_run → session
```

with **policy floors that only tighten** (QM pattern).

---

## D. Harness abstraction

### QM surface (evidence)

```typescript
// Conceptual surface from src/harness/harness.ts
interface Harness {
  profile: HarnessAdapterProfile; // transport + capabilities
  turns: { runTurn(input: HarnessTurnInput): Promise<HarnessTurnResult>; close?(); resetSession?() };
  models: HarnessModelUtilities;  // shouldRespond, compact, screenSecurity, …
  tools: HarnessToolPresentation;
}
```

Supported harnesses (files): Pi, OpenCode, Codex, Claude Code, mock.
Router enforces **approved harness list** per org/scope.

### SaathiOS recommendation: AgentHarness (design only — **not implemented**)

Recommended **conceptual** interface (Python-shaped; names only):

```text
AgentHarness
  start_session(scope, policy_floor, model_prefs) → SessionHandle
  submit_turn(session, input, attachments?) → TurnId
  stream_events(session | turn) → Iterator[Event]
  cancel(session | turn, actor) → CancelResult
  checkpoint(session, label) → CheckpointId
  close_session(session) → None
```

**Hard rules for any future implementation:**

1. Every tool/side effect still becomes **ToolIntent → ExecutionGateway**.
2. Harness is a **conversation/model adapter**, not an execution authority.
3. Adapters for Claude Code / Codex / OpenCode / Pi are **optional, sandboxed,
   certified packages** — default off.
4. No QM source import; MIT attribution only if code is later copied deliberately.
5. Trading Guardian and financial tools remain outside harness discretion.

**Should SaathiOS create AgentHarness?**
**Yes, as a future design milestone (M385), not as QM integration.**

---

## E. Sandbox model comparison

| Dimension | QM | SaathiOS | Verdict |
| --- | --- | --- | --- |
| Filesystem isolation | Per-scope handle + layers; path `..` rejected | Temp-dir sandbox (M30); application harness file-root confined | Both; QM durable computer is product-richer |
| Tool isolation | Fixed tool surface + `execute` in sandbox | tool_runtime allowlists + gateway families | SaathiOS more governance-bound |
| Credentials | Keychain + resident auth paths; **plaintext while in use** (SECURITY.md) | Secret handles, leases, max uses, no ambient secrets in intent | **Prefer SaathiOS** |
| Network / egress | Egress policy; enforcement backend-dependent; **conditional** | Domain policy (browser M17.26); connector policy | Prefer SaathiOS enforcement claims |
| Browser | Separate provider; **outside some core gates** | GovernedBrowser via gateway | **Never adopt QM browser gap** |
| Persistent state | Durable sandbox / resident disk options | SQLite + workspace files; session DBs | Different product goals |
| Shared vs temp | Layers + grants + scratch | Project/workspace + temp evidence | Adapt layers concept carefully |

---

## F. Memory model comparison

### QM

- Scope-scoped memory service (`memory-service.ts`, Postgres implementation).
- Notebook grammar (`notebook.ts`) — bullet capture, recall caps.
- Policy module for memory access.
- Private / shared / org via **scope identity**, not separate product silos.

### SaathiOS

- Hierarchical working → episodic → semantic.
- Platform memory engine with namespaces; promotion + review queue design (M2).
- Knowledge services M19+; codebase memory M18.
- IELTS-shaped legacy + platform path coexist historically (documented).

### Recommended SaathiOS memory hierarchy (refined by this study)

```text
L0  Working        — session/run ring buffer (ephemeral)
L1  Episodic       — agent_run / conversation events (durable)
L2  Semantic       — promoted patterns (review-gated)
L3  Project        — mission/project knowledge (RBAC)
L4  Org / Solo     — owner-approved institutional memory
L5  Archive        — retention / legal hold
L6  Constitution   — Brain.md / Business.md / style (human-only promote)
```

**Cross-cutting rules:**

- Private by default; share by **grant** (QM idea).
- Promotion requires confidence + review (SaathiOS idea).
- No memory write path bypasses audit.
- Financial / trading memory remains under Trading Guardian data rules.

---

## G. Skill model comparison

### QM

- Scope-owned skills; skill packs from git; materialization into sandbox trees.
- Collision/name handling; sync engine.
- Admin-gated promotion to org; grants for sharing.
- Deployment layer skills versioned by content hash.

### SaathiOS

- `saathi/skills/*/SKILL.md` + `skills_library` store with statuses.
- Application harness HARNESS.md/SKILL.md conventions (M17.3).
- External registry import marked `external_untrusted` until review (CLI-Anything posture).

### Safer lifecycle recommendation

```text
draft (private)
  → review (lint + secret scan + policy)
  → certified (pinned hash, owner, tests)
  → grant (named scopes, read or execute)
  → org_promote (admin + dual control for high risk)
  → revoke / retire (audit, cascade)
```

Never: auto-promote from model output; never execute uncertified external packs.

---

## H. Scheduling comparison

### QM

- Cron store + job queue + scheduler (`src/cron/`).
- Monitors/watches (`src/monitors/`).
- Background wake triggers: cron | webhook | monitor.
- Delivery provenance for background fires.
- Recipient consent fields on triggers.

### SaathiOS

- `scheduler.py` (morning briefing, canteen, content) — lightweight local jobs.
- Platform SchedulerFoundation (Brain.md series) for governed scheduling.
- Mission/event systems for proactive work.

### Governance compatibility

Background work **must** re-enter:

1. identity / scope resolution;
2. risk + approval (standing approvals bounded + revocable);
3. ExecutionGateway;
4. kill switch / budgets;
5. audit + delivery provenance (QM idea worth adapting).

QM’s ambient Slack judge and incomplete ModelGateway use on some paths is a **negative**
pattern for SaathiOS.

---

## I. Security analysis

### QM strengths

- Scope isolation intent and threat model documented.
- Portal-only walls for admin grants, impersonation, approval decisions.
- Security postures with compose-only-tighten.
- Command policy floor even under Dangerous.
- Secret masking module; audit log; capability tokens with expiry.
- npm `min-release-age=7` supply-chain cooldown.
- Explicit experimental disclaimer.

### QM limitations (from SECURITY.md — authoritative)

| # | Limitation |
| --- | --- |
| 1 | Command policy **bypassable** (obfuscation, script write+exec) |
| 2 | Browser actions **outside** command policy / HITL |
| 3 | Sandbox credentials **plaintext while in use** |
| 4 | Credential **purpose not enforced** after materialization |
| 5 | Screening **incomplete/heuristic**; unscreened paths |
| 6 | Audience-floor filtering gaps |
| 7 | Egress enforcement **conditional** / not always built |
| 8 | Admins can read sensitive content without user consent |
| 9 | Durable data / artifacts may accumulate indefinitely |
| 10 | Published-app capability links are **bearer** auth |
| 11 | Portal session residual risk |
| 12 | Some model paths **bypass ModelGateway** |
| 13 | Incomplete kill switch / provider token revocation / secret scan on write |
| 14 | Not a hardened multi-tenant public service |
| 15 | Operator fully trusted (no protection against malicious operator) |

### SaathiOS security posture (relative)

- Deterministic red-team corpus (M15.2).
- Approval binding to exact action; risk ladders.
- Fail-closed gateway and residual-exception discipline.
- Secret handles / leases (M35).
- Kill-switch matrix (M21.4).
- Trading Guardian constraints for finance.

### Security compatibility score drivers

QM is honest and product-mature, but its **coding-agent-as-user** model conflicts with
SaathiOS **gateway-as-authority** model. Score: **38/100**.

---

## J. Governance comparison

| Control | QM | SaathiOS | Prefer |
| --- | --- | --- | --- |
| Approval authority | Human for gated commands; posture-dependent | Fail-closed ApprovalGate + leases | SaathiOS |
| RBAC | Scopes + grants + admin | Platform RBAC + ownership | SaathiOS (domain depth) |
| Audit | Audit log + request capture | Evidence packages + run ledger + security store | Both; SaathiOS certification culture stronger |
| Certification | Deployment doctor / layer pins | Connector/package certification, production cert gates | SaathiOS |
| Replay | Tape/replay harness modes | Evidence + deterministic sandboxes | Both useful |
| Fail-closed execution | Partial (enforcement mode screens fail closed; many gaps) | Core invariant | SaathiOS |
| Trading Guardian | N/A | Mandatory for trading paths | SaathiOS only |

**If weaker → preserve SaathiOS implementation.**
QM is weaker on fail-closed mutation control, browser gating, kill switch completeness,
and financial safety. **Preserve SaathiOS governance wholesale.**

Governance compatibility score: **31/100**.

---

## K. Deployment model

| Mode | QM | SaathiOS recommendation |
| --- | --- | --- |
| Local Docker | Supported (`local/`) | Keep SaathiOS local process; optional containers later |
| Fly.io | First-class | **Do not** adopt as SaathiOS control plane |
| AWS (ECS/Fargate/microVM) | First-class | Independent; do not couple |
| Postgres | Required for durable multi-instance | Remain SQLite-first unless a future multi-user product ADR |
| Deployment directory / `qm init` | Org-owned deploy repo pattern | Interesting for *product packaging* later; not now |

**Recommendation:** SaathiOS remains **independent**. No QM deploy, no shared cloud account
coupling, no Fly/AWS microVM agent under SaathiOS authority in this decision horizon.

---

## L. License analysis (MIT)

```text
MIT License — Copyright (c) 2026 QM contributors
```

### Implications

| Action | Obligation |
| --- | --- |
| Read / study public source | None beyond respecting terms of access |
| Copy substantial code into SaathiOS | Retain copyright notice + MIT text in copies / THIRD_PARTY_NOTICES |
| Link as dependency (`@yc-software/qm`) | Attribute; accept no-warranty; track supply chain |
| Reimplement patterns in original code | No copy of QM code → attribution not required for *ideas*; still document conceptual source in ADR (this package) |
| Sell / redistribute modified QM | Allowed under MIT with notice |

### This milestone

- **No QM source copied.**
- Conceptual reference documented (same posture as OpenJarvis / CLI-Anything in
  `THIRD_PARTY_NOTICES.md`).
- If a future milestone copies code, update `THIRD_PARTY_NOTICES.md` with commit pin
  and paths before merge.

---

# 2. Capability matrix

| Capability | QM | SaathiOS | Duplication | Adopt? |
| --- | --- | --- | --- | --- |
| Multi-agent / multi-role runs | Medium (multiplayer sessions) | Strong (M10 DAG) | Partial | Keep SaathiOS |
| Multi-harness coding CLIs | Strong | Weak/partial | Low | **Adapt interface** |
| Execution authority | Harness tools + command policy | ExecutionGateway | High conflict | **Keep SaathiOS** |
| Approvals | Posture + command gate | Fail-closed + leases | High | Keep SaathiOS; learn walls |
| Scopes / rooms | Strong | Medium | Medium | Adapt floors only |
| Sandbox durable computer | Strong | Medium (harness/sandbox) | Medium | Adapt carefully |
| Memory hierarchy | Scope notebooks | Hierarchical + promotion | High | Keep + refine hierarchy |
| Skills / packs | Strong | Medium | Medium | Adapt promotion lifecycle |
| Cron / watches | Strong | Medium | Medium | Governed adapt later |
| Browser automation | Present, weaker gates | GovernedBrowser | Medium | Keep SaathiOS gates |
| Credentials | Keychain + materialize | Handles + leases | High | Keep SaathiOS |
| Slack multiplayer | Strong | Optional connectors | High product | **Reject as core** |
| Local-first 8 GB | Secondary | Primary | — | Keep SaathiOS |
| Trading Guardian | Absent | Present | — | **Never QM** |
| Red-team harness | Not equivalent | M15.2 | — | Keep SaathiOS |
| Kill switch | Incomplete | Matrix | — | Keep SaathiOS |
| Certification | Deploy doctor | Package/production cert | Medium | Keep SaathiOS |

---

# 3. Gap analysis (SaathiOS relative to QM product features)

| Gap | Severity for SaathiOS goals | Action |
| --- | --- | --- |
| No unified multi-harness coding CLI surface | Medium | Design AgentHarness later |
| No Slack multiplayer rooms as first-class OS | Low (by design) | Do not fill via QM |
| No org skill-pack marketplace | Low–Medium | Safer promotion lifecycle later |
| Durable per-user cloud computer | Low (local-first) | Optional future; not QM |
| Security classifier for external content | Medium | Could add **behind** gateway as advisory screen only |
| Multi-instance Postgres queue | Low for solo | Not priority |

---

# 4. Duplication analysis

Introducing QM core would create **parallel systems** for:

1. Orchestration / turn loop
2. Session store
3. Approval path
4. Credential store
5. Memory
6. Skills
7. Cron
8. Audit
9. Sandbox execution
10. Model routing

Agents.md forbids building duplicate orchestration, memory, approval, execution systems.
**Therefore full alignment is architecturally non-compliant** with SaathiOS mission rules.

---

# 5–9. Focused comparisons

See sections **I** (security), **J** (governance), **E** (sandbox), **F** (memory),
**D** (harness proposal) above. They are the authoritative write-ups for deliverables
5–9.

---

# 10. Recommended future architecture (SaathiOS-native)

```text
┌─────────────────────────────────────────────────────────────┐
│ Surfaces: local UI · CLI · chat · (optional future collab)   │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Agent Runtime (existing) + optional AgentHarness adapters    │
│  start_session / submit_turn / stream / cancel / checkpoint  │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Policy floors (org/solo) — only-tighten scopes               │
│ Risk L0–L4 · standing approvals · budgets · kill switches    │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ ExecutionGateway (SOLE external-action authority)            │
│ ToolIntent immutable · credentials leased · evidence always  │
└──────────────┬──────────────────────────────┬───────────────┘
               ▼                              ▼
     Connectors / tools              Inference / models
     Computer / browser              Trading Guardian path
     Application harness             (advisory → bounded)
```

**Principles:**

1. One execution authority.
2. Harnesses are untrusted model drivers.
3. Scopes tighten, never loosen, policy floors.
4. Skills promote through certification.
5. Local-first default; cloud optional and gated.
6. Trading Guardian inviolable.

---

# 11. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | Vendor QM as runtime → dual control planes | Med if pursued | Critical | Decision forbids; ADR |
| R2 | Copy harness adapters without gateway binding | Med | High | M385 design rule |
| R3 | Adopt dangerous/auto postures wholesale | Med | Critical | Strict-equivalent only |
| R4 | Browser-outside-gate pattern leaks in | Low–Med | High | Keep GovernedBrowser |
| R5 | Sandbox secret materialization | Med | High | Keep leases/handles |
| R6 | Slack multiplayer expands attack surface | Med if productized | High | Separate product ADR |
| R7 | License / attribution miss if code copied | Low | Med | THIRD_PARTY_NOTICES |
| R8 | Stale QM tip invalidates analysis | Med over time | Low | M388 re-eval optional |
| R9 | “Adapt patterns” becomes silent reimplementation of QM | Med | High | Milestone gates + no import |
| R10 | Trading path influenced by multiplayer agent norms | Low | Critical | TG freeze rules |

---

# 12. Architecture Decision Record

Formal ADR: [`docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md`](../adr/ADR-QM-MULTI-AGENT-RUNTIME.md).

**Recorded decision:** ADAPT_SELECTED_PATTERNS.

---

## Decision options considered

| Option | Why not (or yes) |
| --- | --- |
| REJECT_QM | Too absolute; valuable harness/scope/skill patterns discarded |
| USE_QM_AS_REFERENCE | True but incomplete — we also authorize *pattern adaptation* |
| **ADAPT_SELECTED_PATTERNS** | **Selected** — evidence supports selective learning without integration |
| ISOLATED_READ_ONLY_EVALUATION | This milestone *is* that evaluation; decision goes one step further for future design |
| LIMITED_PLUGIN_INTEGRATION | Rejected — couples stacks, credentials, deployment; high risk |
| FULL_ARCHITECTURAL_ALIGNMENT | Rejected — duplicates systems, weakens governance, violates local-first |

---

## Evidence index

| Artifact | Location / ref |
| --- | --- |
| QM tip | `0f0e0adccce2` @ github.com/yc-software/qm main |
| QM README architecture | public README (core, sandbox, Postgres, plugins) |
| QM SECURITY.md | full threat model + known limitations |
| QM LICENSE | MIT 2026 |
| QM harness interface | `src/harness/harness.ts` |
| QM harness router | `src/harness/harness-router.ts` |
| QM sandbox interface | `src/sandbox/sandbox.ts` |
| QM security posture | `src/security/security-posture.ts` |
| QM command policy | `src/policy/command-policy.ts` |
| QM types (scopes, sessions, grants) | `src/types.ts` |
| QM skills / cron / memory / runs dirs | `src/*` listings via GitHub API |
| SaathiOS ExecutionGateway ADR | `docs/adr/ADR-EXECUTIONGATEWAY-SPECIFICATION.md` |
| SaathiOS M28 gateway | `docs/M28_EXECUTION_GATEWAY.md` |
| SaathiOS agent runtime | `saathi/agent_runtime/*` |
| SaathiOS M10 audit | `docs/M10_AGENT_RUNTIME_AUDIT.md` |
| SaathiOS harness | `docs/M17_3_HARNESS_ARCHITECTURE.md` |
| SaathiOS sandbox harness | `docs/M30_SANDBOX_HARNESS.md` |
| SaathiOS approvals | `docs/M35_APPROVAL_AND_LEASES.md` |
| SaathiOS agent security | `docs/M15_2_AGENT_SECURITY_AUDIT.md` |
| SaathiOS memory audit | `docs/M2_MEMORY_AUDIT.md` |
| OpenJarvis external-ref precedent | `docs/adr/ADR-OPENJARVIS-LOCAL-RUNTIME.md`, THIRD_PARTY_NOTICES |
| SaathiOS baseline commit | `949afa68a4135aa94dbdaaf9aecfd618e0948c09` |

---

## Integrity verification (post-analysis)

Expected: documentation-only changes under `docs/`.
No changes under `saathi/`, `saathi-os/`, `tests/`, CI, credentials, or deploy configs.

---

## Final report (Agents.md format)

1. **Overall result:** M377–M384 analysis complete; decision ADAPT_SELECTED_PATTERNS.
2. **Milestone completed:** QM multi-agent runtime architecture gap analysis (analysis-only).
3. **Git state:** started at `949afa68…`; docs added (ADR + evidence package).
4. **Files changed:**
   - `docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md`
   - `docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md`
   - (optional roadmap note if appended)
5. **Architecture reused:** Existing SaathiOS authorities preserved; QM not integrated.
6. **Tests/checks:** No code changes → no runtime test suite required; analysis integrity =
   public QM tip pin + local path evidence.
7. **Unresolved blockers:** None for analysis. Implementation of patterns blocked on
   future design milestones + human authorization.
8. **Documentation updated:** ADR + evidence package.
9. **Deployment / push / production:** **None.** No push, no deploy, no cloud resources.
