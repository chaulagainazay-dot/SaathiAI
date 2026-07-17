# M21.4 — Residual Exception Manifest Validation

## Source

`docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json`  
Frozen expected count: **7** (`EXPECTED_EXCEPTION_COUNT` in `runtime_gate.py`)

## Required fields (each exception)

```text
path_id, file, symbol, classification, reason, owner,
production_reachability, allowed_behavior, forbidden_behavior,
caller_id, expiry_milestone, tests, release_guard
```

## Enforcement

| Rule | Result |
|------|--------|
| File exists | PASS |
| Symbol token present in file | PASS |
| Tests files exist | PASS |
| Release guard present | PASS |
| No wildcards | PASS |
| Classification permitted | PASS |
| No expired (≤ M21.3) entries | PASS |
| Count not expanded | PASS (7 ≤ 7) |
| No trading / withdrawal path_ids | PASS |
| unknown_count = 0 | PASS |
| direct_provider_bypass_count = 0 | PASS |
| production_certified field false | PASS |

## Entries (unchanged from M21.3)

1. `legacy_llm_generate_execution` → M22  
2. `chat_engine_legacy_sink` → M23  
3. `agent_sdk_clients` → M22  
4. `tools_research_grounding` → M22  
5. `openjarvis_execution_adapter` → M22  
6. `engine_cloud_caller` → M24  
7. `engine_openai_compat` → M24  

## Expansion status

```text
NOT EXPANDED
```

No exceptions removed (all still required until M22/M23/M24 migrations).
