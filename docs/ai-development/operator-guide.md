# Operator Guide

**Milestones:** M350, extended in M352–M359 · **Entry point:** `python -m saathi.agentdev`

Read-only by default. Every state-changing command accepts `--dry-run`. Nothing
here can push, merge, deploy, use a credential or trade — those verbs do not
exist in the module.

## The one-screen tour

```bash
python -m saathi.agentdev doctor              # is the environment healthy?
python -m saathi.agentdev console show        # fifteen panels, read-only
python -m saathi.agentdev runner run          # 30-step deterministic mission
python -m saathi.agentdev review packet <id>  # everything the owner needs
```

Nine command groups exist. `doctor`, `agent`, `mission`, `worktree`, `meeting`,
`gate`, `config`, `verify` and `simulate` came from M344–M351;
`terminology`, `console`, `runner`, `model`, `eval`, `adversarial` and the
`review` sub-commands were added in M352–M359.

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

## Added in M352–M359

```bash
# Terminology (M352) — is the reviewed surface clean?
python -m saathi.agentdev terminology audit
python -m saathi.agentdev terminology classify autonomy
python -m saathi.agentdev terminology lexicon

# Operations console (M353) — read-only, fifteen panels, no polling
python -m saathi.agentdev console show
python -m saathi.agentdev console state
python -m saathi.agentdev console render --output /tmp/console.html

# Deterministic runner (M354) — no model, no prompts
python -m saathi.agentdev runner plan
python -m saathi.agentdev runner run --dry-run
python -m saathi.agentdev runner run

# Local model adapter (M355) — loopback only
python -m saathi.agentdev model capabilities
python -m saathi.agentdev model health
python -m saathi.agentdev model verify

# Behaviour evaluation (M356) — one model in one seat
python -m saathi.agentdev eval rubric
python -m saathi.agentdev eval run          # ~120 s
python -m saathi.agentdev eval mission      # ~15 s

# Adversarial evaluation (M357) — nine attacks
python -m saathi.agentdev adversarial list
python -m saathi.agentdev adversarial run   # ~125 s

# Owner review (M358) — four actions, owner only
python -m saathi.agentdev review packet <dev_mission_id>
python -m saathi.agentdev review render <dev_mission_id> --output /tmp/review.html
python -m saathi.agentdev review approve <id> --actor owner --rationale "..." \
  --acknowledge-risk "<risk>"
python -m saathi.agentdev review reject <id> --actor owner --rationale "..."
python -m saathi.agentdev review request-changes <id> --actor owner --rationale "..."
python -m saathi.agentdev review needs-research <id> --actor owner --rationale "..."
python -m saathi.agentdev review ledger <id>     # exits 1 if the chain is broken
```

Only `owner` may run the four `review` decision commands. Any other `--actor`
is refused with `action_not_by_owner`.

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
| Passing the owner-approval gate | Only `owner` may, by construction. M358 gives the owner the means; it gives nobody else the same means |
| Pruning the 102 pre-existing stale worktrees | Not this milestone's authority |
| Changing protected configuration | Needs an owner-approved proposal |
| Pushing, merging, deploying | Out of scope entirely |
| Starting or stopping the Ollama daemon | The adapter reads it; it never manages it |
| Counting concurrent agents against the ceilings | Ceilings are declared and reported, not enforced |

## Where to read next

| Question | Document |
|---|---|
| What does a word mean here? | [terminology.md](terminology.md) |
| What is certified, and what is not? | [certification-guide.md](certification-guide.md) |
| What are the hard numbers? | [operating-limits.md](operating-limits.md) |
| Something broke — now what? | [recovery-guide.md](recovery-guide.md) |
| How was the model measured? | [model-evaluation.md](model-evaluation.md) |
| Did the system hold under attack? | [adversarial-evaluation.md](adversarial-evaluation.md) |
