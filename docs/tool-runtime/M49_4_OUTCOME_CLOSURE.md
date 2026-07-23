# M49.4 Outcome Classification Closure

## Terminal classes

SUCCESS, FAILURE, CANCELLED_CONFIRMED, TIMEOUT_CONFIRMED, BLOCKED,
SIDE_EFFECT_UNKNOWN, REQUIRES_REVIEW, PROHIBITED

## Enforced properties

- One terminal outcome per execution attempt
- Output validation before SUCCESS
- No SUCCESS after timeout/cancel
- No cancel SUCCESS without acknowledgement where required
- No auto-retry after SIDE_EFFECT_UNKNOWN
- Financial → PROHIBITED / REQUIRES_REVIEW paths fail closed

## State

`TOOL_OUTCOME_CLASSIFICATION_ENFORCED`
