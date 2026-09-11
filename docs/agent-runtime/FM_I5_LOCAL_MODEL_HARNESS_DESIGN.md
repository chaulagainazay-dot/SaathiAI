# FM-I5 — LocalModelHarness Design and Security

**Status:** DESIGN_ONLY (documentation milestone complete)
**Date:** 2026-08-07
**Terminal verdict:** `FM_I5_LOCAL_MODEL_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS`
**Authorized baseline:** FM-I4 @ `498bf2f75dfe765368a125bfe68c1a3e8e1a985f`
**Baseline branch:** `implementation/fm-i4-resource-governance`
**Design branch:** `docs/fm-i5-local-model-harness-design`
**ADR:** [`docs/adr/ADR-LOCAL-MODEL-HARNESS.md`](../adr/ADR-LOCAL-MODEL-HARNESS.md)
**Production certified:** **False**
**Implementation present:** **No**

---

## 0. Mission boundary

This milestone answers whether SaathiOS can safely host **one** bounded local text-generation
runtime as an **untrusted** `AgentHarness` driver. It does **not** implement the driver,
start or stop Ollama, download or invoke models, connect cloud providers, or begin FM-I6.

### Primary decision question

Can SaathiOS safely support one bounded local text-generation runtime as an untrusted
AgentHarness driver without granting the model direct tool, credential, filesystem, browser,
network, scheduling, approval, execution, or trading authority?

**Answer:** **Yes, with limitations** — if and only if LocalModelHarness remains a pure driver
behind `HarnessSessionController`, uses a user-managed loopback Ollama endpoint, pins one small
installed model, enforces FM-I4 resource limits, treats all model output as untrusted, and
restricts data classification to synthetic/non-sensitive content for the first implementation.

---

## 1. Environment inventory (FM-I5.1)

Read-only inspection performed 2026-08-07. No runtime start/stop, pull, or inference.

### 1.1 Hardware and OS

| Field | Observed value |
| --- | --- |
| Model | MacBook Pro (Mac14,7 / MNEH3ZP/A) |
| Chip | Apple M2 (arm64) |
| Cores | 8 (4P + 4E) |
| Unified memory | **8 GB** (`8589934592` bytes) |
| OS | Darwin 25.5.0 (arm64) |
| Disk (root APFS) | ~228 GiB total; ~**55 GiB free** at inspection |
| Python (system) | 3.9.6 (`/usr/bin/python3`) |
| Project venv | Present (`.venv`); not required for this design milestone |

### 1.2 Memory pressure (safely inspectable)

| Signal | Observation |
| --- | --- |
| Free pages | Low (~4k pages × 16 KiB ≈ tens of MiB free) |
| Compressor pages | High (~148k pages) |
| Swap | Active (historical swapins/swapouts in the millions) |
| Implication | Host is **memory-constrained**. Local inference must assume pressure and fail closed. |

### 1.3 Local runtimes

| Binary | Path | Version | Process state |
| --- | --- | --- | --- |
| **Ollama** | `/usr/local/bin/ollama` → `Ollama.app/.../ollama` | **0.32.5** | **Running** (user-owned `ollama serve`) |
| llama-server | `/opt/homebrew/bin/llama-server` → Cellar llama.cpp **10180** | 10180 | **Not running** |
| LocalAI / LM Studio | Not found as CLI | — | — |

### 1.4 Ollama endpoints (observed listeners)

| Address | Process | Note |
| --- | --- | --- |
| `127.0.0.1:11434` | ollama | Preferred loopback |
| `*:11434` (IPv6) | ollama | **Security residual** — external bind risk if network untrusted |
| `127.0.0.1:49173` | Ollama.app helper | Not the API contract for harness |

**Harness policy endpoint:** `http://127.0.0.1:11434` only.

### 1.5 Installed models (`ollama list` — read-only)

| Name | ID (short) | Size | Modified | Notes |
| --- | --- | --- | --- | --- |
| qwen3:4b | 359d7dd4bcda | 2.5 GB | 6 days ago | Tools + thinking; Apache-2.0 |
| qwen2.5-coder:3b | f72c60cabf62 | 1.9 GB | 6 days ago | Tools; Qwen Research license |
| gemma4:e2b | 7fbdbf8f5e45 | 7.2 GB | 10 days ago | Exceeds 50% RAM policy |
| qwen3:8b | 500a1f067a9f | 5.2 GB | 2 weeks ago | Exceeds 50% RAM policy |
| **qwen2.5:1.5b** | 65ec06548149 | **986 MB** | 2 weeks ago | **FM-I6 primary candidate** |

**Currently loaded models (`ollama ps`):** none (empty).

**Model store size:** `~17G` under `~/.ollama/models` (disk inventory only; not modified).

### 1.6 Environment variables

No `OLLAMA_*`, `OPENAI_*`, `ANTHROPIC_*`, `HF_*`, `LOCAL_MODEL*`, or `SAATHI*` inference
secrets were present in the inspected process environment (names scanned; values not printed).

### 1.7 Existing SaathiOS local-model artifacts

| Artifact | Path / package |
| --- | --- |
| M369–M376 evidence | `docs/evidence/m369_m376/` |
| Routing policy | `docs/ai-development/local-model-routing-policy.md` |
| Resource thresholds | 50% RAM model ceiling; 1 concurrent resident model |
| Inference Ollama adapter | `saathi/inference/adapters/ollama.py` |
| AgentHarness package | `saathi/agent_runtime/harness/` |
| Certification | `PRODUCTION_CERTIFIED = False` in harness `__init__.py` |

### 1.8 Secrets

No secrets were printed or committed. Hardware serial/UUID were visible via system_profiler
but are **not** treated as credentials and are not required for FM-I6 design.

---

## 2. Existing source inventory (FM-I5.2)

### 2.1 Reusable contracts (must compose)

| Component | Module | Reuse for LocalModelHarness |
| --- | --- | --- |
| `AgentHarness` Protocol | `harness/protocol.py` | Implement fully |
| Session/event/tool types | `harness/types.py` | Emit `HarnessEvent`, `ToolProposal` shapes |
| `HarnessSessionController` | `harness/controller.py` | Trusted mediator unchanged |
| `HarnessSessionGovernor` | `harness/governance.py` | Concurrency=1 + budgets for local class |
| Policies | `harness/governance_policy.py` | Tighten timeouts/tokens for local model |
| Durable store | `harness/durable_store.py` | Projections; no auto-resume inference |
| Gateway bridge | `harness/gateway_bridge.py` | Redacted tool results back only |
| Fake harness | `harness/fake.py` | Conformance reference |
| Ollama HTTP patterns | `inference/adapters/ollama.py` | **Pattern reuse only** — not control plane |
| Loopback URL validation | `tests/test_m20_2_governed_local_inference.py` (`_validate_ollama_url`) | Port pattern into harness client config validation |
| M369–M376 inventory/eval | `saathi/agentdev/*`, evidence JSON | Pin digests; honor resource thresholds |

### 2.2 Duplicate adapter risks

| Risk | Mitigation |
| --- | --- |
| Second “local model control plane” parallel to harness | Forbidden — only `AgentHarness` + controller path for multi-turn agents |
| Product callers go to raw `OllamaEngine` | Existing inference plane may remain for non-harness use; harness path must not bypass controller/EG |
| Merge ApplicationHarness with LocalModelHarness | Rejected (M385 D2) |
| New eng `AgentSessionAdapter` for Ollama | FZ-02 retained — platform uses AgentHarness |

### 2.3 Missing abstractions (design targets for FM-I6 — not built here)

1. `LocalModelHarness` implementing `AgentHarness`
2. Bounded loopback HTTP client with redirect/proxy disable
3. Context assembler with token budgets and redaction hooks
4. Stream normalizer → `HarnessEvent` payloads
5. Structured tool-proposal parser (schema-strict)
6. Local readiness state machine (runtime vs model vs harness)
7. Digest pin verification against configured model id

### 2.4 Existing local-model design decisions (binding)

- Cloud fallback **prohibited** (M376 routing policy)
- Automatic model fallback **disabled**
- Model size ceiling **≤ 50% of physical RAM** (4 GiB on 8 GiB host)
- Max concurrent local evaluations / resident models: **1**
- Capability declaration never grants permission (FM-I1)
- Tool proposals never execute (FM-I2)
- Recovery never auto-resumes tools/model (FM-I3)
- Admission/queue governor exists (FM-I4)

### 2.5 Conflicts with FM-I5

| Item | Conflict | Resolution |
| --- | --- | --- |
| FZ-01 prohibits LocalModelHarness implementation | Design vs implement | Design allowed; implement frozen until FM-I6 |
| M376 `NO_QUALIFIED_MODEL` for all roles | Model selection | Select for **harness plumbing proof only**, not role certification |
| Existing `OllamaEngine.stream` is single-shot | Streaming requirement | FM-I6 must implement true NDJSON streaming in harness client (or document degraded mode) |
| Ollama IPv6 `*:11434` | Loopback-only policy | Client connects to 127.0.0.1 only; operator rebind recommended |

---

## 3. Runtime candidate analysis (FM-I5.3)

### 3.1 Comparison matrix

| Criterion | Ollama | llama.cpp server | Direct Transformers | LocalAI | Other OpenAI-compat |
| --- | --- | --- | --- | --- | --- |
| Installation state | **Installed + running** | Binary installed, idle | Heavy deps not harness-ready | Missing | None separate |
| Resource use | Moderate; model-dependent | Low–moderate | High peak RAM | Unknown | N/A |
| Process ownership | User app | Would need user start | In-process (risk) | N/A | N/A |
| Cancellation | HTTP close / abort | Varies | Thread cancel hard | Unknown | Unknown |
| Streaming | Native NDJSON `/api/chat` | Yes | Possible | Typical | Typical |
| Health / inventory | `/api/tags`, `/api/ps`, version | Custom | N/A | Varies | Varies |
| OpenAI compat | Optional `/v1` | Optional | Via wrappers | Yes | Yes |
| Offline behavior | Local weights | Local | Local | Local | Local |
| Network binding | **Loopback + residual `*:11434`** | Operator-controlled | None (in-proc) | Operator | Operator |
| Mac Apple Silicon | Mature Metal path | Mature | Mixed | Varies | Varies |
| Dependency weight | Already present | Already present | Large PyTorch risk on 8 GB | New stack | N/A |
| Sandboxability | Separate process | Separate process | **Poor** (same process) | Separate | Separate |
| Observability | Tags/ps/metrics partial | Logs | Self | Varies | Varies |
| Licensing | Ollama binary proprietary; models separate | MIT-class llama.cpp | Model+HF deps | Apache-class | Varies |
| Maintenance burden | Low for FM-I6 | Medium (wiring) | High | High | N/A |
| Testability | Mock HTTP transport | Mock HTTP | Unit-only | Mock | Mock |
| Failure isolation | Good (separate process) | Good | **Bad** | Good | Good |

### 3.2 Selection

**`OLLAMA_SELECTED`**

Evidence: installed version 0.32.5, user-running, model inventory available, loopback API,
prior SaathiOS integration patterns, and lowest incremental risk for FM-I6.

Not automatic preference — llama.cpp remains a **documented alternate** if Ollama becomes
unacceptable (e.g., binding policy cannot be mitigated operationally).

---

## 4. Model-selection policy (FM-I5.4)

### 4.1 Policy principles

1. Exactly **one** initial model for FM-I6.
2. Prefer already-installed models; **no automatic download**.
3. Explicit digest verification before first turn.
4. Fit 8 GB unified memory with concurrent OS load.
5. Bounded context and output.
6. Concurrency 1.
7. License acceptable for local non-production proof (prefer Apache-2.0).
8. M376 role qualification is **orthogonal** — plumbing may proceed without role cert.

### 4.2 Model-selection matrix

| Model | Disk | Peak risk | Tools | English | Nepali | Coding | Injection resistance (M373) | License | Provenance | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **qwen2.5:1.5b** | 986 MB | Lowest | Yes | Adequate for synthetic | Limited | Weak | Better model refusal rate (12/18 refused) | Apache-2.0 | Ollama library / Alibaba Qwen | **SELECTED** |
| qwen2.5-coder:3b | 1.9 GB | Medium | Yes | OK | Limited | Better coding | 8/18 refused | Qwen Research | Same family | Deferred |
| qwen3:4b | 2.5 GB | High under pressure | Yes + thinking | Better eval pass rate | Limited | Medium | Worse compliance rate (13/18) | Apache-2.0 | Same | **Alternate** if free RAM ≥ ~3 GiB and operator freezes other load |
| qwen3:8b | 5.2 GB | Reject | Yes | — | — | — | — | Apache-2.0 | Same | Rejected (resource) |
| gemma4:e2b | 7.2 GB | Reject | Yes | — | — | — | — | Apache-2.0 | Same | Rejected (resource) |

### 4.3 Selected model

**Name:** `qwen2.5:1.5b`
**Digest:** `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`
**Architecture:** qwen2 · 1.5B · Q4_K_M · context_length claim 32768 (harness must **not** trust full window)
**Download required for FM-I6:** **No** (already installed)
**Role qualification:** **Not qualified** (M376) — authorized only for synthetic harness proof content

### 4.4 Operator download policy (future)

If the selected model is missing at FM-I6 entry:

1. Fail closed with `MODEL_NOT_INSTALLED`.
2. Operator may run `ollama pull qwen2.5:1.5b` **outside** SaathiOS.
3. SaathiOS never issues pull automatically.
4. After pull, re-verify digest before admitting sessions.

---

## 5. Process and endpoint ownership (FM-I5.5)

**Decision:** `USER_MANAGED_RUNTIME`

| Concern | Owner | SaathiOS action |
| --- | --- | --- |
| Startup | User / Ollama.app | None |
| Shutdown | User | None |
| Crash | User / OS | Report `RUNTIME_UNAVAILABLE`; fail closed |
| Health | LocalModelHarness observes | Map to health states |
| Model load | Ollama on demand | May trigger load via chat; must respect load wait timeout |
| Model download | Operator | Never automatic |
| Port ownership | User Ollama config | Validate configured endpoint only |
| Lock ownership | Ollama multi-client | SaathiOS admits ≤1 active local session |
| Stale process | User | Observe only; **never kill arbitrary PIDs** |
| Multi-client | Shared runtime | Isolation via session IDs + no shared secrets in prompts |

**Rejected:** SaathiOS-managed start/stop for FM-I6 (process authority risk).
**Rejected:** killing user Ollama processes on cancel.

---

## 6. Network policy (FM-I5.6)

### 6.1 Binding rules

| Rule | Value |
| --- | --- |
| Scheme | `http` only to loopback (https to loopback optional later; not required) |
| Host | `127.0.0.1` preferred; `localhost` only if resolved to loopback |
| Port | `11434` default |
| Path allowlist | `/api/tags`, `/api/ps`, `/api/show`, `/api/chat`, `/api/version` (or version via tags) |
| Path deny | Anything outside allowlist; no arbitrary model-output URLs |
| Redirects | **Disabled** (max redirects = 0) |
| Proxy | **Do not inherit** `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` for harness client |
| Cloud fallback | **Prohibited** |
| External hostnames | **Prohibited** |
| Model download | **Prohibited** in harness |

### 6.2 Validation algorithm (design)

1. Parse configured base URL.
2. Reject non-http(s) schemes.
3. Resolve host; require loopback address family.
4. Reject userinfo in URL (credentials in URL).
5. Normalize to fixed base; reject path traversal tricks.
6. On any failure → `ENDPOINT_NON_LOOPBACK` or `ENDPOINT_INVALID` (fail closed).

### 6.3 Inventory endpoints (read-only for readiness)

- `GET /api/tags` — installed models
- `GET /api/ps` — loaded models
- Optional `POST /api/show` with model name for metadata (no generation)

**Note:** FM-I5 used CLI `ollama list/ps` for discovery. FM-I6 may use HTTP inventory with same semantics; still no generate until turn submit under controller.

---

## 7. LocalModelHarness responsibility boundary (FM-I5.7)

### 7.1 May own

- Connection to fixed loopback runtime
- Model request formatting
- Bounded context construction from controller-safe inputs
- Turn submission
- Streaming response decoding
- Cancellation **request** (HTTP abort / cooperative)
- Health and model metadata reporting
- Resource measurement reporting (best-effort)
- Model-output normalization
- Safe tool-proposal extraction

### 7.2 Must never own

AuthN/Z, RBAC, Approval, credentials, tool execution, EG invocation, ToolIntent construction,
filesystem, browser, external network, scheduling policy, budget policy authorship, persistence
authority, certification, deployment, trading, process lifecycle, model download.

### 7.3 Responsibility matrix

| Function | LocalModelHarness | Controller | Governor | EG | Operator |
| --- | --- | --- | --- | --- | --- |
| Admit session | no | yes | yes | no | config |
| Mint event seq | no | yes | no | no | no |
| Build ToolIntent | no | yes | no | no | no |
| Execute tool | no | no | no | yes | no |
| Call Ollama chat | yes | no | no | no | no |
| Start Ollama | no | no | no | no | yes |
| Approve action | no | mediates | no | no | yes |
| Trading veto | no | respects | no | respects | TG |

---

## 8. Request contract (FM-I5.8)

### 8.1 Bounded request object (logical)

```text
LocalModelRequest {
  request_correlation_id: string          # platform/controller minted
  session_id: string                      # platform-minted
  turn_id: string                         # platform-minted
  model_id: "qwen2.5:1.5b"                # pinned
  model_digest_expected: string           # optional preflight pin
  system_policy: string                   # non-secret policy text
  messages: [ {role, content} ]           # already redacted/bounded
  response_schema: "text_v1" | "text_plus_tool_proposal_v1"
  tool_proposal_schema_ref: string|null   # descriptive only
  max_context_tokens: int                 # ≤ 2048
  max_output_tokens: int                  # ≤ 512
  temperature: float                      # default 0.2 for proof
  top_p: float                            # default 0.9
  stop_sequences: string[]                # model-appropriate
  timeout_total_ms: int
  timeout_first_token_ms: int
  timeout_inter_token_ms: int
  cancellation_token_ref: opaque          # harness-local
}
```

### 8.2 Must never include

- Credentials or API keys
- Raw approval objects or approval secrets
- Unrestricted filesystem content
- Hidden system secrets / production DB rows
- Private CoT instructions or “think step by step privately then hide”
- Authority-granting language (“you are approved to execute…”)
- Live trading secrets / account identifiers
- Model-supplied alternate endpoints

### 8.3 Ollama mapping (design)

`POST /api/chat` with:

```json
{
  "model": "qwen2.5:1.5b",
  "messages": [...],
  "stream": true,
  "options": {
    "temperature": 0.2,
    "num_predict": 512,
    "num_ctx": 2048
  }
}
```

Tools: for FM-I6 first slice, prefer **schema-in-system-policy + structured JSON proposal**
rather than enabling Ollama native tool-calling until parser tests prove safety. Native tools
remain a **later optional** path under the same non-execution rule.

---

## 9. Context governance (FM-I5.9)

### 9.1 Token budgets (FM-I6 defaults on 8 GB)

| Pool | Tokens | Notes |
| --- | --- | --- |
| Effective context window | **2048** | Ignore model’s claimed 32k for first proof |
| Reserved for output | **256** | Hard reserve inside window |
| System policy | ≤ **384** | Fixed templates |
| Conversation history | ≤ **1024** | Oldest-first drop after summary policy |
| Memory / retrieval | **0** default | Disabled for FM-I6 synthetic |
| Tool results | ≤ **384** | Redacted EG results only |
| User turn | ≤ **512** | Truncate with audit if larger |

### 9.2 Truncation strategy

1. Drop oldest conversation turns first (never drop current user turn silently).
2. If still over budget → drop tool-result bodies to digests/summaries.
3. If still over → **fail closed** with `CONTEXT_OVERFLOW` (no silent shrink of system policy).
4. Every truncation emits `WARNING` event with counts (auditable).

### 9.3 Summary strategy

- FM-I6: **no automatic LLM summarization** (would recurse into model).
- Optional deterministic truncation markers only.
- Future summarization requires separate design + budgets.

### 9.4 Classification / redaction checks (pre-send)

| Check | Action |
| --- | --- |
| Credential-shaped spans | Redact or reject turn |
| Private CoT keys | Strip |
| Cross-workspace IDs in payload | Reject (`SCOPE_FORGERY` / isolation) |
| Classification > INTERNAL for FM-I6 | Reject |

### 9.5 Isolation

- Context assembled **per session** only.
- No silent cross-org/workspace memory.
- Stale context after session close is discarded; durable store keeps projections, not model KV cache.

### 9.6 Model-reported limits

Treat `context_length` from `/api/show` as **advisory**. Effective limits come from harness policy.

---

## 10. Output and event normalization (FM-I5.10)

### 10.1 Stream → events

| Runtime observation | HarnessEventType | Notes |
| --- | --- | --- |
| Token/chunk text | `TEXT_DELTA` | Bounded payload size |
| Final assembled text | payload on terminal or dedicated complete field | Controller sequences |
| Structured tool proposal | `TOOL_PROPOSAL` | After schema validation |
| Model refusal language | `WARNING` or terminal complete with refusal flag | Not execution |
| Malformed JSON / schema fail | `PROTOCOL_VIOLATION` or `ERROR` | Fail closed |
| Runtime HTTP error | `ERROR` | Map taxonomy |
| Timeout | `SESSION_TIMED_OUT` / turn error | Fail closed |
| Cancel ack | `CANCELLATION_ACKNOWLEDGED` | Cooperative |
| Terminal success | `SESSION_COMPLETED` or return READY | Per session lifecycle |

### 10.2 Authority rules

| Field | Authority |
| --- | --- |
| `event_id` | Controller only |
| `sequence_number` | Controller only |
| `run_id` / scope IDs | Platform/controller only |
| Runtime IDs | Non-authoritative metadata at most |

### 10.3 Safety processing

1. Unicode normalization; strip dangerous control chars (preserve necessary newlines).
2. Payload size caps (align with `max_output_chars_per_session` and per-event max, e.g. 4 KiB delta).
3. Secret-shaped output → redaction state `REDACTED` or quarantine.
4. Private CoT fields (`thinking`, `chain_of_thought`, etc.) → **strip; never persist**.
5. Free-form shell/browser commands → remain **text**, not proposals.

---

## 11. Tool-proposal format (FM-I5.11)

### 11.1 Model-emitted proposal (untrusted)

```json
{
  "proposal_id": "model-local-uuid-or-counter",
  "requested_tool_name": "echo",
  "arguments": { "text": "hello" },
  "rationale_summary": "≤ 200 chars",
  "confidence": 0.0,
  "request_correlation_id": "echo-of-request-id-only"
}
```

### 11.2 Controller-added authoritative fields

- `session_id`, `run_id`, `mission_id`
- `organization_id`, `workspace_id`
- Platform `ToolIntent` id
- Idempotency key
- Policy metadata / disposition

### 11.3 Forbidden in model output (if present → quarantine)

- Scope IDs claiming authority
- Approval references (“approval_id already granted”)
- Permissions / RBAC claims
- Credentials
- Execution IDs
- Trading Guardian decisions
- Alternate endpoints

### 11.4 Parsing rules

1. Only parse from dedicated fenced JSON or schema channel — not free-form prose.
2. Unknown fields ignored or rejected by policy (prefer reject for first proof).
3. `requested_tool_name` must be in session `allowed_tool_names` **before** controller builds ToolIntent; else `TOOL_REQUEST_DENIED`.
4. Free-form “run `rm -rf`” text → `TEXT_DELTA` only.

Maps to existing `ToolProposal` dataclass in `types.py` after controller normalization.

---

## 12. Cancellation and timeout design (FM-I5.12)

### 12.1 Timeout taxonomy (local-model tightened defaults)

| Timeout | Default (FM-I6 local) | Relation to FM-I4 |
| --- | --- | --- |
| Queue wait | 60 s | FM-I4 `max_queue_wait_seconds` |
| Runtime unavailable | 2 s connect | New local-specific |
| Model load wait | 60 s | Within startup budget |
| First-token | 30 s | Local-specific |
| Inter-token | 15 s | Local-specific |
| Total turn | **90 s** | Tightens `max_turn_seconds` (120) |
| Session duration | 600 s | FM-I4 |
| Idle | 120 s | FM-I4 |
| Cancellation grace | 10 s | FM-I4 |
| Close | 30 s | FM-I4 |

### 12.2 Cancellation behaviors

| Scenario | Behavior |
| --- | --- |
| Cancel before request | No HTTP call; session → CANCELLING → CANCELLED |
| Cancel during connect | Abort connect; CANCELLED |
| Cancel during stream | Close HTTP body; stop emitting deltas; ACK |
| Cancel after terminal | Idempotent already_terminal |
| Runtime ignores cancel | After grace → mark CANCELLED locally; do not kill process; release reservation after safe terminal |
| Connection drop | ERROR / FAILED; partial text quarantined or marked incomplete |
| Partial response | Persist incomplete flag; no silent retry |
| Duplicate terminal | Ignore second terminal; protocol warning |

### 12.3 Requirements checklist

- Fail closed
- No silent retry after cancellation
- No automatic process kill
- Capacity released only after terminal handling
- Durable cancellation state (FM-I3)
- Audit correlation IDs preserved

---

## 13. Resource-governance mapping (FM-I5.13)

### 13.1 FM-I4 → local defaults (8 GB evidence-based)

| Limit | FM-I6 local default | Notes |
| --- | --- | --- |
| Concurrent local sessions | **1** | `max_active_sessions_per_harness=1` for harness_id `local_model` |
| Global active (other harnesses) | unchanged | Fake may coexist in tests only |
| Context tokens | 2048 | Policy, not model claim |
| Output tokens | 512 | `num_predict` |
| Streamed events / session | ≤ 256 | FM-I4 default |
| Output chars / session | ≤ 8192 | FM-I4; may tighten to 4096 |
| Request retries | ≤ 1 transient connect only | See retry policy |
| Runtime reconnects | ≤ 1 | |
| Wall-clock turn | 90 s | |
| Idle | 120 s | |
| Model-load wait | 60 s | |
| Memory pressure | Originally: fail closed if free% &lt; 20 or available &lt; 1024 MiB (M370 thresholds). **FM-I6.2-MG:** pure free ≥20% is invalid as primary on macOS; see `docs/adr/ADR-MACOS-LOCAL-MODEL-MEMORY-GATE.md` (combined Darwin free% + reclaimable vs model budget + swap). | Observe; do not kill others |
| Parallel model loading | **Forbidden** | |
| Second model | **Forbidden** | |

### 13.2 Memory pressure response

1. Preflight resource check before admit/turn.
2. If breach → `RESOURCE_PRESSURE` / reject turn; no queue spin forever.
3. Never unload other users’ models by force.
4. Never download alternate smaller model automatically.

---

## 14. Health and readiness model (FM-I5.14)

### 14.1 States

| State | Meaning |
| --- | --- |
| `UNCONFIGURED` | No endpoint/model pin configured |
| `RUNTIME_UNAVAILABLE` | Loopback connect failed |
| `RUNTIME_HEALTHY` | Endpoint answers inventory |
| `MODEL_NOT_INSTALLED` | Pin missing from `/api/tags` |
| `MODEL_AVAILABLE` | Installed, not necessarily loaded |
| `MODEL_LOADING` | Load in progress / load wait |
| `MODEL_READY` | Available for chat (loaded or load-on-demand accepted) |
| `DEGRADED` | Partial (e.g., slow, streaming fallback) |
| `RESOURCE_PRESSURE` | Host thresholds breached |
| `QUARANTINED` | Security/protocol quarantine |

### 14.2 Distinctions (mandatory)

| Layer | Healthy means |
| --- | --- |
| Runtime process | Ollama responds |
| Endpoint reachability | Loopback policy pass |
| Model availability | Tag present + digest match |
| Model readiness | Can accept a generate/chat |
| Harness protocol | LocalModelHarness object ok |
| Resource health | Host thresholds ok |
| Authorization | **Never implied** by health |
| Production cert | **Always false** for FM-I6 |

Map aggregate to existing `HarnessHealthStatus` (`healthy` / `degraded` / `unhealthy`) plus detail enum in payload.

---

## 15. Failure taxonomy (FM-I5.15)

| Failure | Harness state | Retry? | Quarantine? | Operator action |
| --- | --- | --- | --- | --- |
| Endpoint unavailable | FAILED / unhealthy | 1 connect | no | Start Ollama (user) |
| Endpoint non-loopback | FAILED | no | yes config | Fix config |
| Model missing | FAILED | no | no | Operator pull |
| Model mismatch (digest) | FAILED | no | yes | Reinstall correct tag |
| Model load failure | FAILED | no | no | Free memory / check logs |
| Model evicted mid-turn | FAILED / DEGRADED | no auto | no | Retry as new turn only if user |
| Context overflow | turn fail | no | no | Shorten input |
| Malformed stream | FAILED | no | yes turn | Inspect runtime |
| Malformed JSON proposal | deny proposal | no | proposal | — |
| Schema violation | deny | no | proposal | — |
| Timeout | TIMED_OUT | no | no | — |
| Cancellation failure | CANCELLED local | no | no | — |
| Memory pressure | reject | no | no | Free RAM |
| Output limit exceeded | stop stream | no | no | — |
| Tool-proposal violation | DENIED | no | maybe | — |
| Scope-forgery attempt | PROTOCOL_VIOLATION | no | **yes** | Investigate |
| Secret-shaped output | redact/quarantine | no | yes | Rotate if real secret |
| Runtime crash | FAILED | no process restart | no | User restart Ollama |
| Unsupported runtime version | unhealthy | no | no | Upgrade/pin |
| Unsupported model version | FAILED | no | no | Pin correct digest |

Audit: every failure emits correlated `ERROR` / `WARNING` / `PROTOCOL_VIOLATION` events without secrets.

---

## 16. Retry policy (FM-I5.16)

| Condition | Retries |
| --- | --- |
| Schema / protocol / scope / secret / policy / cancel | **0** |
| Transient loopback connection failure | **at most 1** |
| HTTP 5xx mid-stream | **0** (fail closed; partial marked) |
| Model download | **never** |
| Cloud fallback | **never** |
| Automatic model switch | **never** |

Retries share the same `request_correlation_id` (idempotent correlation).
Governed by FM-I4 `max_retries_per_operation` (tighten to 1 for local harness).

---

## 17. Prompt-injection and model-trust threat model (FM-I5.17)

### 17.1 Threats

| Threat | Risk | Mitigation |
| --- | --- | --- |
| Malicious user prompt | High | Untrusted model; EG + allowlists |
| Malicious retrieved document | High | Retrieval off in FM-I6; later: redact + delimiters |
| Instruction override | High | System policy + ignore model authority claims |
| Fake approval claim | Critical | Controller owns approval state |
| Fake ToolIntent claim | Critical | Only controller builds ToolIntent |
| Fake system message in history | High | History assembled by harness from trusted store only |
| Shell/browser smuggling | Critical | Free-form text ≠ proposal; tools not in allowlist |
| Credential request | High | Redact; never place secrets in context |
| Workspace-scope confusion | Critical | Scope from platform IDs only |
| Hidden Unicode | Medium | Strip/normalize controls |
| Huge output DoS | High | Token/char limits + inter-token timeout |
| Recursive tool proposals | Medium | Max proposals / session |
| System-prompt extraction | Medium | Treat as text; no extra secrets in policy |
| Unsafe code generation | Medium | Synthetic only; no write tools |
| Financial-action recommendation | Critical | TG veto; financial tools prohibited |

### 17.2 Standing mitigations

1. Model and runtime are **untrusted**.
2. Controller rebuilds all authority context.
3. Structured proposal schema only.
4. Strict output validation.
5. Capability profiles descriptive only.
6. Approval + ExecutionGateway boundaries.
7. FM-I4 resource limits.
8. Redaction + quarantine.
9. Trading Guardian absolute veto.

---

## 18. Data classification and privacy (FM-I5.18)

### 18.1 Classification matrix for local runtime

| Class | FM-I6 to local model? |
| --- | --- |
| Public | Allowed (synthetic preferred) |
| Internal synthetic test | **Allowed** |
| Confidential real data | **Prohibited** |
| Credential | **Prohibited** |
| Health / patient | **Prohibited** |
| Financial / trading live | **Prohibited** |
| Personal data (PII) | **Prohibited** |
| Private source secrets | **Prohibited** |
| Audit/evidence records with secrets | **Prohibited** |
| Public OSS source snippets (non-secret) | Allowed only if policy says so; default **synthetic only** |

### 18.2 Principle

Local execution does **not** make sensitive processing automatically safe (shared multi-client
runtime, residual network bind, swap, model logs).

---

## 19. Observability (FM-I5.19)

### 19.1 Safe metrics

- request_count, success_count, failure_count
- first_token_latency_ms, total_latency_ms
- output_tokens, context_tokens (reported/estimated)
- cancellation_count, timeout_count
- malformed_output_count, tool_proposal_count, quarantine_count
- runtime_health_enum, model_availability_enum
- memory_pressure_event_count

### 19.2 Must not log

- Credentials
- Raw confidential prompts
- Private CoT / thinking traces
- Full responses when classification forbids
- Proxy secrets / Authorization headers (none expected)

### 19.3 Correlation

Always attach `correlation_id`, `session_id`, `turn_id` (platform IDs).

---

## 20. FM-I6 test strategy (FM-I5.20)

### A. Contract tests

- Implements `AgentHarness` protocol
- Required capabilities present
- Health shape
- Resource reporting

### B. Runtime tests

- Loopback accept / non-loopback reject
- Runtime unavailable
- Model missing / digest mismatch
- Model ready path (may use mock transport in CI)

### C. Turn tests

- Simple text, multi-turn, streaming, refusal, malformed output, context overflow

### D. Cancellation tests

- Before request, during stream, ignore-cancel grace, repeated cancel

### E. Tool-proposal tests

- Valid, malformed, free-form command stays text, scope forgery, approval forgery, financial rejection

### F. Resource tests

- Context/output limits, wall-clock, concurrency=1, memory-pressure reject

### G. Security tests

- Prompt injection corpus (reuse M373 patterns where applicable)
- Secret request, system-prompt extraction, cross-scope, Unicode, huge output

### H. Regression

- FM-I1 through FM-I4 suites
- ExecutionGateway, approvals, persistence, governor
- Trading Guardian prohibitions
- `AgentSessionAdapter` unchanged (diff/guard test)

### CI note

Default CI must use **mock transport** (no live Ollama required). Optional live job gated by
operator and `LOCAL_MODEL_LIVE=1` with synthetic prompts only.

---

## 21. FM-I6 entry gates (FM-I5.21)

FM-I6 may begin **only if** all are true:

1. Owner explicitly authorizes FM-I6 implementation milestone.
2. Runtime selection remains `OLLAMA_SELECTED` (or a superseding ADR changes it).
3. Model pin: `qwen2.5:1.5b` + digest verified installed **or** operator-approved alternate documented.
4. Ollama version pin policy documented (e.g., ≥ 0.32.x &lt; next breaking).
5. Endpoint fixed to loopback policy.
6. Process ownership remains `USER_MANAGED_RUNTIME`.
7. No-cloud-fallback policy unchanged.
8. Context/output/concurrency limits fixed as in this design (or tighter).
9. Cancellation + health + failure taxonomy implemented as designed.
10. Test plan sections A–H have owners and file paths planned.
11. Security mitigations from §17 implemented or explicitly ticketed as blockers.
12. Data classification = synthetic/non-sensitive only.
13. `PRODUCTION_CERTIFIED` remains False.
14. FZ-01 implementation unfreeze scoped only to LocalModelHarness + tests (not commercial CLIs).

---

## 22. Prompt / system policy template (design)

Design intent (not a secret; still non-authority-granting):

```text
You are an untrusted local assistant driver for SaathiOS.
You do not have credentials, approval power, tools execution, filesystem, browser,
network, or trading authority.
You may answer in plain text.
If proposing a tool, emit ONLY the tool-proposal JSON schema when asked; otherwise text.
Never claim that actions already executed.
Never invent approval or scope IDs.
Never request or echo secrets.
```

---

## 23. Security findings (environment + design)

| ID | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| SEC-I5-01 | Ollama listens on `*:11434` (IPv6) | Medium | Operator rebind; client loopback-only |
| SEC-I5-02 | Host under memory pressure / swap | Medium | Fail-closed resource gates |
| SEC-I5-03 | No model role-qualified (M376) | Medium | Synthetic plumbing only |
| SEC-I5-04 | Model may emit tool-like prose | Medium | Schema-only proposals |
| SEC-I5-05 | Thinking-capable models may leak CoT | Medium | Strip thinking fields; prefer 1.5b |
| SEC-I5-06 | Shared multi-client Ollama | Low–Med | No secrets in prompts; concurrency 1 |
| SEC-I5-07 | Existing OllamaEngine not redirect-safe by default | Low | Harness client must set strict URL policy |

---

## 24. Explicit non-actions (FM-I5)

- No LocalModelHarness implementation
- No protocol source changes
- No Ollama start/stop/pull/run/generate
- No model download or deletion
- No cloud providers, credentials, commercial CLIs
- No browser/shell/fs mutation tools
- No FM-I6 start
- No production certification claim

---

## 25. Freeze-register disposition

| Freeze | Disposition after FM-I5 |
| --- | --- |
| FZ-01 | **Design allowed**; implementation remains frozen pending FM-I6 authorization |
| FZ-02 | Retained |
| FZ-07 | Retained |
| FZ-08 | Retained |

---

## 26. Recommended next milestone

**FM-I6 — LocalModelHarness implementation (not authorized by this document)**

Only after owner authorization and entry-gate checklist satisfaction.

---

## 27. Exact stop statement

**STOP after FM-I5.**
Do not begin FM-I6.
Do not implement LocalModelHarness.
Do not start, stop, download, invoke, or modify Ollama or another local runtime.
Do not add providers, credentials, browser, shell, filesystem mutation, external network access,
commercial CLI adapters, production missions, or trading authority.

---

## Appendix A — Evidence commands used (read-only)

```bash
git status --short
git rev-parse HEAD
git rev-parse implementation/fm-i4-resource-governance
uname -a
sysctl -n hw.memsize
system_profiler SPHardwareDataType
df -h /
vm_stat
command -v ollama
ollama --version
ollama list
ollama ps
ollama show <model>   # metadata only
command -v llama-server
lsof -nP -iTCP -sTCP:LISTEN   # inspect listeners only
```

Forbidden commands **not** run: `ollama pull`, `ollama run`, `ollama launch`, HTTP
`/api/generate`, `/api/chat`, `/v1/chat/completions` for generation.

## Appendix B — Key source paths

| Path | Role |
| --- | --- |
| `saathi/agent_runtime/harness/protocol.py` | AgentHarness protocol |
| `saathi/agent_runtime/harness/types.py` | Events, ToolProposal, health |
| `saathi/agent_runtime/harness/controller.py` | Trusted mediator |
| `saathi/agent_runtime/harness/governance.py` | FM-I4 governor |
| `saathi/inference/adapters/ollama.py` | Existing non-harness Ollama client |
| `docs/evidence/m369_m376/CERTIFICATION.json` | Qualification verdicts |
| `docs/adr/ADR-LOCAL-MODEL-HARNESS.md` | ADR decisions |

## Appendix C — Terminal verdict rationale

**`FM_I5_LOCAL_MODEL_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS`**

Approved because architecture, runtime, model pin, ownership, network, contracts, threats,
and FM-I6 gates are complete without implementation side effects.

Limitations: 8 GB pressure, non-qualified models, Ollama bind residual, synthetic-only data,
user-managed availability, streaming must be correctly implemented in FM-I6.
