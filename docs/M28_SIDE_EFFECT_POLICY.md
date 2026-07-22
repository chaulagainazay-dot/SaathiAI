# M28 Side-Effect Policy

## Classes

| Class | Approval | Default |
|-------|----------|---------|
| READ_ONLY | no | allow under policy |
| LOCAL_MUTATION | policy | allow under policy |
| EXTERNAL_MUTATION | **required** | deny without approval |
| COMMUNICATION | **required** | deny without approval |
| ACCOUNT_CHANGE | blocked | always deny |
| FINANCIAL | blocked | always deny |
| PRIVILEGED | explicit policy + approval | deny |
| PROHIBITED | blocked | always deny (trading, …) |

## Rules

1. Undeclared operations classify as PRIVILEGED → fail closed.  
2. Caller-supplied `claimed_side_effect_class` is **ignored** for policy.  
3. Manifest/registry cannot weaken PROHIBITED/FINANCIAL/ACCOUNT_CHANGE floors.  
4. Trading operations and `manifest.trading=true` registration fail closed.  
5. Simulated catalog actions under `manager` compat are **not** external side effects; live adapters are blocked without governed ACTIVE path.

## Mapping sources

* Operation name / capability verb  
* HTTP method (for `http_request` and generic POST/PUT/PATCH/DELETE)  
* Optional registry `operation_side_effects` (can only tighten floors)
