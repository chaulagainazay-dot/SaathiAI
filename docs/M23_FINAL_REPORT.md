# M23 Final Report — Full Governed Chat Default and Conversation Runtime Migration

## 1. Verdict

```text
M23 COMPLETE WITH LIMITATIONS — GOVERNED CHAT DEFAULT; PRODUCTION NOT CERTIFIED
```

## 2. Baseline

| Item | Value |
|------|-------|
| Start HEAD | `232ff78` |
| Tip HEAD | `4d22208` |
| Branch | `milestone/m7-security-engine` |
| Worktree at start | clean |
| Remote ahead/behind | 0/0 |
| M21.0–M22 | COMPLETE WITH LIMITATIONS (as recorded) |
| Production certification | false |
| Live provider cert | ENVIRONMENT_BLOCKED |
| Cloud fallback | disabled |
| Trading Guardian | UNCHANGED / UNENGAGED |

## 3. Questions answered

1. **Chat paths** — inventoried in `docs/M23_CHAT_RUNTIME_AUDIT.md` (HTTP, engine, adapter, runtime, voice/studio internal, tools via gateway).
2. **Canonical production path** — `saathi.chat.runtime.run_chat_completion`.
3. **All chat uses governed inference by default** — yes (`GOVERNED_CHAT_DEFAULT=true`).
4. **Chat residual exception removed** — yes (`chat_engine_legacy_sink` migrated).
5. **One runtime authority for stream/non-stream** — yes; delivery differs only.
6. **Cancel / retry / failover deterministic** — cancel no-retry; no chat-level retry loops; router chain only via adapters.
7. **Context bounded and privacy-aware** — `build_chat_context` + safe telemetry.
8. **Tools separately governed** — default off; ExecutionGateway remains authority.
9. **Public APIs compatible** — yes (HTTP shapes, `{text,provider,tokens}`, SSE wire names).
10. **Full suite green** — see §25.

## 4–6. Scope / rules / intake

Implemented only M23. Did not start M24+. Absolute rules respected (no deploy, merge, force-push, trading, credentials, Ollama install, production_certified=true).

## 7. Canonical architecture

See `docs/M23_ARCHITECTURE.md`.

Entry → ChatRequest → identity → context builder → InferenceRequest → preflight → ModelRouter → adapters → result / stream events → ChatStore + mapper.

## 8. Governed default

| Item | Value |
|------|-------|
| Previous default | optional governed + llm.generate sink |
| New default | chat.runtime only |
| Legacy path count | 0 |
| Compatibility wrapper | thin; no provider execution |
| Hidden fallback | none |

## 9. Chat request contract

Fields: request_id, caller_id, actor/user, session, conversation_id, message, stream, tool_mode, privacy, timeout, token budget, metadata. Validation denies empty/oversized/unknown/test-in-prod/force overrides.

## 10. Context and history

Sources: store history, memory, knowledge, project, summary, agent roles. Ordering deterministic. Truncation message-count + char bound. System layering in `compose_system_prompt`.

## 11–12. Streaming / non-streaming

Event model: stream_started, text_delta, usage_update, stream_completed/cancelled/failed. Wire names start/delta/done/error. Shared governance.

## 13. Tool governance

Default off; allowlist via gateway; trading forbidden; chat does not execute tools.

## 14. Persistence

Unchanged ChatStore authority; ownership fail-closed for unknown IDs; engine still persists user/assistant once.

## 15. Privacy and logging

No raw prompt/output in runtime events; fingerprints and sizes only; release_check blocks raw log patterns.

## 16. Cost and limits

Caller max_output 2048, timeout 120, max_retries 0, request_cost_ceiling 0 cloud; process-local daily cost remains M24 limitation.

## 17. Failure taxonomy

Mapped via `map_chat_failure` to safe codes (INVALID_REQUEST, PROVIDER_KILLED, CANCELLED, …).

## 18. Residual exception manifest

| | Count |
|--|------|
| Before | 3 |
| After | 2 |
| Chat exception | **removed** |
| Remaining | engine_cloud_caller, engine_openai_compat → **M24** |

## 19. Release checks

M23 rules in `saathi/inference/release_check.py` (`_check_m23_chat_governed`). Command: `python -m saathi.inference.release_check` → ok=true.

## 20. Runtime gate

M23 checks: chat_governed_default, legacy_chat_paths, chat_residual_exception_count, chat_privacy_check, chat_streaming_check, chat_tool_governance. production_certified=false.

## 21. Invariants

```text
unknown chat paths: 0
unclassified chat paths: 0
direct chat provider execution: 0
legacy production chat paths: 0
chat residual exceptions: 0
direct provider bypasses: 0
unknown callers: 0
unknown inference paths: 0
```

## 22. Compatibility

HTTP, SSE, CLI/internal via engine, response models, conversation IDs, error envelope, cheap_ask, prose_clean, agent, research — preserved. M22 adapters unchanged.

## 23. Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```

## 24. Focused tests

```text
.venv/bin/python -m pytest tests/test_m23_governed_chat_default.py -q
→ 82 passed
```

M21/M22/chat regression suites: green after inventory/test updates.

## 25. Full repository suite

```text
Command: .venv/bin/python -m pytest -q --tb=line
Passed: 3034
Failed: 0
Skipped: 1
Duration: ~699s
Classification: PASS
```

## 26. Critical checks

Added: `m23.governed_chat_default`, `m23.release_check_chat`, `m23.residual_manifest`.

## 27. Secret scan

Chat package + chat_adapter: no blocking secrets. Pre-existing pattern hits in server/config/insforge out of M23 scope.

## 28. Performance

No new latency budget claimed. Streaming remains post-complete word-chunk delivery (compat).

## 29. Files changed (primary)

* `saathi/chat/request.py` (new)
* `saathi/chat/context.py` (new)
* `saathi/chat/stream_events.py` (new)
* `saathi/chat/runtime.py` (new)
* `saathi/chat/engine.py`, `api.py`, `__init__.py`
* `saathi/inference/chat_adapter.py`
* `saathi/inference/caller_policy.py`, `residual_paths.py`, `release_check.py`, `runtime_gate.py`, `path_inventory.py`
* `docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json`
* `tests/test_m23_governed_chat_default.py` (new)
* Related M21/M22 test assertion updates
* `docs/M23_*`, TECHNICAL_DEBT, Brain.md, critical_checks.json

## 30. Documentation

`docs/M23_CHAT_RUNTIME_AUDIT.md`, `ARCHITECTURE`, `MIGRATION`, `SECURITY_PRIVACY`, `OPERATIONS`, `ROLLBACK`, `RELEASE_CHECK`, `VALIDATION`, `FINAL_REPORT`.

## 31. Known limitations

* Live Ollama ENVIRONMENT_BLOCKED
* Circuit + daily cost process-local (M24)
* Cloud/openai_compat residual engines (M24)
* production_certified=false by design
* Multi-tenant conversation ownership still local single-user bound

## 32. Technical debt

| Item | Class | Risk | Target | Exit gate |
|------|-------|------|--------|-----------|
| Durable circuit | MEDIUM | multi-process drift | M24 | durable store + tests |
| Durable daily cost | MEDIUM | multi-process drift | M24 | durable store + tests |
| Cloud/openai_compat residuals | MEDIUM | residual count 2 | M24 | migrate or hard-block |
| Live Ollama cert | ENV | cert blocked | operator | binary + live suite |

## 33. Disable procedure

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

## 34. Rollback

See `docs/M23_ROLLBACK.md` — `git revert` of M23 commits; soft-disable via kill switch.

## 35. Commit and push

Recorded at close (implementation + docs commits; push non-force).

## 36. Production impact

Touched: chat runtime, adapter, residual manifest, release/runtime gates, tests, docs.
Untouched: Trading Guardian, exchange credentials, deploy, production cert flag, M24 stores.

## 37. Recommended next milestone

**M24 — Durable circuit/cost state and remaining engine residuals** (operator authorize only).

## 38. Exact next action

Operator decides whether to authorize M24, or hold for environment unlock (Ollama live cert).

## 39. Final milestone verdict

```text
M23 COMPLETE WITH LIMITATIONS — GOVERNED CHAT DEFAULT; PRODUCTION NOT CERTIFIED
```
