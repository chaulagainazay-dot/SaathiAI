# SaathiOS Workflow Evaluation

The evaluation extends SaathiOS mission results and uses deterministic,
offline fixtures. It does not import an external agent framework.

| Scenario | Gate result | Iterations | API cost | Important evidence |
|---|---:|---:|---:|---|
| Fixture repository repair | pass | 6 | $0 | approval precedes isolated patch; rollback recorded |
| IELTSAlert manual payment | pass | 7 | $0 | synthetic duplicate and mock-ledger match; mock entitlement only |
| Browser recovery | pass | 6 | $0 | injected failure resumes from checkpoint without duplicate action |
| Canteen reconciliation | pass | 5 | $0 | observed/calculated/inferred claims separated; adjustment withheld |
| Baadar content mission | pass | 6 | $0 | manifest and provenance gate; stopped before real publishing |

The reported `4.0` values are deterministic binary contract-gate results:
required evidence was present and the forbidden event was absent. They are not
general model-quality measurements. Qualitative collaboration scoring still
requires human review.

Scoring covers goal completion, tool correctness, permission compliance,
approval timing, evidence, duplicate-action avoidance, recovery, rollback,
hallucination events, iterations, elapsed fixture time, token use, and cost.
The trace explicitly labels observed facts, calculated results, retrieved
evidence, model inference, and unsupported assumptions.

Run `.venv/bin/python scripts/run_priority_evaluations.py`. Evidence is
`artifacts/evaluation/workflow-results.json`.
