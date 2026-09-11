# Worktree Isolation

**Milestone:** M346 · **Module:** `saathi/agentdev/worktrees.py` ·
**Tests:** `tests/test_m346_agentdev_worktree_isolation.py` (60)

## The problem this solves

Measured on the baseline commit, `git worktree list` reported **112 entries, of
which 102 were stale and `prunable`** — all `m233-worktree-*` directories left
behind by the ad-hoc helper in
`saathi/platform/tg/integration_assurance/reproduction.py`, which creates
worktrees in `tempfile.mkdtemp()` and removes them with
`git worktree remove --force`. Two further worktrees existed at
`~/.worktrees/backend-core` and `~/.worktrees/frontend-auth` on branches
`agent/backend-core` and `agent/frontend-auth`: an agent-worktree convention
that existed in practice with no registry, no mission binding and no collision
check behind it.

## Properties

| Property | How |
|---|---|
| One worktree ↔ one mission ↔ one agent | Registry key is `<mission-id>-<agent-id>`; a second worktree for the same pair is refused |
| Mandated branch naming | `agent/<agent-id>/<mission-id>-<description>`, built and parsed by regex |
| Starting SHA recorded | `WorktreeRecord.starting_sha`, written at creation, never rewritten |
| No two worktrees share a branch or a path | Checked against live `git worktree list`, `refs/heads/*`, **and** the registry |
| Cleanliness inspection | `git status --porcelain=v1`, split into dirty and untracked |
| Contamination detection | branch drift, agent drift, mission drift, branch outside the agent namespace, branch or path shared with another record |
| Safe removal | `removal_plan()` only; refuses on uncommitted, untracked, contaminated or unmerged state |
| No destructive verbs | Absent from the allowlist and refused in `_assert_git_allowed` |

## Branch convention

```
agent/<agent-id>/<mission-id>-<description>
      │           │            └── kebab-case
      │           └── dm + 2–24 alphanumerics, NO hyphen
      └── a declared role id
```

Mission ids carry no hyphen on purpose, so
`agent/backend-engineering/dm001-eval-coverage` decomposes back to exactly
`("backend-engineering", "dm001", "eval-coverage")` with no ambiguity.

Default parent directory: `~/SaathiAI-agent-worktrees/`, overridable with
`SAATHI_AGENTDEV_WORKTREE_PARENT`.

## Who gets a writable worktree

Only `backend-engineering`, `frontend-engineering` and `ai-model-systems` — the
three roles that declare `write_code`. Every other role defaults to `readonly`,
including Research, CEO, Program Manager, Security and Code Review, as required.

A writable worktree needs **all four** of:

1. a role declaring `write_code` and `default_worktree_mode: writable`;
2. `SAATHI_AGENTDEV_ENABLED=1`;
3. `SAATHI_AGENTDEV_WORKTREES=1`;
4. no refusal from the plan.

Flags 2 and 3 both default false.

## Forbidden git operations

`_assert_git_allowed()` runs before `subprocess`, so these never reach a shell —
this is **technically enforced**, not documented policy:

```
git reset --hard          git clean [-fd|-fdx]      git push [anything]
git merge                 git rebase                git branch -d / -D / --delete
git checkout --force      git worktree remove --force
git worktree prune        any argv containing --force, -f, --hard, --force-with-lease
```

Branch deletion is refused in both its lowercase and uppercase forms. An
unmerged implementation candidate is still evidence; deleting its branch
destroys the record of what an agent produced.

The verb allowlist is `rev-parse`, `rev-list`, `status`, `worktree`, `branch`,
`log`, `diff`, `show-ref`. Anything else raises `git_verb_not_allowed`.

## Planning is pure

`plan()` performs no writes and collects **every** refusal rather than raising
on the first, so an operator sees the whole picture in one pass:

```json
{
  "branch": "agent/backend-engineering/dm001-eval-coverage",
  "path": "/Users/…/SaathiAI-agent-worktrees/dm001-backend-engineering",
  "base_ref": "HEAD",
  "base_sha": "0af2f46…",
  "allowed": false,
  "refusals": ["agentdev_disabled", "worktree_creation_disabled"]
}
```

`create()` **re-plans** before acting: a plan computed minutes ago may have been
invalidated by another process, and a stale plan is never trusted. A test proves
this by claiming the branch between `plan()` and `create()`.

## Removal is a plan, never an action

`WorktreeManager` has **no** `remove()`, `delete()`, `prune()` or `destroy()`
method — a test asserts their absence. `removal_plan()` returns refusals and,
only when everything is clean, the exact non-forcing command an operator may
choose to run:

```
git -C <repo> worktree remove <path>
```

Refusal reasons: `uncommitted_changes:<n>_files`, `untracked_files:<n>_files`,
`contaminated:<reasons>`, `unmerged_commits:<n>`.

`mark_removed()` updates the registry *after the fact*, and refuses unless the
worktree is genuinely gone from both the filesystem and `git worktree list`, so
the registry cannot be desynchronised by an optimistic call.

## Stale worktrees are reported, never removed

`inspect_environment()` reports `prunable_stale_worktrees`,
`unregistered_agent_worktrees`, `registered_but_missing_on_disk` and
`duplicate_branch_checkouts`. It removes nothing. The 102 pre-existing stale
entries are surfaced for an operator decision; this milestone does not clean
them up, because deleting another milestone's leftovers is not this milestone's
authority.

## Enforcement tiers

| Control | Tier |
|---|---|
| Destructive git verbs and force flags | **Technically enforced** — refused before `subprocess` |
| Two env flags required to create | **Technically enforced** — `PermissionError` |
| Branch naming, mission-id shape | **Schema validated** — regex at construction |
| Branch/path/agent collision, one-worktree-per-agent-per-mission | **Orchestration checked** — plan refusals, re-checked at create |
| Dirty-tree removal refusal | **Orchestration checked** — the plan withholds the command |
| An agent writing outside its worktree | **Detected, not prevented** — contamination flags and `behavior_evals`; see [limitations.md](limitations.md) |
