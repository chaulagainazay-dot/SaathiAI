# TARGET_ALLOCATION_POLICY

## Representation
- `security_id` (canonical; not ticker-only)
- `target_weight`
- `target_notional`
- optional `target_quantity` (requires fresh mark)

## Invariants
1. Long-only: weight ≥ 0 (no shorts)
2. No leverage: sum(position weights) ≤ max_gross_exposure (default 1.0)
3. Cash: cash_weight ≥ min_cash_buffer (default 5%)
4. Concentration: each weight ≤ max_position_weight (default 15%)
5. Weight reconciliation: sum(long weights) + cash_weight = 1.0 ± weight_sum_tolerance (0.0001)

## Methods (implemented)
- equal_weight
- fixed_target
- signal_proportional (caller-provided strengths)
- risk_budget_constrained (explainable caps)

## Fail closed
Invalid sums, shorts, leverage, non-eligible IDs → DATA_INSUFFICIENT / ConstructionError.
Default: do **not** silently clip fixed targets (`clip_overweight_targets=False`).

