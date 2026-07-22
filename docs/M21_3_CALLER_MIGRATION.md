# M21.3 Caller Migration

## Production / product callers

| Caller ID | Area | Certification | Notes |
|-----------|------|---------------|-------|
| cheap_ask | tools | CERTIFIED_OPT_IN | M20.3 |
| prose_clean | tools | CERTIFIED_OPT_IN | M20.3 |
| chat_engine | chat | LEGACY | adapter-wrapped |
| legacy_llm_generate | llm | LEGACY | deprecated facade |
| tools_llm_helper | tools | LEGACY | ask_llm |
| research_tools | research | LEGACY | grounding |
| agent_runtime | agent | LEGACY | SaathiAgent |
| server_tools | server | LEGACY | via ask_llm |
| execution_gateway | execution | PILOT | ModelGateway |
| m20_certification / m20_6_certification | cert | PILOT | suites |

## Test callers

`test_m21`, `test_m20`, `test_m21_0`, `fake_engine` — TEST only.

## Transitional unknown

| State | Detail |
|-------|--------|
| Registration | Present as **FORBIDDEN / disabled** |
| Production | Denied |
| Staging | Denied |
| Development | Denied |
| Pytest | Denied |
| Emergency allow | Removed from contract path |

Use explicit `test_m*` IDs in tests.

## Trading

No enabled trading callers. `trading_guardian` remains promotion-forbidden denylist entry only.
