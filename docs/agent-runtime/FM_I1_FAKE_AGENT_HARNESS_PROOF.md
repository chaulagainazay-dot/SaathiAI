# FM-I1 — AgentHarness Contract, FakeInMemoryHarness, Controller Proof

**Status:** Internal non-production proof  
**Date:** 2026-08-07  
**Authorized base:** `docs/fm-c2-agent-session-harness-relationship` @ `97dc6bfab840834f3430df347f526835d94f34cd`  
**Branch:** `implementation/fm-i1-fake-agent-harness`  
**Package:** `saathi.agent_runtime.harness`  
**Tests:** `tests/test_fm_i1_agent_harness.py`  
**Production certified:** **False** (`PRODUCTION_CERTIFIED = False`)

---

## Scope

FM-I1 implements the smallest safe executable proof of Alternative F (FM-C2):

| Deliverable | Location |
| --- | --- |
| Contract types / protocol | `saathi/agent_runtime/harness/types.py`, `protocol.py`, `errors.py` |
| RunState ↔ harness projection | `saathi/agent_runtime/harness/mapping.py` |
| FakeInMemoryHarness | `saathi/agent_runtime/harness/fake.py` |
| HarnessSessionController | `saathi/agent_runtime/harness/controller.py` |
| Gateway test double | `GatewayTestDouble` in `controller.py` (not a shadow EG) |
| Audit hooks | `saathi/agent_runtime/harness/audit.py` |
| Conformance tests | `tests/test_fm_i1_agent_harness.py` |

## Architecture boundaries preserved

- `AgentSessionAdapter` **unchanged** (engineering plane only)
- No shared `DriverProtocol`
- `RunState` authoritative; harness state is projection only
- ToolIntent constructed only by `HarnessSessionController`
- Fake harness never calls ExecutionGateway
- `GatewayTestDouble` is a narrow FM-I1 seam; does not replace ExecutionGateway
- No providers, credentials, commercial CLIs, Ollama, network, shell, browser, FS mutation tools
- Trading Guardian authority unchanged
- FZ-02 / FZ-07 remain fully active

## RunState ↔ harness state mapping

| HarnessSessionState | Typical RunState projection |
| --- | --- |
| CREATED | CREATED |
| INITIALIZING / READY / RUNNING / WAITING_FOR_TOOL / CANCELLING | RUNNING |
| WAITING_FOR_APPROVAL | AWAITING_APPROVAL |
| CANCELLED | CANCELLED |
| COMPLETED | COMPLETED |
| FAILED | FAILED |
| TIMED_OUT | TIMED_OUT |
| CLOSED | prior terminal RunState (if known) |

## Tool mediation path

```text
FakeInMemoryHarness (TOOL_PROPOSAL)
  → HarnessSessionController.mediate_proposal
  → validate scope / allowlist / correlation
  → construct immutable ToolIntent (controller only)
  → GatewayTestDouble.submit (synthetic redacted result; executed=False)
  → deliver_tool_result → fake continuation
```

Approval-required tools pause at controller with `ApprovalRefState.PENDING`.
The harness cannot approve itself. Consumed approvals cannot be reused.

## Explicit non-actions

No Claude Code, Codex, OpenCode, Pi, Ollama, remote models, credentials,
AgentSessionAdapter edits, EngineeringOrchestrator changes, ExecutionGateway
replacement, Trading Guardian changes, production missions, or FM-I2.

## Freeze disposition

| Freeze | Disposition |
| --- | --- |
| FZ-01 | Partial unfreeze for FM-I1 only |
| FZ-02 | Retained |
| FZ-07 | Retained |
