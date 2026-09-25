# Agent Registry

**Milestone:** M345 · **Declaration:** `saathi/agentdev/data/roles.json` ·
**Validator:** `saathi/agentdev/roles.py` · **Tests:** `tests/test_m345_agentdev_role_registry.py`

Roles are declared as data and validated at load time. `load_registry()` either
returns a fully valid registry or raises `RoleValidationError` with a stable
code — it never returns a partially validated one.

## The fourteen roles

| Agent ID | Role | Max authority | Worktree | Writes code | Approves gates | Escalates to | Reviewed by |
|---|---|---|---|---|---|---|---|
| `ceo` | CEO Agent | L2 | readonly | no | yes | owner | program-manager, security-governance |
| `program-manager` | Program Manager Agent | L2 | readonly | no | yes | ceo | ceo, architecture |
| `product-strategy` | Product Strategy Agent | L2 | readonly | no | no | program-manager | ceo, program-manager |
| `research` | Research Agent | L2 | readonly | no | no | program-manager | architecture, security-governance |
| `architecture` | System Architecture Agent | L2 | readonly | no | yes | program-manager | security-governance, testing-verification |
| `security-governance` | Security and Governance Agent | L2 | readonly | no | yes | **owner** | architecture, code-review |
| `ux-product-design` | UX and Product Design Agent | L2 | readonly | no | no | program-manager | architecture, code-review |
| `backend-engineering` | Backend Engineering Agent | L3 | **writable** | **yes** | no | program-manager | code-review, testing-verification |
| `frontend-engineering` | Frontend Engineering Agent | L3 | **writable** | **yes** | no | program-manager | code-review, testing-verification |
| `ai-model-systems` | AI and Model Systems Agent | L3 | **writable** | **yes** | no | program-manager | architecture, testing-verification |
| `testing-verification` | Testing and Verification Agent | L3 | readonly | no | yes | program-manager | code-review, architecture |
| `code-review` | Code Review Agent | L2 | readonly | no | yes | program-manager | architecture, security-governance |
| `documentation` | Documentation Agent | L2 | readonly | no | no | program-manager | program-manager, code-review |
| `cost-resource` | Cost and Resource Agent | L2 | readonly | no | no | program-manager | program-manager, ceo |

Three roles may write code. Eleven may not, and the loader refuses a contract
that gives a non-implementation role a `worktree:` writable scope.

Six roles may approve gates. An agent may only approve the gate of an author
that has declared it as an independent reviewer, and never its own — see
[review-and-evidence.md](review-and-evidence.md).

## Contract fields

Every role declares all sixteen:

| Field | Meaning |
|---|---|
| `agent_id` | Stable kebab-case identifier; the registry key |
| `role_name` | Human-readable name |
| `mission` | One sentence: what this role is for |
| `responsibilities` | What it must do |
| `allowed_capabilities` | Drawn from a closed 20-verb vocabulary; anything else fails to load |
| `prohibited_actions` | Must include all twelve global prohibitions, plus role-specific ones |
| `readable_paths` | Path scopes it may read |
| `writable_paths` | Path scopes it may write; only `mission:` or `worktree:` |
| `required_inputs` | What must exist before it can start |
| `required_outputs` | What it must produce |
| `escalation_to` | Another role, or `owner` |
| `independent_review_by` | Roles that may review its output; never itself |
| `max_authority` | A `saathi.safety.SafetyLevel` — no parallel enum exists |
| `approval` | A `saathi.safety.Approval` |
| `completion_criteria` | How "done" is judged |
| `default_worktree_mode` | `none`, `readonly` or `writable` |

## Path scope grammar

Scopes are prefixed so a contract can be validated without touching the disk:

| Prefix | Resolves to | Writable? |
|---|---|---|
| `repo:` | repository-relative path | Never |
| `mission:` | this mission's artifact directory | Yes |
| `worktree:` | the worktree assigned to this agent for this mission | Yes, implementation roles only |
| `reference:` | a named external read-only reference (e.g. `reference:ecc`) | Never |

Absolute paths and `~` are rejected at load time. There is no scope that can
address `~/.claude`, `~/.config`, a shell rc file or a credential store — those
are additionally blocked by [config protection](security-boundaries.md).

## Capability vocabulary

```
read_repository        read_external_reference   write_artifact
create_proposal        create_challenge          respond_to_challenge
chair_meeting          participate_meeting       decompose_mission
assign_task            request_worktree          write_code
run_tests              review_code               review_security
security_veto          approve_gate              synthesize_decision
estimate_cost          author_documentation
```

## Global prohibitions

Every role must prohibit all twelve. Omission is a load-time failure, so a role
cannot be quietly widened by leaving one out:

```
push                    merge                   deploy
force_push              delete_branch           git_reset_hard
git_clean               force_worktree_removal  modify_global_config
access_credentials      execute_trade           approve_own_work
```

## Enforcement tiers for this component

| Rule | Tier |
|---|---|
| Unknown capability, malformed id, absolute path scope, missing prohibition | **Schema validated** — `RoleValidationError` at load |
| Self-review, undeclared reviewer, reviewer without `approve_gate` | **Orchestration checked** — `can_review()` returns `False` and the gate refuses |
| Non-implementation role holding a writable worktree scope | **Schema validated** |
| An agent actually writing outside its worktree at runtime | **Detected, not prevented** — see [limitations.md](limitations.md) |

The last row is the honest one: the registry constrains what an agent is
*granted*, and the worktree manager constrains where a worktree *is*. Neither
can stop a model that is handed an unrestricted shell — which is why
`agentdev` never hands one out, and why `behavior_evals` tests for the
violation.

## Changing a role

1. Edit `saathi/agentdev/data/roles.json`.
2. Run `python -m pytest tests/test_m345_agentdev_role_registry.py`.
3. If the change widens authority, record why in `docs/DECISIONS.md`.

The registry is data, so a role change is reviewable as a diff rather than as
code.
