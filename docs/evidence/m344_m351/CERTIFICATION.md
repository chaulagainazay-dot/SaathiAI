# M344–M351 — Multi-Agent Development Environment Foundation

**Verdict:** `MULTI_AGENT_DEVELOPMENT_FOUNDATION_CERTIFIED_WITH_LIMITATIONS`

Machine-readable companion: [EVIDENCE.json](EVIDENCE.json)

---

## 1. Numbering

Specified as M328–M335. Both that range (production readiness, commit `6cdf726`)
and M336–M343 (private-alpha readiness, `d2961e0`) are already shipped and
recorded in `docs/AUTONOMOUS_ROADMAP.md`. Reusing those numbers would create two
milestones with the same identity — the duplicate-source-of-truth failure this
work exists to prevent. Renumbered to the next free block with owner approval.
Scope unchanged.

| Specified | Delivered |
|---|---|
| M328 Discovery and architecture decision | **M344** |
| M329 Agent registry and role contracts | **M345** |
| M330 Worktree isolation manager | **M346** |
| M331 Mission and artifact protocol | **M347** |
| M332 Meeting and debate workflow | **M348** |
| M333 Review, approval and verification gates | **M349** |
| M334 Agent environment control surface | **M350** |
| M335 End-to-end offline simulated mission | **M351** |

## 2. Repository state

| | |
|---|---|
| Repository | `/Users/macbookpro/SaathiAI` (main), worked in worktree `/Users/macbookpro/SaathiAI-agent-foundation` |
| Baseline | `improve/saathios-private-alpha-product-excellence` @ `53b9b20` |
| Branch | `milestone/m344-m351-multi-agent-development-foundation` |
| Commits | 8 |
| Worktrees created | 1 (the milestone worktree) |
| Pushes / merges / deploys | 0 |

Every pre-existing worktree was left untouched, including the 30 dirty lines in
`~/SaathiAI` and the 10 in `~/SaathiAI-full-e2e`.

## 3. Validation

| Suite | Result |
|---|---|
| `tests/test_m345…m351_agentdev_*.py` (7 files) | **343 passed** in 3.66 s |
| Existing engineering + agent regressions (5 files) | **144 passed** in 5.02 s |
| Existing safety / governance / approval / security / trading (`-k`) | **1090 passed** in 174.96 s |
| Behaviour scenario suite | **10 / 10** in ~8 ms |
| Simulated mission | completed, `APPROVED_WITH_LIMITATIONS` |

Negative-path coverage is deliberate and large: 18 parametrised registry
refusals, every forbidden git sequence, every forbidden CLI flag, every
protected configuration path, gate self-approval in both pass and fail
directions, gate skipping, veto blocking, unanswered-challenge finalisation,
and dirty-tree removal.

## 4. Architecture delivered

| Component | Module |
|---|---|
| Role registry, 14 declarative contracts | `saathi/agentdev/roles.py`, `data/roles.json` |
| Authority model | reuses `saathi/safety.py`; `settings.py` denial block |
| Mission lifecycle, 13 states, 11 gates | `saathi/agentdev/missions.py` |
| Artifact protocol, 16 kinds | `saathi/agentdev/artifacts.py` |
| Worktree isolation | `saathi/agentdev/worktrees.py` |
| Meetings, 5 types, 6 phases | `saathi/agentdev/meetings.py` |
| Review gates, no self-approval | `saathi/agentdev/gates.py` |
| Configuration protection | `saathi/agentdev/config_protection.py` |
| Behaviour evaluation foundation | `saathi/agentdev/behavior_evals.py` |
| Simulated mission | `saathi/agentdev/simulation.py` |
| Control surface | `saathi/agentdev/cli.py` |

## 5. Existing systems reused

| SaathiOS system | Location | How it was reused |
|---|---|---|
| Runtime governance engine | `saathi/safety.py` | `SafetyLevel` and `Approval` are the only authority vocabulary; a test asserts no parallel enum exists |
| Governed engineering orchestrator | `saathi/engineering/` | Left unmodified. `agentdev` sits above it with a one-way dependency; its bound-approval shape, hash-chained ledger and disabled-by-default settings pattern are the models followed |
| Durable store primitives | `saathi/engineering/store.py` | Atomic `.tmp` → `os.replace` writes with `.bak` retention, copied into all three `agentdev` stores |
| Milestone evidence convention | `docs/evidence/m<NNN>/` | This pack |
| Decision record convention | `docs/DECISIONS.md` | ADR-012 appended |
| Test convention | `tests/test_m<NNN>_*.py`, pytest `asyncio_mode=auto` | Seven new suites |
| CLI conventions | `saathi/platform/cli.py`, `saathi/engineering/cli.py` | argparse sub-parsers, JSON output, named exit codes |
| Python environment | `~/SaathiAI-full-e2e/.venv` | Reused rather than duplicated — no second dependency install |

## 6. New systems created

Each with the reason no existing component covers it:

| New | Why |
|---|---|
| `roles.py` | `AgentContract` describes runtime product agents. It has no repository path scope, no prohibited actions, no independent reviewer, no escalation target, no completion criteria. Adding six development-only fields would couple two unrelated lifecycles. |
| `worktrees.py` | No registry, mission binding, collision check or dirty-tree refusal existed anywhere. The ad-hoc M233 helper leaked 102 prunable worktrees. |
| `artifacts.py` | The universal `Evidence` schema is a metrics record for product episodes and is documented as stable. Proposals, challenges, minutes and decisions are deliberation documents with claims, counterarguments and unresolved questions. |
| `missions.py` | A development mission has different participants, artifacts and terminal states than a product mission; sharing a store would make "mission" ambiguous. |
| `meetings.py` | Nothing modelled multi-participant deliberation with preserved disagreement. |
| `gates.py` | `engineering/approval.py` binds an operator approval to a launch. It does not model "B must review A's output, and A may never review its own." |
| `config_protection.py` | No module classified the user-level AI and shell configuration surface. |
| `behavior_evals.py` | 343 test files assert code behaviour; none assert agent behaviour, and none model an enforcement tier. |

## 7. ECC concepts adopted

**As principles only. No ECC runtime, hook, orchestration framework, dependency
or managed file was imported into SaathiOS. Zero ECC files exist in this
repository.** ECC remains a read-only reference at `~/dev-toolkits/ECC`.

| Principle | SaathiOS implementation |
|---|---|
| A finding must demonstrate a concrete failure mode | `gates.py` + high/critical claim fields, SaathiOS-authored |
| Configuration protection | `config_protection.py`, SaathiOS-authored, broader surface |
| Fact-forcing before action | Narrowed: an implementation handoff must name importers and data shapes |
| Agent-behaviour evaluation | `behavior_evals.py`, offline and deterministic |
| Declarative schema-validated agent definitions | `roles.py` + `data/roles.json`, hand-written validator, no new dependency |

Rejected explicitly: the installer and plugin system, all 21 hooks, the Memory
Vault, `SOUL.md`, `RULES.md`, ECC's `AGENTS.md`, the 281-skill catalog, the
35-server MCP catalog, `orch-*` / `multi-*` orchestration, `harness-audit`
scoring, and the 67-agent catalog.

## 8. Simulated mission

`dmevalcov1` — *Evaluate whether SaathiOS should adopt ECC-style
agent-behaviour evaluation coverage.*

All 12 steps ran with all 7 required agents. 24 artifacts across 12 kinds.
Three meetings: Research Review (decided), Architecture Council (decided),
Red-Team Review (**blocked**).

**Disagreement was preserved, not manufactured away.** The Testing agent's
objection — that ten scenarios bound ten refusals rather than the behaviour
space — went unanswered, so the red-team meeting finalised as `blocked`, the
disagreement landed on the mission, and the CEO's terminal verdict is
`APPROVED_WITH_LIMITATIONS` rather than a clean approval. The decision restates
that objection as an unresolved risk and refers the naming question to the
owner.

Every passed gate had a different approver from its subject author, with
evidence. The `owner_approval` gate remains **pending**, because no agent may
pass it. No production change was made.

## 9. Resource measurements

| Metric | Value |
|---|---|
| Behaviour suite | ~8 ms |
| Simulated mission | ~33 ms |
| Peak RSS (measured) | 21.2 MB |
| Model calls | 0 |
| Provider calls | 0 |
| External paid calls | 0 |
| Network calls | 0 |
| Worktrees created | 1 |
| Worktree disk | 127 MB |
| Second venv created | none — reused the existing interpreter |
| `~/SaathiAI-agent-worktrees/` | not created; no agent worktree was needed |

Not measured: long-run flakiness, live-provider cost. Both are recorded as
limitations rather than estimated.

## 10. Safety verification

| Check | Result |
|---|---|
| Trading Guardian modified | **No** — `agentdev` imports nothing from it |
| Credentials touched | **No** |
| Global configuration modified | **No** — `~/.claude` and `~/.config/opencode` are refused |
| ECC hooks enabled | **No** — no ECC file in this repository |
| MCP server created | **No** |
| Broker / live account / trade | **No** |
| Deploy / merge / push | **No** |
| Files deleted | **No** |
| Stale worktrees removed | **No** — 102 reported, all left in place |
| Denials forced false | 12, re-applied after every settings load |

## 11. Limitations

Full list in `docs/ai-development/limitations.md`. The four that matter most:

1. **No filesystem sandbox.** Nothing prevents a process from writing outside its worktree. What is guaranteed: `agentdev` never grants an unrestricted shell, no contract declares such a scope, and contamination is detected. Detection is not prevention, and BE-02 is tiered `schema_validated` accordingly.
2. **No model is in the loop.** Every agent in the simulation is a scripted caller of the real modules. The systems are proven; agent behaviour under a real model is not.
3. **Prompt-level expectations are guidance.** "Separate fact from inference" validates the *shape*; the honesty of the labelling is unverifiable here.
4. **Concurrency ceilings are declared, not enforced.** Nothing in this milestone spawns agents, so nothing enforces them yet.

## 12. Why "with limitations"

The foundation is implemented, validated and safe. The verdict is not a clean
certification because three claims cannot be made honestly yet: behaviour under
a real model is unproven, the enforcement boundary is partly evaluative rather
than technical, and the owner has not reviewed this evidence. Certifying past
any of those would be exactly the overstatement this milestone's own red-team
review rejected.

## 13. Recommended next milestone

**M352–M359 — Agent Operations Console and Controlled Provider Routing.**
Recommended, not started. It should begin only after the owner reviews this
evidence, and should resolve the open question the simulated mission referred
upward: whether the first suite may be called behaviour coverage before a model
participates.
