# ECC Engineering Harness — SaathiOS Integration Policy

Status: active — hardened profile
Installed: 2026-08-29 · Hardened: 2026-08-29
ECC version: 2.2.0 **pinned** (`ecc@ecc`, project scope, **installed but disabled**)
Owner: SaathiOS engineering
Supersedes: nothing. Complements `AGENTS.md`.

---

## 1. What ECC is here

ECC is a **development-plane harness** for Claude Code. It supplies agents,
skills, commands, rules, and lifecycle hooks that help plan, build, test,
review, and document SaathiOS.

ECC is **not** part of SaathiOS. It ships no runtime code into the product, owns
no state the product reads, and holds no authority over anything the product
does.

```
DEVELOPMENT PLANE                     RUNTIME / AUTHORITY PLANE
-----------------                     -------------------------
Claude Code                           Research / Agents / Models
   |                                     |
ECC (this harness)                    PortfolioConstructionEngine  (proposal only)
   |                                     |
SaathiOS repository engineering       PortfolioRiskEngine          (deterministic)
   |                                     |
tests / reviews / security /          Trading Guardian             (deterministic veto)
certification                            |
                                      Approval                     (explicit, separate)
                                         |
                                      ExecutionGateway             (sole external boundary)
                                         |
                                      OMS / Broker Adapter
                                         |
                                      Canonical Fund Ledger        (authoritative state)
                                         |
                                      Reconciliation Authority     (fails closed)
```

**ECC never appears in the right-hand column.** No ECC agent, skill, command,
hook, rule, memory entry, or MCP server may sit anywhere in the runtime path.

---

## 2. Authority statement (binding)

ECC and every component it installs hold **none** of the following:

| Authority | ECC status |
|---|---|
| Trading authority | NONE |
| Risk override | NONE |
| Approval authority | NONE |
| Execution authority | NONE |
| Broker authority | NONE |
| Ledger mutation authority | NONE |
| Risk-budget mutation | NONE |
| Withdrawal authority | NONE |
| Leverage activation | NONE |
| Live-trading enablement | NONE |

An ECC agent that proposes a change to any of these surfaces is producing a
**suggestion for human review**, identical in standing to a code comment.

### Invariants ECC must never weaken

These are canonical SaathiOS invariants. They live in code and in the documents
referenced in §3; this list is a pointer, not a second source of truth.

1. `ExecutionGateway` is the sole external execution boundary.
2. Trading Guardian is the canonical deterministic allow/deny trading veto.
3. `PortfolioRiskEngine` is deterministic portfolio-risk authority.
4. `PortfolioConstructionEngine` is proposal-only, never executing.
5. Approval is explicit and separate from proposal generation.
6. The Canonical Fund Ledger is authoritative for ownership, cash, positions,
   lots, NAV, and accounting state.
7. Reconciliation fails closed when authoritative state is uncertain.
8. LLMs and development agents never hold direct broker or order authority.
9. No agent overrides deterministic risk.
10. Risk budgets change only through a dedicated deterministic configuration
    path with explicit authorization.
11. No withdrawal authority anywhere.
12. Leverage stays disabled until separately designed, reviewed, certified, and
    explicitly authorized.
13. No hidden live-trading enablement.
14. No broker credentials in repository files.
15. Existing approval, RBAC, audit, security, evidence, and certification
    systems remain intact.
16. ECC components are never financial authorities.

---

## 3. Canonical implementations (verify before changing)

| Authority | Canonical location on this branch |
|---|---|
| ExecutionGateway | `saathi/execution/gateway.py` (`ExecutionGateway`), `saathi/execution/` |
| Trading Guardian | `saathi/platform/trading_guardian.py`, `saathi/platform/tg/` (`service.py`, `domain.py` — policy, kill switch) |
| PortfolioRiskEngine | `saathi/portfolio.py` (`PortfolioRiskEngine`) |
| Paper ledger | `saathi/platform/tg/paper_simulation/ledger.py` |
| Reconciliation | `saathi/platform/paper_trading/reconciliation.py`, `saathi/platform/tg/market_data/reconciliation.py` |
| Execution gateway docs | `docs/M28_EXECUTION_GATEWAY.md` |
| Reconciliation semantics | `docs/M17_17_RECONCILIATION_SEMANTICS.md`, `docs/M38_RECOVERY_AND_RECONCILIATION.md` |
| Project authority docs | `AGENTS.md`, `docs/AUTONOMOUS_ROADMAP.md`, `docs/DECISIONS.md`, `docs/adr/` |

`PortfolioConstructionEngine` is **not present on this branch**; it lives in the
`feature/t-next-3-portfolio-construction` worktree. Check that worktree before
asserting anything about construction behaviour.

**Architecture documents and code win over ECC memory, ECC rules, and ECC
generic patterns, always.** If ECC guidance conflicts with a SaathiOS ADR, the
ADR is correct and the ECC guidance is discarded.

---

## 4. Operating rules for ECC agents in this repository

ECC agents are development agents only. Before changing any subsystem they must
identify, in writing:

1. the current canonical implementation;
2. the authority owner of that subsystem;
3. existing tests covering it;
4. relevant ADRs;
5. current milestone evidence;
6. regression risks.

Every proposed architectural change carries exactly one verdict:

`KEEP` · `ADAPT` · `INTEGRATE` · `REPLACE` · `COMBINE` · `DEFER` · `REJECT`

**"Newer" and "larger" are not arguments.** A proposal that reduces determinism,
auditability, or recoverability is rejected regardless of how modern it is.

Prefer: deterministic · auditable · modular · low-resource · secure · observable
· recoverable · testable · local-first where appropriate.

Avoid: unnecessary frameworks · duplicate registries · duplicate gateways ·
duplicate risk engines · duplicate ledgers · duplicate auth systems · hidden
network dependencies · uncontrolled background daemons · high-memory
infrastructure inappropriate for this machine.

---

## 5. Conflict resolution against SaathiOS's own development system

Resolved deterministically at install time. Do not re-litigate per session.

| Surface | SaathiOS | ECC | Verdict |
|---|---|---|---|
| Mission / milestone discipline | `AGENTS.md`, roadmap, milestone records | generic feature/task loop | **KEEP SAATHIOS** — canonical |
| Completion criteria | evidence artifacts under `docs/evidence/**` + certification | tests pass + coverage | **KEEP SAATHIOS** — ECC gates are advisory inputs |
| Certification pipeline | SaathiOS milestone certification | none equivalent | **KEEP SAATHIOS** |
| Authority boundaries / Trading Guardian | canonical | absent | **KEEP SAATHIOS** — ECC has nothing here |
| TDD workflow | ad hoc | `tdd-workflow` skill, `tdd-guide` agent | **COMBINE** — ECC drives the loop, SaathiOS defines done |
| Code review | generic | `code-review` skill, 13 language reviewers, `silent-failure-hunter` | **USE ECC** as an additional reviewer, never as sole authority |
| Security review | SaathiOS security audits + secret scan | `security-review`, `security-reviewer` | **COMBINE** — ECC is an extra pass, SaathiOS audits remain gating |
| Architecture review | ADRs | `architect`, `code-architect` | **COMBINE** — ADR is the record of record |
| Build-fix | manual | 11 build resolvers | **USE ECC** |
| Planning | `writing-plans` / milestone slices | `plan`, `planner` | **COMBINE** |
| Memory | `.saathi-agent-state/`, `HANDOFF.md`, repo docs | ECC memory vault | **KEEP SAATHIOS canonical**; ECC memory holds references only (§6) |
| Orchestration loops (`orch-*`, `multi-*`, `loop-*`) | SaathiOS mission + autonomous loop | ECC equivalents | **DEFER ECC** — would duplicate mission machinery |
| `harness-audit` scoring | — | self-authored rubric that recommends installing ECC | **REJECT** as a quality metric |
| Browser MCP | `Claude_Browser`, `claude-in-chrome` already available | ECC `chrome-devtools` MCP | **REMOVE DUPLICATE** — denied (§7) |
| Off-domain skill packs (healthcare, customs, energy, homelab, media, trading-adjacent ECC skills) | — | present in catalog | **DEFER** — not invoked; see §8 |

### Duplicate-hook resolution

Pre-existing hooks are user-owned and were not modified:

- `~/.claude/hooks/cbm-code-discovery-gate` — `PreToolUse` on `Grep|Glob`
- `~/.claude/hooks/cbm-session-reminder` — `SessionStart`
- `claude-mem@thedotmack`, `caveman@caveman` plugin hooks

ECC hooks match `Bash`, `Edit|Write|MultiEdit`, `Skill`, `*`, `Stop`,
`PreCompact`, `SessionEnd`. The only overlap is `SessionStart` context
injection, where three producers now run. Resolved by capping ECC's share:
`ECC_SESSION_START_MAX_CHARS=4000`. No hook was disabled to achieve this and no
hook was duplicated.

---

## 6. Memory and context design

Canonical facts live in this repository. ECC memory stores **references**, never
authoritative values.

- ECC runtime state is confined to `SaathiAI/.ecc-data/` via
  `ECC_AGENT_DATA_HOME`. It is gitignored and is not authoritative for anything.
- Nothing volatile goes into always-loaded context. The invariant list in §2 is
  short and stable by design; everything else is a pointer to §3.
- ECC rule packs live in `.claude/rules/ecc/`. **Correction from the initial
  install:** `.claude/rules/**` is auto-loaded, not referenced on demand. Files
  carrying a `paths:` frontmatter gate (all of `python/`, `typescript/`,
  `react/`) load only when matching files are in scope; `common/` has no gate and
  is always loaded. Only five `common/` files are kept — see §8.

If ECC memory ever disagrees with `AGENTS.md`, an ADR, or the code: the memory
entry is wrong. Delete it.

---

## 7. Security posture of this installation

| Item | Status |
|---|---|
| Install method | Official ECC plugin, once, project scope. The plugin is **installed but disabled**: it is the pinned, updatable vendor source and contributes zero context, zero hooks, and zero MCP servers. No second install method. |
| Component delivery | Curated subset synced from the pinned plugin cache into project-local `.claude/{skills,agents,commands,rules}` by `scripts/ecc_profile_sync.sh`, driven by `.claude/ecc-profile.json`. Synced content is gitignored vendor material; the manifest and script are the committed source of truth. |
| Install scope | `SaathiAI/.claude/` only. Global `~/.claude/settings.json` holds nothing but an inert `pluginConfigs.ecc@ecc` block. Other projects and the ~30 worktrees are unaffected. |
| Hooks | 5 entries wired explicitly, pinned to the vendor path. 19 hook ids disabled by id. See §7.1. |
| GateGuard | **Enabled and verified.** Denies the first `Edit`/`Write` per file until importers and data schemas are investigated, and denies destructive Bash. Fails closed. Escape hatch: `ECC_GATEGUARD=off`. |
| Config protection | **Enabled and verified.** Blocks weakening linter/formatter/test configs. |
| ECC `chrome-devtools` MCP | **ELIMINATED.** `disabledMcpServers` / `disabledMcpjsonServers` were both tested and do **not** gate plugin-provided MCP servers — the only reliable control is disabling the plugin, which is what this profile does. `claude mcp list` shows zero chrome-devtools entries and no process runs. `permissions.deny` rules are retained as defence in depth. |
| `@latest` executables | **None** launch automatically in the final configuration. The only auto-launched ECC code is Node running scripts from the pinned `2.2.0` vendor path. |
| Broker / trading / production credentials | None granted. No `.env`, no secret access, no credential path. |
| Network egress | None automatic. Marketplace updates only, and only when explicitly run. |
| Auto-update | Disabled. No `autoUpdate` on the `ecc` marketplace; ECC's own `auto-update` command is excluded from the profile. |
| Supply chain | Pinned to 2.2.0. `ecc security-ioc-scan` passes (211 files). Review `hooks/` and `scripts/hooks/` diffs on every update — the only surfaces that execute code. |
| Prompt injection | Reduced from 286 to 16 model-readable skills, all first-party engineering skills. Off-domain and community-origin catalogs are not installed. |
| Executable in synced content | One file: `.claude/skills/delivery-gate/hooks/quality-gate.py`. Not wired into any hook; inert unless a skill invokes it. |

### 7.1 Hook configuration

Wired (5 entries, pinned to `~/.claude/plugins/cache/ecc/ecc/2.2.0`):

| Event | Matcher | Hook | Why kept |
|---|---|---|---|
| PreToolUse | `Bash` | `pre-bash-dispatcher` | GateGuard destructive-Bash gate + `--no-verify` block |
| PreToolUse | `Edit\|Write\|MultiEdit` | `pre:config-protection` | Blocks weakening quality configs |
| PreToolUse | `Edit\|Write\|MultiEdit` | `pre:edit-write:gateguard-fact-force` | Fact-forcing gate before first edit of a file |
| SessionStart | `*` | `session-start-bootstrap` | Project-type detection + prior session context, capped at 4,000 chars |
| Stop | `*` | `stop:session-end` | Session state persistence (feeds SessionStart) |

Disabled by id (19): tmux automation and reminders, git-push and commit-quality nags,
doc-file warnings, compaction suggestions, continuous-learning observers (pre and post),
MCP health checks, console-log checks, format/typecheck at Stop, desktop notifications,
session evaluation, cost tracking, plan-canvas orchestration triggers, the PostToolUse
quality gate, and design-quality checks.

Rationale: keep every gate that can prevent a bad change; drop stylistic nags,
telemetry-shaped observers, orchestration triggers that duplicate SaathiOS mission
machinery, and anything that spawns background processes.

## 8. Resource posture

| Metric | Before hardening | After hardening |
|---|---|---|
| Always-on: component metadata | ~40,637 tok | **~3,580 tok** |
| Always-on: `rules/ecc/common` | ~6,458 tok (10 files) | **~3,956 tok (5 files)** |
| **Always-on total** | **~47,095 tok/session** | **~7,536 tok/session (-84.0%)** |
| Registered skills | 286 | 16 |
| Registered agents | 68 | 19 |
| Registered commands | 94 | 12 |
| Path-gated rules (load only on matching files) | ~15.7k tok | ~15.7k tok |
| PreToolUse processes per Edit | 6 | 2 |
| Edit-path hook latency | ~250 ms | ~95-140 ms |
| MCP servers added | 1 (`chrome-devtools`, unpinned) | 0 |
| Persistent background processes | 0 | 0 |
| Project-local disk | 128 KB | 736 KB |
| Vendor cache (pinned source) | 285 MB | 285 MB |

**Measurement method.** The component baseline came from `claude plugin details
ecc@ecc` (`Always-on: ~40,637 tok`). That command only reports enabled plugins, so
the post-hardening figure uses a calibration derived from the *same* corpus: always-on
component cost is the injected `name` + `description` frontmatter of every registered
skill, agent, and command. Summing that metadata across all 448 plugin components
gives 111,728 characters against the tool's 40,637 tokens — **2.749 chars/token**.
Per-type averages reconcile with the tool's own per-component table (skills 109 vs
108 tok, agents 82 vs 81, commands 43 vs 43). The same factor is applied to the 47
registered components and to always-loaded rule files.

**Correction to the initial install report.** That report stated rules were
"referenced on demand, not always-loaded". That was wrong. Verified in a fresh
session: `common/coding-style.md` content is present in the system context without
any tool call. Language packs are genuinely gated by their `paths:` frontmatter; the
ungated `common/` pack is not. The before-figure above therefore includes the 6,458
always-on tokens the first install was actually paying for rules.

**`common/` rule files dropped** (~2,500 always-on tokens, no gate lost):
`agents.md` and `hooks.md` describe an ECC component roster this profile does not
install, so they were stale and actively misleading; `git-workflow.md` conflicts with
SaathiOS git discipline in `AGENTS.md`; `performance.md` is Claude model-selection
advice; `patterns.md` is skeleton-project advice. Kept: `coding-style`, `testing`,
`security`, `code-review`, `development-workflow`.

Nothing was deleted from the vendor cache. Every other ECC component remains readable
there and can be added to `.claude/ecc-profile.json` and re-synced on demand.

## 9. SaathiOS + ECC development lifecycle

```
MISSION INTAKE
   -> DISCOVERY            (read-only intake audit; record starting commit)
   -> ARCHITECTURE CHECK   (canonical implementation, authority owner, ADRs)
   -> PLAN                 (ECC plan / planner; bounded slice)
   -> INVARIANT TESTS FIRST
   -> IMPLEMENT            (smallest complete change; reuse existing systems)
   -> FOCUSED TESTS
   -> FRESH-CONTEXT REVIEW (ECC code-review + language reviewer, clean context)
   -> SECURITY REVIEW      (ECC security-review + SaathiOS secret scan)
   -> FAILURE TESTING
   -> REGRESSION
   -> CERTIFICATION        (SaathiOS certification — canonical)
   -> EVIDENCE             (docs/evidence/**)
   -> COMMIT
   -> OPTIONAL PR          (only on explicit authorization)
```

### Additional gates for any trading-plane work

Every one of these is mandatory and each produces a written finding:

1. authority audit — did any authority move, widen, or get duplicated?
2. risk audit — is deterministic risk still deterministic and still first?
3. approval audit — is approval still explicit and still separate from proposal?
4. ExecutionGateway audit — is it still the sole external boundary?
5. ledger audit — is the canonical ledger still authoritative and append-correct?
6. reconciliation audit — does uncertain state still fail closed?
7. no-live-authority audit — no broker connectivity, no live enablement, no
   leverage, no withdrawal path introduced.

---

## 10. Readiness for T-NEXT-4

ECC is prepared to support **T-NEXT-4 — Canonical Trading Chain Integration &
Execution Integrity** as a development harness. Nothing in T-NEXT-4 is started,
designed, or implemented by this installation.

Planned sub-missions and the ECC surfaces prepared for each:

| Sub-mission | ECC support |
|---|---|
| T4.1 Canonical trading lineage convergence | `architect`, ADR skill, discovery agents |
| T4.2 Durable OMS state machine | `tdd-workflow`, `type-design-analyzer` |
| T4.3 Idempotent order submission | `tdd-workflow`, `code-review`, `silent-failure-hunter` |
| T4.4 Fill ingestion | `tdd-workflow`, `python-reviewer` |
| T4.5 ReconciliationAuthority | `architect`, invariant tests first |
| T4.6 Unknown-state recovery | `silent-failure-hunter`, failure-injection review |
| T4.7 Execution failure injection | `e2e-runner`, `test-coverage` |
| T4.8 Shadow execution adapter | `security-review`, authority audit (§9) |
| T4.9 End-to-end certification | SaathiOS certification, canonical; ECC advisory only |

Preconditions that remain in force throughout T-NEXT-4:

- no broker connectivity;
- no live trading;
- no change to financial authority boundaries;
- no auto-merge of trading PRs;
- every sub-mission passes all seven trading-plane gates in §9.

---

## 11. Updating ECC — never automatically

**Rule: ECC is never upgraded automatically.** The `ecc` marketplace has no
`autoUpdate`, ECC's own `auto-update` command is excluded from the profile, and the
vendor path in `.claude/settings.json` is pinned to an exact version directory.
A newer ECC cannot reach this repository without a person running the steps below.

For every ECC update, in order:

1. **Inspect the release/change diff.** `git -C ~/.claude/plugins/marketplaces/ecc log --oneline <old>..<new>` and read the CHANGELOG.
2. **Inspect hooks.** Diff `hooks/hooks.json` and `scripts/hooks/**`. These are the only surfaces that execute code on your machine. Any new blocking hook, any new spawned process, any new network call is a stop-and-review.
3. **Inspect MCP changes.** Diff `.mcp.json` and `mcp-configs/`. A new MCP server is a new network and credential surface; the default answer is no.
4. **Inspect scripts.** Diff `scripts/lib/**` — particularly `hook-flags.js` (the disable mechanism this profile depends on) and anything touching `ECC_AGENT_DATA_HOME`.
5. **Inspect permission changes.** Confirm nothing new requests credentials, shell authority, or writes outside `.ecc-data/`.
6. **Run the security scan.** `node <vendor>/scripts/ecc.js security-ioc-scan` must pass.
7. **Test in isolation.** Install the new version to a scratch directory or the sandbox at `~/dev-toolkits/ecc-workspace`, never straight into SaathiOS.
8. **Then upgrade the project integration:** `claude plugin update ecc@ecc`, re-disable the plugin, bump `eccVersion` and `vendorRoot` in `.claude/ecc-profile.json`, bump the pinned paths in `.claude/settings.json`, run `scripts/ecc_profile_sync.sh`, re-run the §5 conflict check, and re-measure always-on cost.

`scripts/ecc_profile_sync.sh --check` reports drift between the manifest and what is
on disk without changing anything.

---

## 12. Rollback

```bash
cd ~/SaathiAI
scripts/ecc_profile_sync.sh --clean          # remove synced skills/agents/commands/rules
rm -rf .ecc-data .claude/settings.json .claude/ecc-profile.json
rm -f  scripts/ecc_profile_sync.sh docs/engineering/ECC_INTEGRATION.md
git checkout -- .gitignore AGENTS.md
claude plugin uninstall ecc@ecc --scope project
claude plugin marketplace remove ecc --scope project
rm -rf ~/.claude/plugins/cache/ecc ~/.claude/plugins/marketplaces/ecc
```

To roll back only the hardening and return to the full plugin profile:

```bash
cd ~/SaathiAI
scripts/ecc_profile_sync.sh --clean
cp ~/.claude/backups/ecc-install-20260829/project.settings.json.pre-harden.bak .claude/settings.json
claude plugin enable ecc@ecc
```
(That restores ~47k always-on tokens and the unpinned chrome-devtools MCP.)

Pre-change backups: `~/.claude/backups/ecc-install-20260829/`
(global `settings.json`, `known_marketplaces.json`, `installed_plugins.json`,
project `settings.local.json`, `AGENTS.md`, pre-install git status and HEAD).

Global `~/.claude/settings.json` was never modified, so uninstalling ECC returns
every other project to its exact prior state with no action.
