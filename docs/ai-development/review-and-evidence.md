# Review, Evidence and Gates

**Milestone:** M349 · **Modules:** `saathi/agentdev/gates.py`,
`saathi/agentdev/config_protection.py` ·
**Tests:** `tests/test_m349_agentdev_gates_and_config_protection.py` (56)

## The rule everything else protects

> **No agent may approve its own output.**

Every other check in this module exists to stop that rule being evaded — by an
undeclared reviewer, by a gate passed with no evidence, by a "pass" recorded
over an unresolved critical finding, or by an agent claiming the owner's
approval on the owner's behalf.

`fail_gate()` is bound by the same rule: an agent cannot record a failure
against its own work either, because self-assessment in both directions is
still self-assessment.

## The eleven gates

| Gate | Required evidence kind | Who may pass it |
|---|---|---|
| `research_completeness` | `research_findings` | a declared reviewer of the author |
| `architecture_approval` | `architecture_decision` | a declared reviewer |
| `security_approval` | `security_review` | **security-governance only** |
| `implementation_readiness` | `implementation_handoff` | a declared reviewer |
| `code_review` | `code_review` | a declared reviewer |
| `automated_testing` | `verification_report` | a declared reviewer |
| `negative_path_testing` | `verification_report` with `negative_paths` | a declared reviewer |
| `red_team_review` | `meeting_minutes` | **security-governance only** |
| `executive_synthesis` | `executive_decision` | a declared reviewer of the CEO |
| `owner_approval` | `owner_approval` | **the owner only** |
| `integration_candidacy` | `final_synthesis` | a declared reviewer |

## Every refusal `evaluate()` can return

`evaluate()` performs no writes and collects **all** reasons, so an operator
sees the whole picture at once:

| Refusal | Meaning |
|---|---|
| `self_approval_forbidden` | Approver is the subject author |
| `reviewer_not_declared_for:<author>` | Not in the author's `independent_review_by` |
| `reviewer_cannot_approve:<id>` | Reviewer lacks `approve_gate` |
| `owner_only_gate:<gate>` | An agent tried to pass an owner gate |
| `owner_may_only_pass_owner_gates` | The owner tried to pass an agent gate |
| `security_gate_requires_security_role:<id>` | Security gate, non-security approver |
| `gate_without_evidence` | No evidence supplied |
| `evidence_not_found:<id>` | Evidence id does not exist in this mission |
| `evidence_wrong_kind:<id>:expected=…:actual=…` | Wrong artifact kind |
| `evidence_not_authored_by_subject:<id>` | The evidence is not the subject's work |
| `unresolved_critical_findings:<ids>` | A critical claim stands on a non-accepted artifact |
| `security_veto_open:<ids>` | A veto blocks everything but its own gate |
| `no_negative_path_results` | The report ran no negative paths |
| `verification_without_not_run_list:<id>` | Unrun checks were omitted rather than listed |

Unresolved disagreements produce a **warning**, not a refusal, at
`executive_synthesis` and `integration_candidacy` — they must be carried into
the decision visibly, not used to block it. The refusal happens one level up:
`APPROVED_FOR_IMPLEMENTATION` is refused by the mission store while any
disagreement is unresolved.

## The finding standard

SaathiOS-authored, informed by ECC's review discipline but written here:

> A finding is not accepted merely because it sounds plausible. It must
> demonstrate a concrete, relevant failure mode.

Any claim at `high` or `critical` severity must carry all five, or the artifact
does not validate:

| Field | Meaning |
|---|---|
| `source_location` | Exact file and line |
| `failure_mode` | What goes wrong, as an outcome |
| `trigger_condition` | The input or state that causes it |
| `caller_or_dataflow_evidence` | Who calls this, or where the data comes from |
| `severity_rationale` | Why this severity and not one lower |

`recommended_remediation` is expected but not blocking. `review_finding_requirements()`
publishes this as data so the CLI and docs cannot drift from the code.

## Claim epistemics

| Claim kind | Requirement |
|---|---|
| `fact` | An evidence reference. Refused without one. |
| `inference` | `rests_on` naming claim ids that exist in the same artifact. |
| `assumption` | `falsified_by` — what would show it wrong. |
| `INSUFFICIENT_EVIDENCE` | Always acceptable, needs none of the above. |

This is what makes "separate fact from inference" checkable rather than
aspirational.

## Configuration protection

Development agents must never quietly rewrite the machine they run on.

**Protected home prefixes:** `~/.claude`, `~/.config/claude`,
`~/.config/opencode`, `~/.opencode`, `~/.codex`, `~/.cursor`, `~/.gemini`,
`~/.aws`, `~/.ssh`, `~/.gnupg`, `~/.netrc`, `~/.docker/config.json`, `~/.kube`,
`~/.saathi`.

**Protected basenames:** `.zshrc`, `.zshenv`, `.zprofile`, `.bashrc`,
`.bash_profile`, `.profile`, `.zlogin`, `.netrc`, `.npmrc`, `.pypirc`, `.env`,
`.mcp.json`, `mcp.json`, `mcp-servers.json`, `settings.json`,
`settings.local.json`, `hooks.json`, `credentials`, `credentials.json`,
`id_rsa`, `id_ed25519`.

**Credential markers** anywhere in a path: `secret`, `credential`, `token`,
`apikey`, `api_key`, `keychain`.

Paths are expanded before classification, so `~/.claude/settings.json`,
`$HOME/.claude/settings.json` and the absolute form all land in the same place —
an agent cannot evade the check by choosing a different spelling. A test asserts
all three spellings.

A repository-local `.claude/settings.json` is **not** protected: that is
ordinary project configuration. Only the user-level copies are.

### Changing protected configuration

Requires a complete `ConfigChangeProposal`:

1. `inventory` — what exists now
2. `backup_plan` — how the current state is preserved
3. `change_diff` — exactly what changes
4. `rollback_plan` — how to undo it
5. `owner_approved` **by the owner** — `owner_approval_actor` must be `owner`

An agent can author the first four. The fifth it cannot grant, by construction:
a proposal approved by `ceo` is refused with
`owner_approval_not_by_owner:ceo`.

## Enforcement tiers

| Control | Tier |
|---|---|
| No self-approval, owner-only gates, security-owned gates | **Technically enforced** — `GateError` |
| Evidence existence, kind and authorship | **Technically enforced** |
| High/critical finding fields, claim epistemics | **Schema validated** |
| Protected-path classification and proposal completeness | **Technically enforced** — `ConfigProtectionError` |
| Unresolved-disagreement carry-through | **Orchestration checked** — warning here, refusal at the verdict |
| Whether a reviewer read the code before approving | **Prompt guidance** |
