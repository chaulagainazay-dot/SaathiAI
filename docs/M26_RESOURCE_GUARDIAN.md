# M26 Resource Guardian

## Device target

Apple Silicon M2-class, **8 GB unified memory**, **256 GB** storage.

## Memory rule (canonical M25 — do not redefine)

```text
available_memory_gb >= safety_margin_gb + minimum_model_budget_gb
# 1.5B class: 0.8 + 1.0 = 1.8 GB free required
```

Source: `saathi.inference.certification.memory_selection_ok`.

## Monitors

* available memory  
* free disk (min 5 GB default for ops block)  
* active governed requests  
* concurrency cap (default **1** on constrained host)  
* failure window → cooldown  
* circuit breaker state  

## Safeguards

| Action | Policy |
|--------|--------|
| Reject new work under memory floor | Yes |
| Invalidate historical cert on RAM drop | **No** |
| Cap concurrency | Yes (default 1) |
| Bound request storms | Yes |
| Cooldown after repeated failures | Yes (deterministic) |
| Auto model unload | **Disabled by default** |
| Auto delete model | **Never** |
| Kill unrelated apps | **Never** |
| Destructive disk cleanup | **Never** |
| Model download/pull | **Never in M26** |

## Idle unload

Policy flag `idle_unload_enabled` defaults false. Even when enabled, M26 does
not delete models; unload is operator-mediated and evidence-recorded.
