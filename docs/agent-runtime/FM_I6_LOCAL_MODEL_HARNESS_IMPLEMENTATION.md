# FM-I6 — Bounded LocalModelHarness Implementation

**Status:** Internal non-production implementation  
**Date:** 2026-08-07  
**Terminal verdict:** `FM_I6_LOCAL_MODEL_HARNESS_CERTIFIED_WITH_LIMITATIONS`  
**Closeout:** FM-I6.1 — `docs/agent-runtime/FM_I6_1_CLOSEOUT.md` · verdict `FM_I6_1_CLOSEOUT_CERTIFIED_WITH_LIMITATIONS`  
**Authorized baseline:** FM-I5 @ `8a45aa947944540e87a106616a2d42142543a5ca`  
**Branch:** `implementation/fm-i6-bounded-local-model-harness`  
**Production certified:** **False**  
**Model role-qualified:** **No** (plumbing only)

---

## Baseline and authorization

Owner-authorized FM-I6 from FM-I5 design. Preserves:

| Decision | Value |
| --- | --- |
| Runtime | `OLLAMA_SELECTED` 0.32.5 |
| Ownership | `USER_MANAGED_RUNTIME` |
| Model | `qwen2.5:1.5b` |
| Digest | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` |
| Endpoint | `http://127.0.0.1:11434` only |
| Concurrency | 1 session |
| Context / output | 2048 / 512 tokens |
| Data | synthetic / non-sensitive only |

## Package architecture

```text
saathi/agent_runtime/harness/
├── local_model.py              # LocalModelHarness (AgentHarness driver)
├── local_model_types.py        # Pins, readiness, config, endpoint validation
├── local_model_transport.py    # Mock + Loopback transports, NDJSON decoder
├── local_model_context.py      # Bounded context assembler
└── local_model_normalize.py    # Output normalize + strict tool proposals
```

Reuses controller, governor, durable store, ToolIntent path, FakeInMemoryHarness. Does **not** create a second gateway, governor, or controller.

## Transport model

| Transport | Network | Use |
| --- | --- | --- |
| `MockOllamaTransport` | None | CI authoritative |
| `LoopbackOllamaTransport` | Loopback only | Optional live, gated |

Loopback client: `ProxyHandler({})`, no redirects, path allowlist, structural endpoint validation, at most one transient connect retry before output.

## Endpoint policy

Accept only `http://127.0.0.1:11434`. Reject HTTPS, localhost name, non-loopback IPs, userinfo, paths, query, model-supplied endpoints.

## Runtime/model pinning

Inventory via transport `inventory()`. Exact model name + digest match. No pull, no substitution, no cloud alias.

## Context governance

`ContextAssembler`: system/user/history/tool budgets, secret-shaped reject, synthetic classification, demote forged system history, no LLM summarization, fail closed on overflow.

## Streaming decoder

`NdjsonStreamDecoder`: line/total size limits, UTF-8, JSON, strip thinking/CoT fields, fail on missing/duplicate terminal and post-terminal data.

## Events

Harness-local sequences only. Controller remains authoritative for platform event IDs. Emits TEXT_DELTA, TOOL_PROPOSAL (non-authoritative), WARNING, ERROR, PROTOCOL_VIOLATION, cancel events.

## Tool proposals

Only `<tool_proposal>{...}</tool_proposal>` with required fields. Forbidden scope/approval/credential keys rejected. Free-form shell/browser/finance prose remains text.

## Cancellation / timeouts

Cooperative `cancel_event` + `cancel_active()` (HTTP body close). Never kill PIDs. Connect 2s, first-token/load 30–60s, inter-token 15s, turn 90s.

## Retry

At most one transient loopback connect retry before any output (Loopback transport). No retry after cancel, schema fail, pressure, mismatch.

## Health/readiness

`LocalReadinessState` including RESOURCE_PRESSURE, BINDING_UNSAFE, MODEL_*, QUARANTINED. Maps to `HarnessHealth`. Healthy ≠ production certified.

## Resource governance

`max_active_sessions=1`, budget fields from session, memory gate on live, no second model policy (degraded if multiple loaded).

## Durability

Does not auto-resume inference. Interrupted turns fail/cancel; new turn requires explicit submit. Compatible with FM-I3 projections.

## Live-test gates (this host)

| Gate | Result |
| --- | --- |
| IPv6 `*:11434` listener | **`LIVE_OLLAMA_BINDING_UNSAFE`** — live skipped |
| Memory pressure | Often fails free% / available MiB floors |
| `LOCAL_MODEL_LIVE=1` | Required for live; default unset |

Mock tests are authoritative for certification of plumbing.

## Test results (authoritative)

```text
tests/test_fm_i6_local_model_harness.py  — 42 passed, 1 skipped (live)
FM-I1 + I1.5 + I2 + I3 + I4 + I6         — 184 passed, 1 skipped
```

## Limitations

1. Live inference blocked by Ollama wildcard bind and/or memory pressure (operator must rebind loopback-only and free RAM).
2. Model not role-qualified (M376).
3. Existing `OllamaEngine` elsewhere remains separate inference plane — not harness control plane.
4. Token estimates are character/4, not model tokenizer.
5. Production certification false.

## FM-I7 entry criteria (not authorized)

- Operator rebinds Ollama loopback-only
- Optional live suite green under synthetic data
- Separate design for multi-model / role qualification
- No commercial CLI adapters without security ADR

## Explicit non-actions

No ollama pull/run/start/stop/kill · no cloud providers · no credentials · no commercial CLIs · no browser/shell/fs mutation · no trading · no FM-I7 · no production cert · no model role qualification.
