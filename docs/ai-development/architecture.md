# Multi-Agent Development Environment — Architecture

**Milestones:** M344–M351
**Baseline:** `improve/saathios-private-alpha-product-excellence` @ `53b9b20`
**Branch:** `milestone/m344-m351-multi-agent-development-foundation`
**Status:** foundation; no production behaviour changed

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
optionally handing work to that coding agent*. They compose vertically —
`agentdev` sits above `engineering` and calls into it — so keeping them
separate preserves the existing module's certified surface (M20.0–M20.7
evidence) while making the dependency direction explicit and one-way:

```
saathi/agentdev/   (new — deliberation, roles, worktrees, meetings, gates)
        │  depends on
        ▼
saathi/engineering/  (existing — approvals, ledger, settings, integrity)
        │  depends on
        ▼
saathi/safety.py     (existing — SafetyLevel, Approval)
```

`agentdev` never imports upward. `engineering/` is not modified.

### 3.2 What is extended, not rebuilt

| New need | Reused SaathiOS component | How |
|---|---|---|
| Authority levels for dev-agent capabilities | `saathi.safety.SafetyLevel`, `Approval` | Each role's `max_authority` is a `SafetyLevel`; no parallel enum |
| Approval semantics | `engineering.approval` binding fields | Gate records reuse the same bound shape: repository + branch + starting commit + subject + actor + TTL + single-use |
| Tamper-evident audit | `engineering.session_ledger.SessionLedger` | Mission events append to a ledger of the same hash-chained form |
| Disabled-by-default flags | `engineering.settings` pattern | `agentdev` settings follow the same "env can enable convenience, never authority" rule, with the same hard-false denials |
| Store durability | `engineering.store.EngineeringStore` locking / `.bak` / atomic write pattern | Mission artifact store uses the same primitives |
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
