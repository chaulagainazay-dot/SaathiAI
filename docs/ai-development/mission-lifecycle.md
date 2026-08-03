# Development Mission Lifecycle

**Milestone:** M347 · **Module:** `saathi/agentdev/missions.py` ·
**Tests:** `tests/test_m347_agentdev_mission_artifacts.py`

## A different noun

A **development mission** answers a question ("should SaathiOS adopt X?").
A **product mission** executes a user's goal and lives in `saathi/missions/`,
`saathi/mission_control.py` and `saathi/platform/mission_runtime/`.

They never share a store. The identifier here is `dev_mission_id`, never
`mission_id` — duplicate-source-of-truth rule 4 from ADR-012, asserted by a test.

Identifiers are `dm` + 8 hex characters and contain **no hyphen**, so
`agent/<agent-id>/<mission-id>-<description>` decomposes unambiguously.

## States

```
   intake ──► decomposed ──► research ──► design ──► security_review
                                            ▲             │
                                            └─────────────┤
                                                          ├──► implementation_ready
                                                          │         │
                                                          │         ▼
                                                          │   in_implementation
                                                          │         │
                                                          │         ▼
                                                          │    verification ──┐
                                                          │         ▲         │
                                                          │         └─────────┤
                                                          ▼                   ▼
                                                    executive_decision ◄──────┘
                                                          │
                                                    ┌─────┴─────┐
                                                    ▼           ▼
                                             owner_approval   closed
                                                    │
                                                    ▼
                                                 closed

   blocked   ◄── reachable from every state, and back to most
   abandoned ◄── reachable from every state, terminal
```

A `security_review` may skip straight to `executive_decision` when the mission
produces a decision rather than code — which is what M351's simulated mission
does.

## Exit gates

Each state names the gates that must have passed before a mission may **leave**
it. A mission cannot skip a gate by advancing twice, because the check runs on
every hop:

| Leaving | Requires |
|---|---|
| `research` | `research_completeness` |
| `design` | `architecture_approval` |
| `security_review` | `security_approval` |
| `implementation_ready` | `implementation_readiness` |
| `in_implementation` | `code_review` |
| `verification` | `automated_testing`, `negative_path_testing`, `red_team_review` |
| `executive_decision` | `executive_synthesis` |
| `owner_approval` | `owner_approval` |

`blocked` and `abandoned` are always reachable — a mission in trouble must never
be trapped by its own gates.

## Refusal codes

| Code | Meaning |
|---|---|
| `invalid_state_transition` | The transition is not declared |
| `gate_not_passed` | One or more exit gates are unmet; the detail lists them |
| `security_veto_open` | A veto blocks every forward transition |
| `close_without_terminal_verdict` | A mission cannot close undecided |
| `verdict_not_authored_by_ceo` | Only the CEO sets a terminal verdict |
| `approval_with_open_veto` | `APPROVED_FOR_IMPLEMENTATION` while a veto stands |
| `approval_with_unresolved_disagreements` | Full approval cannot paper over disagreement |
| `veto_withdrawal_by_non_author` | Only `security-governance` withdraws its own veto |
| `veto_withdrawal_without_evidence` | Assertion is not evidence |

## Terminal verdicts

```
APPROVED_FOR_IMPLEMENTATION   APPROVED_WITH_LIMITATIONS
RESEARCH_REQUIRED             REWORK_REQUIRED
REJECTED                      OWNER_DECISION_REQUIRED
```

`APPROVED_FOR_IMPLEMENTATION` is refused while any veto is open **or** any
disagreement is unresolved. `APPROVED_WITH_LIMITATIONS` may carry unresolved
disagreements — that is the point of having two approval verdicts rather than
one. This makes "do not fabricate consensus" a state-machine property rather
than an instruction.

## Artifacts

Sixteen kinds, one envelope, all schema-validated. See
[review-and-evidence.md](review-and-evidence.md) for the claim rules and the
per-kind requirements.

## Enforcement tiers

| Control | Tier |
|---|---|
| Transition table, gate prerequisites, verdict authorship | **Technically enforced** — `MissionError` from the store |
| Artifact shape, claim epistemics, per-kind fields | **Schema validated** |
| Which agent approves which gate | **Orchestration checked** — `can_review()` |
| The quality of an agent's reasoning inside a valid artifact | **Prompt guidance** |
