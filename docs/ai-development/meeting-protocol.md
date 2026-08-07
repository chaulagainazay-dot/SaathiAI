# Meeting Protocol

**Milestone:** M348 · **Module:** `saathi/agentdev/meetings.py` ·
**Tests:** `tests/test_m348_agentdev_meetings.py` (40)

## Not a chat

A meeting is a five-phase state machine over durable artifacts. Each phase
accepts exactly one class of artifact and refuses the rest, so the record cannot
drift into an unbounded conversation.

```
agenda ──► collecting ──► challenging ──► responding ──► synthesizing ──► finalized
   │            │              │               │               │
   │        submissions    challenges      responses        minutes
   │        (bounded)      (targeted)      (one per)     (+ outcome)
   │
   └── only the chair advances a phase; phases cannot be skipped
```

`blocked` is reachable from any live phase.

## Meeting types and required participants

| Type | Required participants |
|---|---|
| **Research Review** | research, product-strategy, architecture, security-governance, program-manager |
| **Architecture Council** | architecture, backend-engineering, frontend-engineering, ai-model-systems, security-governance, testing-verification |
| **Implementation Planning** | program-manager, architecture, testing-verification, documentation, **plus the assigned engineering agents** |
| **Red-Team Review** | security-governance, testing-verification, code-review, architecture |
| **Executive Decision** | ceo, program-manager, product-strategy, architecture, security-governance, testing-verification |

A meeting missing a required participant cannot be created. A red-team review
without security, or an architecture council without testing, is theatre.

Only `implementation_planning` accepts extra participants — the engineers
actually assigned. Every other type refuses them with
`unexpected_participants`, so a meeting cannot be quietly packed.

The chair must hold `chair_meeting` **and** be a participant.

## Bounded submissions

Each participant may submit at most `max_submissions_per_participant` artifacts
(default 3), and only kinds their role contract permits them to author. This is
what makes "request bounded submissions" a property rather than an instruction.

Accepted in the collecting phase: `research_findings`, `proposal`,
`architecture_decision`, `security_review`, `verification_report`, `code_review`.

## The disagreement structure

Every challenge carries all seven fields, in this order — enforced by the
artifact schema:

```
Claim:
Evidence:
Counterargument:
Failure mode:
Risk:
Alternative:
Decision required:
```

A challenge must also target a submission **made in this meeting**, and an agent
cannot challenge only its own submission.

## No fabricated consensus

Three rules, each with a test:

1. **`decided` is refused while any challenge is unanswered** — `decided_with_unanswered_challenges`.
2. **An agreement cannot be recorded over an open objection.** Pass `contested_points` mapping an agreement to the challenge that contests it; if that challenge is unanswered, finalisation is refused — `agreement_over_unanswered_challenge`.
3. **Unanswered challenges are never dropped.** They become preserved disagreements in the minutes *and* on the mission's `unresolved_disagreements`, which in turn blocks `APPROVED_FOR_IMPLEMENTATION` at decision time.

Each preserved disagreement retains who raised it, the claim, the failure mode,
the risk and the decision required.

## Insufficient evidence

`INSUFFICIENT_EVIDENCE` is a legitimate meeting outcome, not a failure. It
cannot be claimed alongside agreements — if the meeting agreed on something, it
had enough evidence for that much, and saying otherwise is its own kind of
dishonesty.

## Minutes

Every finalisation writes a `meeting_minutes` artifact carrying participants,
questions, submissions, agreements, disagreements, answered challenges and the
outcome, with `unresolved_questions` populated from each preserved
disagreement's `decision_required`.

## Enforcement tiers

| Control | Tier |
|---|---|
| Phase order, chair-only transitions, phase-specific artifact kinds | **Technically enforced** — `MeetingError` |
| Required participants, submission bounds, challenge targeting | **Orchestration checked** |
| Seven-field disagreement structure | **Schema validated** |
| `decided` with open challenges, agreement over open objection | **Technically enforced** |
| Whether an agent's challenge is *substantive* | **Prompt guidance** — structure is enforced, quality is not |
