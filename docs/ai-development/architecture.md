# Multi-Agent Development Environment — Architecture

**Milestones:** M344–M351, extended by M352–M359
**Baseline:** `improve/saathios-private-alpha-product-excellence` @ `53b9b20`
**Branch:** `milestone/m344-m351-multi-agent-development-foundation`
**Status:** foundation; no production behaviour changed

> **M352–M359 update.** Sections 1–3 below describe the M344–M351 foundation
> and remain accurate. [Section 4](#4-m352m359-extension) records what the
> second block added, why each addition was necessary, and what it deliberately
> did not change.

> Numbering note. This work was specified as "M328–M335". Both M328–M335
> (production readiness) and M336–M343 (private-alpha readiness) are already
> implemented, committed and recorded in `docs/AUTONOMOUS_ROADMAP.md`. Reusing
> those numbers would create two milestones with the same identity — the exact
> duplicate-source-of-truth failure this milestone exists to prevent. The scope
> was therefore renumbered to the next free block, M344–M351, with owner
> approval. Scope is unchanged; only the labels moved.

---

## 1. Discovery map (M344)

Every claim below is a file that exists on the baseline commit. Nothing here is
inferred from documentation alone.

### 1.1 Governed engineering agent supervision — ALREADY EXISTS

`saathi/engineering/` (8,183 lines, 21 modules, milestones M20.0–M20.7) is a
complete supervision layer over coding-agent work. Its own docstring states it
"does **not** replace Mission Engine, ExecutionGateway, Approval Engine,
Knowledge Service, Run Ledger, Event Bus, Scheduler, Repair Loops, or Trading
Guardian."

| Concern | Module | What it already provides |
|---|---|---|
| Work-item model | `engineering/models.py` | `EngineeringBacklogItem`, `EngineeringTask`, 13 `ItemStatus` values, an explicit `ALLOWED_TRANSITIONS` table, `can_transition()`, `RECOVERABLE_FAILURES` / `NON_RECOVERABLE_FAILURES` |
| Persistence | `engineering/store.py` | File-backed store with `fcntl` locking, `.bak` corruption recovery, atomic `os.replace`, session leases, `append_history` |
| Approvals | `engineering/approval.py` | Bound approvals: repository, branch, starting commit, item, provider, **prompt fingerprint**, TTL, single-use `consumed` flag, 9 distinct mismatch reasons |
| Session ledger | `engineering/session_ledger.py` | Append-only hash-chained ledger with `verify_chain()` |
| Integrity evidence | `engineering/evidence.py`, `integrity.py` | Repository snapshot / `verify_unchanged` diffing |
| Settings | `engineering/settings.py` | Disabled-by-default flags; `merge_allowed`, `deploy_allowed`, `force_push_allowed`, `trading_allowed`, `unrestricted_shell_allowed`, `unrestricted_mcp_allowed` are **forced false after env load** and cannot be enabled by environment |
| Orchestration | `engineering/orchestrator.py` (759 lines) | Select → plan → launch → monitor → validate → stop |
| CLI | `engineering/cli.py` | 24 subcommands, JSON output, exit codes 0/1/2/3/4, explicit `forbidden_flag` rejection of `--unsafe`, `--skip-approval`, `--force-push`, `--deploy`, `--force`, `--merge`, `--write-anywhere` |
| Guardian isolation | `engineering/security.py` | `trading_guardian_isolation_report()`, `assert_no_trading_imports()` |

**Consequence:** a new orchestrator, a new approval type, a new session ledger
or a new work-item lifecycle would each be a duplicate source of truth. This
milestone builds none of them.

### 1.2 Runtime agent contracts — ALREADY EXISTS

`saathi/agent_registry.py` — `AgentContract(agent_id, department, purpose,
model_label, max_safety, memory_access, allowed_tools, approval)` plus
`AgentRegistry.register/get/instance/by_department`.

This describes **runtime product agents** (the ones that serve users at
request time), not development agents. It binds each agent to a Model Router
label and a Safety level. It has no concept of a repository path scope, a
worktree, a mission meeting or an independent reviewer, because runtime agents
do not need those.

### 1.3 Action governance — ALREADY EXISTS

`saathi/safety.py` — the Runtime Governance Engine. Deterministic, never an
LLM: `SafetyLevel` L0 (read-only) … L5 (destructive/irreversible), `Approval`
(`AUTOMATIC` / `HUMAN` / dual), and layers L1–L9 for classification, capability
validation, identity validation, resource guardrails, approval workflow, audit
logging and risk scoring.

### 1.4 Mission systems — ALREADY EXIST, PLURAL

- `saathi/missions/` (14 modules) — product missions: intake, store, workflow, timeline, proposal, overview.
- `saathi/mission_control.py`, `saathi/financial_mission_control.py`, `saathi/daily_mission.py`.
- `saathi/platform/mission_runtime/`.
- `saathi/application_harness/mission.py`.

These are **product** missions (a user's goal being executed by the OS). A
development mission ("evaluate whether SaathiOS should adopt X") is a different
noun with a different lifecycle, different participants and a different
terminal state.

### 1.5 Evidence — ALREADY EXISTS, TWO LAYERS

- `saathi/evidence/` — the universal SQLite Evidence schema, one shape for every department. Explicitly stable: "adapters absorb change, the schema does not."
- `docs/evidence/<milestone>/` — the repository-level certification evidence convention used by every milestone from M25 onward.

### 1.6 Worktree practice — PARTIAL, AD HOC

`saathi/platform/tg/integration_assurance/reproduction.py` creates detached
worktrees under `tempfile.mkdtemp(prefix="m233-worktree-")` for clean-clone
reproduction, and removes them with `git worktree remove --force`.

Live `git worktree list` on the baseline shows the cost of having no manager:
**over 100 stale `m233-worktree-*` entries marked `prunable`**, plus two
hand-made agent worktrees at `~/.worktrees/backend-core` and
`~/.worktrees/frontend-auth` on branches `agent/backend-core` and
`agent/frontend-auth` — a naming convention that exists in practice but is
enforced nowhere.

There is no worktree registry, no mission binding, no collision check, and no
refusal to remove a dirty tree. This is the clearest genuine gap.

### 1.7 CLI conventions — ESTABLISHED

Two shapes coexist:

- `python -m saathi.engineering <cmd>` — hand-rolled dispatch, `_emit()` JSON, module-docstring help, numeric exit codes.
- `python -m saathi.platform.cli <cmd>` — `argparse` sub-parsers, human-readable output, named exit-code constants, explicit refusal gates.

`pyproject.toml` `[project.scripts]` exposes only `saathi` and `saathi-listen`.
`bin/` holds `saathi-alpha` and `saathi-local`.

### 1.8 Test and certification conventions — ESTABLISHED

`tests/test_m<NNN>_<slug>.py`, 343 files, pytest with `asyncio_mode = "auto"`.
Milestone evidence lands in `docs/evidence/m<NNN>/`, roadmap entries in
`docs/AUTONOMOUS_ROADMAP.md`, decisions in `docs/DECISIONS.md`
(ADR-001 … ADR-011).

---

## 2. Gap analysis

| Capability the terminal objective requires | Exists? | Where |
|---|---|---|
| Bounded work items with a governed lifecycle | **Yes** | `engineering/models.py` |
| Bound, single-use, fingerprinted approvals | **Yes** | `engineering/approval.py` |
| Append-only tamper-evident audit | **Yes** | `engineering/session_ledger.py` |
| Disabled-by-default authority flags | **Yes** | `engineering/settings.py` |
| Repository integrity evidence | **Yes** | `engineering/integrity.py`, `evidence.py` |
| Deterministic action classification and approval | **Yes** | `saathi/safety.py` |
| Declarative agent contracts | **Partial** | `agent_registry.py` — runtime agents only; no path scope, no reviewer, no worktree |
| **Development-agent role contracts with path scopes and independent review** | **No** | — |
| **Managed, mission-bound worktree isolation** | **No** | ad-hoc temp worktrees only |
| **Structured multi-agent meetings with preserved disagreement** | **No** | — |
| **Durable inter-agent artifacts (proposal / challenge / minutes / decision)** | **No** | — |
| **Agent-behaviour regression evaluation** | **No** | 343 code test files, zero behaviour tests |

Six capabilities exist and will be extended. Five do not exist and are genuinely
new. Every new component below has a one-line justification for why no existing
component covers it.

---

## 3. Architecture decision

### 3.1 Placement

All new code lands in **`saathi/agentdev/`** — a new package, deliberately
separate from `saathi/engineering/`.

Rationale for a sibling package rather than extending `engineering/` in place:
`engineering/` governs *one coding agent executing one backlog item*. This
milestone governs *many reasoning agents deliberating over one mission and
optionally handing work to that coding agent*. Keeping them separate preserves
the existing module's certified surface (M20.0–M20.7 evidence).

**Actual runtime dependencies of `saathi/agentdev/`** — verified by reading
every import statement in the package:

```
saathi/agentdev/  ──imports──►  saathi.safety   (SafetyLevel, Approval)
                  ──imports──►  saathi.config   (ROOT)
                  ──imports──►  standard library only
```

That is the complete list. `agentdev` does **not** import
`saathi.engineering`, `saathi.missions`, `saathi.platform` or any product
module. What it takes from `saathi/engineering/` is *design contract*, not
code: the bound-approval field set, the append-only ledger shape, the atomic
`.tmp` → `os.replace` + `.bak` write pattern, and the
denials-re-applied-after-override settings rule are each re-implemented for the
different nouns this layer handles. Where a future milestone hands work to a
coding agent, it will call `EngineeringStore` directly rather than duplicating
its lifecycle.

The dependency direction is one-way and asserted by a test: nothing under
`saathi/engineering/`, `saathi/missions/` or `saathi/platform/` imports
`saathi.agentdev`. `engineering/` is not modified.

### 3.2 What is extended, not rebuilt

| New need | Reused SaathiOS component | How |
|---|---|---|
| Authority levels for dev-agent capabilities | `saathi.safety.SafetyLevel`, `Approval` | **Imported.** Each role's `max_authority` is a `SafetyLevel`; no parallel enum |
| Repository root | `saathi.config.ROOT` | **Imported.** |
| Approval semantics | `engineering.approval` binding fields | *Pattern only.* Gate records carry the same bound shape — subject, approver, evidence, decided-at — for a different subject |
| Tamper-evident history | `engineering.session_ledger.SessionLedger` | *Pattern only.* Mission `history` is append-only with the same event vocabulary |
| Disabled-by-default flags | `engineering.settings` | *Pattern only.* Same "env can enable convenience, never authority" rule, with its own twelve hard-false denials |
| Store durability | `engineering.store.EngineeringStore` | *Pattern only.* Atomic `.tmp` → `os.replace` with `.bak` retention, re-implemented for three stores |
| Evidence convention | `docs/evidence/m<NNN>/` | Mission evidence written to `docs/evidence/m344_m351/` |
| Decision record convention | `docs/DECISIONS.md` | New ADR-012 appended |
| Test convention | `tests/test_m<NNN>_*.py` | `tests/test_m344_m351_*.py` |

### 3.3 What is genuinely new, and why

| New component | Why nothing existing covers it |
|---|---|
| `agentdev/roles.py` — development-agent role contracts | `AgentContract` describes runtime agents. It has no readable/writable path scope, no `prohibited_actions`, no `independent_review_by`, no escalation target, no completion criteria. Adding six development-only fields to the runtime contract would couple two unrelated lifecycles. |
| `agentdev/worktrees.py` — mission-bound worktree manager | No registry, no branch-collision check, no dirty-tree refusal exists anywhere. The ad-hoc helper in `integration_assurance/reproduction.py` is single-purpose, uses `--force` removal, and has leaked 100+ prunable worktrees. |
| `agentdev/artifacts.py` — 16 artifact kinds | `Evidence` is a metrics/outcome record for product episodes. A proposal, a challenge, a set of meeting minutes and an executive decision are deliberation documents with claims, counterarguments and unresolved questions. They do not fit the stable Evidence schema, and that schema is documented as stable on purpose. |
| `agentdev/meetings.py` — structured meetings | Nothing in SaathiOS models multi-participant deliberation with preserved disagreement. |
| `agentdev/gates.py` — lifecycle gates with no self-approval | `engineering/approval.py` binds an operator approval to a launch. It does not model "agent B must review agent A's output, and A may never review its own." |
| `agentdev/behavior_evals.py` — behaviour evaluation | 343 test files assert code behaviour. None assert agent behaviour. |

### 3.4 Duplicate-source-of-truth prevention

Five explicit rules, each enforced by a test:

1. **One authority enum.** `agentdev` imports `SafetyLevel` and `Approval` from `saathi.safety`. A test asserts `agentdev` defines no enum whose members are a superset of `SafetyLevel`.
2. **One work-item lifecycle for code.** When a development mission produces an implementation handoff, it creates an `EngineeringBacklogItem` through `EngineeringStore` rather than tracking code work itself.
3. **One-way dependency.** A test asserts no module under `saathi/engineering/`, `saathi/missions/` or `saathi/platform/` imports `saathi.agentdev`.
4. **Distinct nouns.** A development mission is `dev_mission_id`, never `mission_id`, and lives in its own store. It is never written into `saathi/missions/store.py`.
5. **No new CLI framework.** `agentdev` extends the established `python -m saathi.<module>` convention with `argparse`, matching `saathi/platform/cli.py`.

### 3.5 ECC concepts adopted — as principles only

| ECC principle | How SaathiOS implements it | ECC code used |
|---|---|---|
| Review pre-report gate (cite the line, name the failure mode, read the context, defend the severity) | `agentdev/gates.py` rejects a `high`/`critical` finding lacking source location, failure mode, trigger condition, caller/data-flow evidence and severity rationale | None — SaathiOS-authored |
| Configuration protection | `agentdev/config_protection.py` refuses proposals touching `~/.claude`, `~/.config/opencode`, shell rc files, MCP config, credentials, global hooks | None — SaathiOS-authored |
| Fact-forcing before action (GateGuard's DENY → FORCE → ALLOW) | Adopted *narrowly*: an implementation handoff must name importers and data shapes before a writable worktree is granted | None — SaathiOS-authored |
| Agent-behaviour evaluation | `agentdev/behavior_evals.py` — offline, deterministic scenarios | None — SaathiOS-authored |
| Declarative, schema-validated agent definitions | `agentdev/roles.py` + `schemas/` | None — SaathiOS-authored |

**Rejected from ECC, explicitly:** the installer and plugin system, `hooks.json`
and all 21 hooks, the Memory Vault, `SOUL.md`, `RULES.md`, ECC's `AGENTS.md`,
the 281-skill catalog, the 35-server MCP catalog, the `orch-*` / `multi-*`
orchestration commands, `harness-audit` scoring, and the 67-agent catalog.

No ECC file, module, dependency or managed artifact is imported into SaathiOS.
ECC remains a read-only reference at `~/dev-toolkits/ECC`, outside this
repository.

### 3.6 Enforcement honesty

Controls are classified into four tiers throughout this milestone, and the
distinction is never blurred:

| Tier | Meaning | Example |
|---|---|---|
| **Technically enforced** | The code path cannot proceed; a `PermissionError` or non-zero exit is raised | Destructive git operations are absent from the command allowlist; `git worktree remove` on a dirty tree returns a refusal |
| **Schema validated** | Malformed input is rejected at construction | An agent role with a writable path outside its worktree fails validation |
| **Orchestration checked** | The workflow refuses to advance | A gate cannot be approved by its own author |
| **Prompt guidance** | Depends on agent compliance; detectable only by evaluation | "Separate fact from inference in research output" |

Nothing in this milestone technically prevents a model from writing outside its
worktree if it is handed an unrestricted shell. What is enforced is that
`agentdev` never hands one out, and that a violation is detected and recorded.

---

## 4. M352–M359 extension

Eight milestones, seven new modules, one new artifact kind, no change to any
module outside `saathi/agentdev/`.

### 4.1 What was added

| Module | Milestone | Why nothing existing covered it |
|---|---|---|
| `terminology.py` | M352 | The lexicon existed only as prose, and prose did not prevent the coverage overstatement the M351 mission itself flagged and referred to the owner. A typed lexicon plus a phrase guard makes drift loud |
| `console.py` | M353 | M344–M351 limitation 6 was "no UI, the CLI is the only interface". Fifteen panels assembled from stores, registry, live git and the host |
| `resources.py` | M353 | Ceilings were declared against an 8 GB host with nothing measuring that host. `resource`, `shutil` and `os.sysconf` were enough; no dependency was added |
| `runner.py` | M354 | `simulation.py` is *one* hard-coded mission. Nothing executed an arbitrary plan through a uniform contract with traces, timing, lineage and named failure causes |
| `model_adapter.py` | M355 | No component talked to a model at all. One place, loopback only, nine capabilities and seven structural denials |
| `model_eval.py` | M356 | 343 code test files, ten deterministic governance scenarios, and nothing that measured a real model against a published rubric |
| `adversarial.py` | M357 | Nothing asked what the system does when the model misbehaves — the question that decides whether governance is real |
| `review_console.py` | M358 | The `owner_approval` gate was owner-only from M349 with no means for the owner to exercise it, and no immutable record of owner decisions |

### 4.2 The dependency graph is unchanged

```
saathi/agentdev/  ──imports──►  saathi.safety   (SafetyLevel, Approval)
                  ──imports──►  saathi.config   (ROOT)
                  ──imports──►  standard library only
```

Verified at certification: `saathi/agentdev/` imports exactly `saathi.safety`,
`saathi.config` and itself, and **zero** modules under `saathi/engineering/`,
`saathi/missions/` or `saathi/platform/` import `saathi.agentdev`.

No package was installed. No virtual environment was created — the existing
`~/SaathiAI/.venv` is reused.

### 4.3 One extension to the closed vocabulary

`ArtifactKind.DOCUMENTATION_UPDATE` was added in M354, taking sixteen kinds to
seventeen. The Documentation Agent held `author_documentation` with no artifact
kind it could write; every other capability had one. The alternative — letting
documentation masquerade as `research_findings` — was worse.

### 4.4 The seam a model enters through

This is the load-bearing design decision of the second block.

```
PlanStep ──► HandlerContext(plan, step, inputs) ──► handler ──► body dict
                                                                  │
                     runner owns the envelope ────────────────────┘
                     (artifact_id, mission_id, kind, authoring_agent,
                      repository_sha, title, required_next_action, status)
```

A handler returns the artifact **body**. The envelope belongs to the runner, and
a handler returning any envelope field is refused by name at the `produce`
phase. `override_handler()` swaps one handler for a model-backed one.

The consequence, measured in M356 and M357: a model that failed six of eight
behaviour scenarios and complied with seven of nine attacks still could not
forge an author, approve a gate, skip a state or close a mission. It gains no
authority by being a model, because authority was never in the handler.

### 4.5 Enforcement honesty, extended

The four tiers from §3.6 gained a fifth for model-produced claims:

| Tier | Added in | Meaning |
|---|---|---|
| `model_evaluated` | M352 | A local model produced it and a documented rubric scored it. Establishes what one model did on one host at one moment — never a property of models |

`certification` was pinned as `documentation_only`, `autonomy` was rejected
outright, and `runtime` was reserved for the product runtime so the new
execution engine is called the *deterministic runner*. See
[terminology.md](terminology.md).

### 4.6 What M352–M359 deliberately did not do

- **No new orchestrator.** The runner drives the existing `GateEngine`, `DevMissionStore` and `ArtifactStore`; it does not re-implement any of them.
- **No second approval model.** M358 satisfies the M349 owner-only gate; it does not introduce a parallel approval concept.
- **No provider abstraction layer beyond one interface.** One adapter protocol, one implementation, one scripted stand-in for tests, no registry and no fallback.
- **No agent process supervisor.** Nothing spawns a process, so the concurrency ceilings remain declared rather than enforced — stated everywhere they appear.
- **No change to `saathi/engineering/`**, `saathi/missions/`, `saathi/platform/` or any product module.
