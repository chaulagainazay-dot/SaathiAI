# Recovery Guide

**Milestones:** M346, M347 · Nothing in this guide deletes anything.

## Principle

Every recovery path here is **inspect → plan → operator decides**. The modules
report; they do not clean up. That is deliberate: an automated cleanup that
guesses wrong destroys the only record of what an agent produced.

## A mission is stuck

```bash
python -m saathi.agentdev mission status <dev_mission_id>
```

Read `unmet_exit_gates`, `open_vetoes` and `next_states`.

| Symptom | Cause | Recovery |
|---|---|---|
| `unmet_exit_gates` non-empty | A gate has not passed | Produce the evidence, then have a declared reviewer pass the gate |
| `open_vetoes` non-empty | Security veto stands | Only `security-governance` may withdraw it, and only with evidence |
| `can_advance` false with neither | Requested state is not in `next_states` | Check the transition table in [mission-lifecycle.md](mission-lifecycle.md) |
| Mission must stop | — | Advance to `blocked`; it is reachable from every state |

`blocked` is always reachable, and returns to `research`, `design`,
`security_review`, `in_implementation`, `verification` or `executive_decision`.
A mission is never trapped by its own gates.

## A mission cannot close

`close_without_terminal_verdict` means the CEO has not set a verdict. Only the
CEO may, and `APPROVED_FOR_IMPLEMENTATION` is refused while any veto or
unresolved disagreement stands. Either resolve them with evidence, or choose
`APPROVED_WITH_LIMITATIONS`, `RESEARCH_REQUIRED`, `REWORK_REQUIRED`,
`REJECTED` or `OWNER_DECISION_REQUIRED`.

## A worktree is stranded

```bash
python -m saathi.agentdev worktree inspect <name>
python -m saathi.agentdev worktree removal-plan <name>
```

| `contamination` entry | Meaning | Recovery |
|---|---|---|
| `worktree_missing_on_disk` | Registry knows it, the filesystem does not | Confirm it is gone from `git worktree list`, then `mark_removed` |
| `branch_drift:expected=…:actual=…` | Someone checked out a different branch | Return to the recorded branch before continuing |
| `branch_outside_agent_namespace:<b>` | The checkout left `agent/…` entirely | Same |
| `agent_drift` / `mission_drift` | The branch belongs to another agent or mission | Do not reuse; plan a fresh worktree |
| `branch_shared_with:<name>` | Two registry records point at one branch | Investigate before removing either |

`removal-plan` refuses while uncommitted changes, untracked files,
contamination or unmerged commits exist, and prints the reasons. When clean, it
prints a **non-forcing** command:

```bash
git -C <repo> worktree remove <path>
```

Then record it:

```python
from saathi.agentdev.worktrees import WorktreeManager
WorktreeManager().mark_removed("<name>")
```

`mark_removed` refuses unless the worktree is gone from both the filesystem and
`git worktree list`, so the registry cannot drift out of sync optimistically.

**The branch is never deleted.** An unmerged implementation candidate is still
evidence. `git branch -d` and `-D` are both refused by the module.

## Stale worktrees from other milestones

```bash
python -m saathi.agentdev worktree census
```

On the baseline commit this reports 102 `prunable` entries left by the M233
reproduction helper. They are **reported and left in place** — pruning them is
an operator decision, not this milestone's authority. If you choose to:

```bash
git -C ~/SaathiAI worktree prune --dry-run   # inspect first
```

Run it yourself. The module will not.

## Store corruption

Every store writes atomically (`.tmp` → `os.replace`) and keeps a `.bak` of the
previous version, following `saathi/engineering/store.py`.

| File | Recovery |
|---|---|
| `<store>/<mission>/mission.json` | Restore from `mission.json.bak` |
| `<store>/<mission>/artifacts/<id>.json` | Restore from `<id>.json.bak` |
| `<store>/<mission>/meetings/<id>.json` | Restore from `<id>.json.bak` |
| `<store>/worktrees.json` | `registry_corrupt` is raised; restore from `worktrees.json.bak` |

A corrupt mission or artifact raises `mission_corrupt` / `artifact_corrupt`
naming the path rather than returning partial data.

## Verifying a mission end to end

```bash
python -m saathi.agentdev verify <dev_mission_id>
```

Reports `consistent` or `inconsistent` with a `problems` list:
`open_security_veto`, `closed_without_verdict`,
`gate_passed_without_evidence:<gate>`, `gate_self_approved:<gate>`.

The last one should be impossible — the gate engine refuses it at write time.
If `verify` ever reports it, the store was edited by hand, and that is the
finding.

## Starting clean

The store is disposable. Missions and artifacts live under
`SAATHI_AGENTDEV_STORE` (default `<repo>/data/agentdev`, gitignored). Point the
variable at a fresh directory to start over; nothing in the repository depends
on the store's contents.
