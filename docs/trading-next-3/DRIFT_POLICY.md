# DRIFT_POLICY

Trigger for material rebalance consideration:

`abs(current_weight - target_weight) >= rebalance_drift_threshold` (default 2%)

Below threshold (and below min notional) → HOLD / NO_ACTION with NO_MATERIAL_DRIFT.

Proposal only — never auto-execute.

