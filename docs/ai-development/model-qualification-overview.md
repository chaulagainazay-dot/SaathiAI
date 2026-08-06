# Local Model Qualification — Overview

**Milestones:** M369–M376 · **Package:** `saathi/agentdev/` · **Status:** certified with limitations

M352–M359 put one local model in one seat of one mission and measured what it
did. This range asks the next question: across every model actually installed
on this machine, is any of them good enough to be given a named role — and what
does "good enough" have to mean before the answer can be yes?

The answer this range produced is **no model qualified for any role**. That is
a result, not a failure of the exercise. The apparatus that produced it is the
deliverable.

## What each milestone did

| Milestone | What it added |
|---|---|
| M369 | Pinned the vocabulary the rest of the range is written in — model output, model claim, verified claim, unverified claim, contradictory claim, completion claim, external evidence, role qualification, role restriction, model disqualification — and the boundary tokens they sit inside. |
| M370 | Read the installed models off the host and measured the machine they would run on. [Details](model-inventory.md) |
| M371 | Generalised the M356/M357 harness so more than one model can be measured against one pinned suite. [Details](cross-model-evaluation.md) |
| M372 | Ran the twelve-scenario behavioural suite across every eligible model. [Details](cross-model-evaluation.md) |
| M373 | Ran eighteen adversarial attacks across the same models, reporting model behaviour and system behaviour separately. [Details](adversarial-model-evaluation.md) |
| M374 | Added an independent claim verifier, so a model's statement about what it did is checked against evidence rather than read. [Details](claim-verification.md) |
| M375 | Scored every model against every role using published thresholds. [Details](model-role-qualification.md) |
| M376 | Turned the matrix into a routing policy that refuses, and certified the range. [Details](local-model-routing-policy.md) |

## The one idea underneath all eight

A model produces text. Text is not evidence.

Everything here follows from that. A model that says it edited a file has
produced a **model claim**, and until a deterministic source agrees, the claim
is an **unverified claim**. If the recorded evidence disagrees, it is a
**contradictory claim**. If the same reply both refuses an action and reports
it done, that contradiction is inside the response itself and is counted
separately. None of these readings change a file, a gate, a mission or an
approval, because **model statements do not change system state** — the system
state was already what it was before the model spoke.

The corollary is that **completion requires external evidence**. No model in
this range can close anything by saying it is closed.

## What was measured

Five models were installed on the certifying host. Two exceeded the host's size
ceiling and were never loaded — their behaviour is unmeasured, not poor. Three
were evaluated against an identical suite: twelve behavioural scenarios at three
runs each, eighteen adversarial attacks, and claim verification over every
response produced.

Zero model-role pairs qualified. Every one of the ten candidate roles routes to
`NO_QUALIFIED_MODEL`, which means a deterministic workflow or a person.

## What this range does not do

| Not this | Because |
|---|---|
| Give a model a tool | No role allowance in `ROLE_ALLOWANCES` contains a tool, and `assert_no_authority_granted` raises if one ever does. |
| Give a model a shell or a filesystem | The authority boundary is checked in code on every published role record, not asserted in a document. |
| Let a model approve anything | Approval is a `technically_enforced` term with an M349 gate behind it. No qualification status touches it. |
| Route around a missing model | There is no cloud fallback, no paid fallback, and no automatic fallback between local models. |
| Rank models on a leaderboard | Qualification is per role against published thresholds. There is no overall score, and adding one would let a strong dimension hide a disqualifying one. |
| Run itself | Every command is operator-invoked. The console reads evidence files and has no write verb. |

## Reading the evidence

Everything is under `docs/evidence/m369_m376/`:

| File | What it holds |
|---|---|
| `MODEL_INVENTORY.json` | Installed models, digests, sizes, eligibility, exclusions, host baseline |
| `RESOURCE_MEASUREMENTS.json` | Memory, swap and disk before and after every model that ran |
| `EVALUATION_<model>.json` | One per evaluated model: manifest, every raw reply, every parsed reply, per-criterion results, adversarial outcomes, claim verification |
| `ROLE_QUALIFICATION_MATRIX.json` | Every model against every role, with the thresholds it was measured against |
| `ROUTING_POLICY.json` | The decision for each role and the reason for it |
| `CERTIFICATION.json` | The range verdict, derived from the files above |
| `TERMINOLOGY_AUDIT.json` | The phrase guard and per-surface term coverage |
| `console-screenshots/` | The rendered read-only console |

Start with `CERTIFICATION.json`. Every number in it has a file behind it.

## Companion documents

- [Model inventory and resource baseline](model-inventory.md)
- [Cross-model evaluation](cross-model-evaluation.md)
- [Adversarial model evaluation](adversarial-model-evaluation.md)
- [Claim verification](claim-verification.md)
- [Model-to-role qualification](model-role-qualification.md)
- [Local model routing policy](local-model-routing-policy.md)
- [Model resource limits](model-resource-limits.md)
- [Operator guide](model-qualification-operator-guide.md)
- [Limitations](model-qualification-limitations.md)
- [Pinned terminology](terminology.md) (M352, extended by M369)
