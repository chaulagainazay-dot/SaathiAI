# ARCHITECTURE_VALIDATION

**Tree:** `integration/saathios-canonical-baseline` @ `272dbd5d0b9495d9682955074a76b4931e440daf`  
**Delta from baseline:** M17 application_harness only (+ tests/docs)

## Runtime coexistence (intentional)

| Component | Present after M17? | M17 impact |
| --- | --- | --- |
| AgentRuntime / AgentExecutor | YES | none |
| PlatformAgentRuntime | YES | none |
| HarnessSessionController / AgentHarness | YES | none |
| LocalModelHarness | YES | none |
| EngineeringOrchestrator / AgentSessionAdapter | YES | none |
| application_harness MissionEngine / scheduler / scheduled_graph | YES | **idempotent concurrent recovery** |

## Scheduling / recovery ownership

| Concern | Owner | Post-M17 |
| --- | --- | --- |
| Mission graph recovery | MissionEngine + scheduled_graph | concurrent recoverers converge on one resumed graph |
| Occurrence dispatch | scheduler | still no direct graph executor calls |
| Harness session recovery | HarnessSessionController | unchanged |
| Platform reconcile | PlatformAgentRuntime | unchanged |

**No second mission authority introduced.**  
**No duplicate ToolIntent path introduced.**  
**No duplicate ExecutionGateway.**

## ExecutionGateway

- Single class: `saathi/execution/gateway.py`
- M17 files do not call subprocess, shell, broker, or HTTP providers
- Gateway enforcement tests (M49 + m17_22 + FM-I2) pass on this tree

## Residual legacy subprocess

Unchanged from baseline audit: tools under `saathi/tools/*` may use allowlisted subprocess.  
**Classification:** residual pre-existing risk, not introduced by M17.  
**Action this mission:** classify only; no silent mass deletion.

## Verdict

```text
ARCHITECTURE_VALIDATION_PASSED_WITH_KNOWN_PREEXISTING_DEBT
```
