# M38 — Canary Readiness Evaluation

## Verdicts

* NOT_READY
* READY_WITH_LIMITATIONS
* READY_FOR_OPERATOR_REVIEW
* BLOCKED_LIVE_VALIDATION_REQUIRED

## Rules

* Evaluator is read-only
* `grants_canary` is always false
* Without live sandbox exercise, maximum is READY_WITH_LIMITATIONS
* Readiness ≠ authorization
