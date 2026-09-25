# Authority Model

**Milestones:** M345, M349 · **Reuses:** `saathi/safety.py`, `saathi/engineering/settings.py`

## One authority vocabulary

`agentdev` defines **no** authority enum. Every role's `max_authority` is a
`saathi.safety.SafetyLevel` and every role's `approval` is a
`saathi.safety.Approval`. A test asserts that no enum in `saathi.agentdev.roles`
is a superset of `SafetyLevel` — duplicate-source-of-truth rule 1 from ADR-012.

| Level | Meaning | Used by |
|---|---|---|
| L0 | read-only | (no dev role; all roles write artifacts) |
| L1 | low-risk automation | — |
| L2 | local modification | 10 reasoning and review roles |
| L3 | external side effects | 4 roles that execute repository tooling (build/test) inside a worktree |
| L4 | financial / production / deployment | **refused** — `authority_above_ceiling` |
| L5 | destructive / irreversible | **refused** |

L3 is the ceiling. A contract declaring L4 or L5 fails to load.

## Where authority actually comes from

Authority is the intersection of four independent gates. A role needs **all
four**; widening any one alone changes nothing.

```
  role contract          settings flags         gate approval        owner
  (what the role         (what the              (whether the         (final
   may request)           environment            lifecycle            authority)
                          permits)               allows it)
        │                      │                      │                  │
        └──────────────────────┴───────┬──────────────┴──────────────────┘
                                       ▼
                              effective authority
```

Example — a backend agent writing code:

1. `backend-engineering` declares `write_code` and a `worktree:` scope. ✓
2. `SAATHI_AGENTDEV_ENABLED=1` **and** `SAATHI_AGENTDEV_WORKTREES=1` must both be set; both default false. ✓
3. The mission must have passed the implementation-readiness gate, approved by an agent that is not the author. ✓
4. The owner must have approved the mission's implementation handoff. ✓

Miss any one and the worktree is not created.

## Non-overridable denials

`AgentDevSettings` re-applies this block **after** environment loading and after
keyword overrides, so neither can flip it:

```
push_allowed                     merge_allowed
deploy_allowed                   force_push_allowed
branch_delete_allowed            destructive_git_allowed
force_worktree_removal_allowed   global_config_writes_allowed
credential_access_allowed        trading_allowed
external_paid_calls_allowed      unrestricted_shell_allowed
```

This mirrors `saathi/engineering/settings.py`, which does the same for
`merge_allowed`, `deploy_allowed`, `force_push_allowed`, `trading_allowed`,
`unrestricted_shell_allowed` and `unrestricted_mcp_allowed`. Two layers, same
rule: **the environment may enable convenience, never authority.**

## Escalation

| From | To |
|---|---|
| Any role except CEO and Security | `program-manager` |
| `program-manager` | `ceo` |
| `ceo` | `owner` |
| `security-governance` | `owner` — directly, bypassing the CEO |

Security escalates straight to the owner on purpose. A security veto that could
be resolved inside the agent hierarchy would be worth nothing.

## The security veto

`security-governance` is the only role holding `security_veto`, and the registry
refuses to load without a veto-holder. A veto:

- blocks mission advancement past the security gate;
- can only be withdrawn by its author, and only against evidence;
- cannot be overridden by the CEO — `override_security_veto` is in the CEO's own prohibited list;
- leaves the mission in `blocked` if unresolved at decision time, so the CEO's terminal verdict cannot be `APPROVED_FOR_IMPLEMENTATION`.

## No self-approval

`can_review(reviewer, author)` returns `False` when:

| Condition | Reason code |
|---|---|
| reviewer is the author | `self_review_forbidden` |
| reviewer is not in the author's `independent_review_by` | `reviewer_not_declared_for:<author>` |
| reviewer lacks `approve_gate` | `reviewer_cannot_approve:<reviewer>` |
| either id is unknown | `unknown_reviewer:` / `unknown_author:` |

Gates call this before recording any approval. This is **orchestration
checked**: the workflow refuses to advance. It is not a runtime sandbox.

## Owner authority

Four things no agent may do, at any authority level:

1. Declare owner approval on the owner's behalf (`declare_owner_approval` is prohibited for the CEO).
2. Push, merge or deploy.
3. Modify global configuration or access credentials.
4. Change Trading Guardian controls.

Trading Guardian is untouched by this milestone. `agentdev` imports nothing from
`saathi.platform.trading_guardian` and a test asserts the absence of that import.

## Enforcement tiers

| Control | Tier |
|---|---|
| Authority ceiling L3, closed capability vocabulary, sandbox-only writable scopes | **Schema validated** |
| Non-overridable denial block | **Technically enforced** — re-applied after every override |
| Worktree creation requires two env flags | **Technically enforced** — `PermissionError` |
| No self-approval, gate ordering, security veto | **Orchestration checked** |
| "An agent must not present inference as fact" | **Prompt guidance** — detectable only by behaviour evaluation |
