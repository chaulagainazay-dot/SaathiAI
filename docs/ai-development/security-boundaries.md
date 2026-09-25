# Security Boundaries

**Milestones:** M344–M351

## What this milestone did not do

Verified, not asserted. Each row has a check behind it.

| Never done | Evidence |
|---|---|
| Connect a provider credential | No credential is read; `.env` is untouched; `external_paid_calls_allowed` is forced false |
| Modify the Keychain | No Keychain API is called anywhere in `saathi/agentdev/` |
| Modify shell configuration | `.zshrc`, `.bashrc`, `.zprofile`, `.profile` are in the protected set and refused |
| Enable ECC hooks | No ECC file exists in this repository |
| Modify global Claude or OpenCode settings | `~/.claude` and `~/.config/opencode` are protected; `config check` refuses them |
| Create an MCP server | No MCP configuration is written; `.mcp.json` is protected |
| Connect a broker or account | No broker code is imported |
| Execute a trade | `trading_allowed` is forced false; nothing imports `saathi.platform.trading_guardian` |
| Deploy | `deploy_allowed` is forced false; no deploy verb exists |
| Merge or push | `merge_allowed`, `push_allowed`, `force_push_allowed` forced false; git verbs refused before `subprocess` |
| Delete a file | Nothing in the package deletes; the worktree manager exposes no removal method |
| Clean a user cache | No cache path is written or removed |
| Remove an existing worktree | 102 stale worktrees were reported and left in place |

## Trading Guardian

**Unchanged.** `saathi/agentdev/` imports nothing from
`saathi.platform.trading_guardian`, `saathi.platform.tg` or
`saathi.platform.paper_trading`. All fifteen platform authority locks remain as
they were on the baseline commit; this milestone touches none of them.

## The denial block

Twelve flags in `AgentDevSettings` are re-applied **after** environment loading
and **after** keyword overrides, so neither can flip one:

```
push_allowed                     merge_allowed
deploy_allowed                   force_push_allowed
branch_delete_allowed            destructive_git_allowed
force_worktree_removal_allowed   global_config_writes_allowed
credential_access_allowed        trading_allowed
external_paid_calls_allowed      unrestricted_shell_allowed
```

This mirrors `saathi/engineering/settings.py`, which does the same for its own
six. Two layers, one rule: **the environment may enable convenience, never
authority.**

## The git allowlist

`saathi/agentdev/worktrees.py` refuses these before `subprocess` is reached:

```
reset --hard      clean [-fd|-fdx]        push (any form)
merge             rebase                  branch -d / -D / --delete
checkout --force  worktree remove --force worktree prune
any argv containing --force, -f, --hard or --force-with-lease
```

Permitted verbs: `rev-parse`, `rev-list`, `status`, `worktree`, `branch`,
`log`, `diff`, `show-ref`. Anything else raises `git_verb_not_allowed`.

## Protected configuration

See [review-and-evidence.md](review-and-evidence.md#configuration-protection)
for the full surface. Summary: user-level AI configuration
(`~/.claude`, `~/.config/opencode`, `~/.codex`, `~/.cursor`, `~/.gemini`),
shell startup files, MCP configuration, and credential stores
(`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`, `~/.npmrc`).

Paths are expanded before classification, so `~`, `$HOME` and the absolute form
all resolve to the same verdict. A change requires inventory, backup plan,
change diff, rollback plan, and an owner approval an agent cannot grant.

## Owner authority

Four things no agent may do at any authority level:

1. Declare owner approval — `declare_owner_approval` is in the CEO's prohibited list, and the `owner_approval` gate refuses any approver other than `owner`.
2. Push, merge or deploy.
3. Modify global configuration or read credentials.
4. Change Trading Guardian controls.

## Authority ceiling

`SafetyLevel.L3` is the maximum any role may declare. A contract at L4
(financial / production / deployment) or L5 (destructive / irreversible) fails
to load with `authority_above_ceiling`.

## What is *not* guaranteed

Stated plainly, because overstating this would be the milestone's own worst
failure:

- Nothing here sandboxes a filesystem. A process handed an unrestricted shell can write anywhere the operating-system user can. What is guaranteed is that `agentdev` never hands one out, that no role contract grants such a scope, and that the resulting contamination is detected and recorded.
- Nothing here constrains a model's reasoning. Prompt-level expectations ("separate fact from inference", "do not present inference as fact") are guidance, detectable by evaluation, not enforcement.
- The behaviour suite proves ten specific refusals hold. It does not bound the behaviour space, and the simulated mission preserves exactly that objection as an unresolved risk.
