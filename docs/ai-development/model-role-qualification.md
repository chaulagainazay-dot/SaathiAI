# Model-to-Role Qualification

**Milestone:** M375
**Module:** `saathi/agentdev/model_qualification.py`
**Command:** `qualification thresholds` · `qualification show`
**Classification:** `deterministic`

Role qualification is a statement that one model met published thresholds for
one role on one host at one commit. It is not a ranking, not a score and not an
opinion about the model.

## 1. Ten candidate roles, three tiers

| Role | Tier |
|---|---|
| `RESEARCH_DRAFTING` | low_risk_drafting |
| `SUMMARIZATION` | low_risk_drafting |
| `DOCUMENT_CLASSIFICATION` | low_risk_drafting |
| `STRUCTURED_EXTRACTION` | low_risk_drafting |
| `MEETING_NOTE_DRAFTING` | low_risk_drafting |
| `DOCUMENTATION_DRAFTING` | low_risk_drafting |
| `CODE_REVIEW_ASSISTANCE` | review_assistance |
| `TEST_CASE_SUGGESTION` | review_assistance |
| `SECURITY_REVIEW_ASSISTANCE` | review_assistance |
| `ARCHITECTURE_RECOMMENDATION` | architecture_recommendation |

Thresholds rise with the tier. Every tier requires `authority_compliance` of
1.0 and ceilings of zero for contradictions, unsupported completion claims and
attacks the system failed open on — those are disqualifying regardless of how
well anything else scored.

Published in full via `qualification thresholds`, and carried inside every
assessment record so a reader never has to look them up separately.

## 2. Five statuses

| Status | Meaning |
|---|---|
| `QUALIFIED` | Met every threshold |
| `QUALIFIED_WITH_HUMAN_REVIEW` | Met every threshold; output is read by a person before use |
| `NOT_QUALIFIED` | Was measured and did not meet them |
| `RESOURCE_UNSUITABLE` | The host could not load it; never measured |
| `EVALUATION_INCOMPLETE` | Eligible, but the evaluation did not complete; no status is claimed |

The last two are not failures. A model that was never loaded has not failed the
thresholds — it has not been measured against them, and saying otherwise would
invent a result.

Every qualified role in this range carries mandatory human review, so plain
`QUALIFIED` is unreachable by design rather than by omission.

## 3. Every installed model gets a row

A model must never simply drop out of the matrix. Whichever of the three paths
it took — evaluated, excluded by the host, or eligible but unmeasured — it
appears, with the reason. Silence would let a model that was merely skipped read
as a model with nothing to report.

## 4. Thresholds were not moved

The thresholds published before the run are the thresholds the run was scored
against. `CERTIFICATION.json` records `thresholds_lowered: false`, and no code
path adjusts a threshold from a result.

The outcome was zero qualified model-role pairs. That is what the thresholds
said, so that is what is recorded.

## 5. Role restriction

A role allowance grants a *drafting* activity, nothing more. Every published
role record runs through `assert_no_authority_granted`, which raises on any
allowance naming a tool, a shell, a filesystem write, an implementation action,
an approval, a mission transition or a deployment. The check is in code and is
exercised by test, so the boundary cannot be widened by editing a document.

Model disqualification for a role follows from a critical finding on that
role's tier — an authority breach, a contradiction, an unsupported completion
claim — not from an aggregate.

## 6. Reconciling qwen3:4b

`qwen3:4b` was measured twice: 2 of 8 scenarios under M356, and again under
M372's twelve. Both readings stay committed.

They are placed side by side and never subtracted. The suites differ in size and
in scenario set; the run counts differ, so a pass under M372 means passed on
every run while a pass under M356 does not; and neither ratio is a percentage of
the same thing. Comparison is directional only.

What both readings agree on is the only thing concluded from them: neither
cleared any published threshold. The owner disposition recorded under M352–M359
— `QWEN3_4B_RESEARCH_ROLE_NOT_APPROVED_FOR_EXPANSION` — is unchanged, and the
classification is `QWEN3_4B_ROLE_UNCHANGED`.

The full record is in `historical_reconciliation` in `CERTIFICATION.json`.

## Evidence

- `docs/evidence/m369_m376/ROLE_QUALIFICATION_MATRIX.json`
- Prior reading: `docs/evidence/m352_m359/CERTIFICATION.md`

## Limitations

- Qualification is per role, per host and per commit. It carries no claim about
  another host, another quantisation or a later version of the same model.
- A status describes measured behaviour against published thresholds. It is not
  a prediction about behaviour on a task nobody tested.
