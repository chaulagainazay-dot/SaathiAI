# Operator Guide

**Milestone:** M350 · **Entry point:** `python -m saathi.agentdev`

Read-only by default. Every state-changing command accepts `--dry-run`. Nothing
here can push, merge, deploy, use a credential or trade — those verbs do not
exist in the module.

## First contact

```bash
python -m saathi.agentdev doctor
```

Reports settings, the twelve denials (all false), registry health, the live
worktree census and the mission count. Exit `0` if the registry loads, `1` if
it does not.

## Enabling anything

Both flags default false and must be set deliberately:

```bash
export SAATHI_AGENTDEV_ENABLED=1        # allows planning and mission work
export SAATHI_AGENTDEV_WORKTREES=1      # additionally allows worktree creation
```

Optional:

| Variable | Default | Effect |
|---|---|---|
| `SAATHI_AGENTDEV_STORE` | `<repo>/data/agentdev` | Where missions and artifacts live |
| `SAATHI_AGENTDEV_WORKTREE_PARENT` | `~/SaathiAI-agent-worktrees` | Where worktrees are created |
| `SAATHI_AGENTDEV_MAX_REASONING_AGENTS` | `2` | Host concurrency ceiling |
| `SAATHI_AGENTDEV_MAX_CODING_AGENTS` | `1` | Host concurrency ceiling |
| `SAATHI_AGENTDEV_MAX_TESTING_AGENTS` | `1` | Host concurrency ceiling |
| `SAATHI_AGENTDEV_MAX_LOCAL_MODELS` | `1` | Host concurrency ceiling |

Disabling is the default; unsetting is sufficient.

## Common tasks

```bash
# Who are the agents?
python -m saathi.agentdev agent list
python -m saathi.agentdev agent show security-governance

# Start a mission
python -m saathi.agentdev mission create \
  --title "Adopt evaluation coverage" \
  --objective "Decide whether SaathiOS should adopt it." \
  --sha "$(git rev-parse HEAD)" --dry-run

# Where is it, and what is blocking it?
python -m saathi.agentdev mission status <dev_mission_id>
python -m saathi.agentdev gate report <dev_mission_id>

# Would this advance succeed?
python -m saathi.agentdev mission advance <id> --state design \
  --actor program-manager --dry-run

# Would this gate pass? (writes nothing)
python -m saathi.agentdev gate evaluate <id> --gate research_completeness \
  --approver architecture --subject research --evidence <artifact_id>

# Worktrees
python -m saathi.agentdev worktree census
python -m saathi.agentdev worktree plan --agent-id backend-engineering \
  --mission-id dm001 --description eval-coverage
python -m saathi.agentdev worktree inspect dm001-backend-engineering
python -m saathi.agentdev worktree removal-plan dm001-backend-engineering

# Meetings
python -m saathi.agentdev meeting participants red_team_review
python -m saathi.agentdev meeting list <dev_mission_id>
python -m saathi.agentdev meeting status <dev_mission_id> <meeting_id>

# Is a path protected configuration?
python -m saathi.agentdev config check ~/.claude/settings.json
python -m saathi.agentdev config surface

# Consistency check over a whole mission
python -m saathi.agentdev verify <dev_mission_id>

# The offline demonstration
python -m saathi.agentdev simulate --dry-run
python -m saathi.agentdev simulate
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, or "allowed" |
| `1` | Ran, but the result is inconsistent or failed |
| `2` | Usage error, or a forbidden flag |
| `3` | Refused — a governance rule said no |
| `4` | Not found |

`3` is the interesting one: the command worked, and the answer is no. The
payload always names the refusal.

## Reading a refusal

Refusals are collected, not raised one at a time:

```json
{
  "allowed": false,
  "refusals": [
    "self_approval_forbidden",
    "gate_without_evidence"
  ]
}
```

Fix all of them, then re-run. Every code is documented in
[review-and-evidence.md](review-and-evidence.md) or
[mission-lifecycle.md](mission-lifecycle.md).

## What an operator still has to do by hand

| Task | Why it is not automated |
|---|---|
| Removing a worktree | The module emits the command; it never runs one |
| Passing the owner-approval gate | No agent may, by construction |
| Pruning the 102 pre-existing stale worktrees | Not this milestone's authority |
| Changing protected configuration | Needs an owner-approved proposal |
| Pushing, merging, deploying | Out of scope entirely |
