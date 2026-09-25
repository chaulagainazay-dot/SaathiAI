# ADR: LocalModelHarness — Bounded Local Inference Driver

| Field | Value |
| --- | --- |
| **ID** | ADR-LOCAL-MODEL-HARNESS |
| **Date** | 2026-08-07 |
| **Status** | **ACCEPTED_DESIGN_ONLY** |
| **Milestone** | FM-I5 |
| **Parent decisions** | ADR-AGENT-HARNESS-INTERFACE · ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP · FM-I1–FM-I4 |
| **Full design** | [`docs/agent-runtime/FM_I5_LOCAL_MODEL_HARNESS_DESIGN.md`](../agent-runtime/FM_I5_LOCAL_MODEL_HARNESS_DESIGN.md) |
| **Design baseline SHA** | `498bf2f75dfe765368a125bfe68c1a3e8e1a985f` |
| **Design baseline branch** | `implementation/fm-i4-resource-governance` |
| **Design branch** | `docs/fm-i5-local-model-harness-design` |
| **Implementation status** | **FM-I6 partial** — `LocalModelHarness` + mock/loopback transports under `saathi.agent_runtime.harness.local_model*` (`PRODUCTION_CERTIFIED=False`). Live gated. Not role-qualified. |
| **Terminal verdict (design)** | `FM_I5_LOCAL_MODEL_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS` |
| **Terminal verdict (impl)** | `FM_I6_LOCAL_MODEL_HARNESS_CERTIFIED_WITH_LIMITATIONS` |
| **Closeout (FM-I6.1)** | `FM_I6_1_CLOSEOUT_CERTIFIED_WITH_LIMITATIONS` — true wildcard Ollama exposure documented; live skipped; see `docs/agent-runtime/FM_I6_1_CLOSEOUT.md` |
| **Production certified** | **False** |
| **Authority impact** | None while design-only; if later implemented under FM-I6, driver only under harness controller — never EG replacement |
| **Supersedes** | Informal “wire Ollama as agent control plane” speculation |
| **Does not supersede** | ADR-AGENT-HARNESS-INTERFACE · M369–M376 qualification certificates · `saathi.inference` provider plane |
| **Explicit non-actions** | No LocalModelHarness code · no Ollama start/stop/pull/run · no model download · no inference · no providers/credentials · no commercial CLIs · no FM-I6 |

---

## Context

FM-I1 through FM-I4 established an internal multi-turn **AgentHarness** stack:

| Milestone | What was proven |
| --- | --- |
| FM-I1 | Contract types, `FakeInMemoryHarness`, `HarnessSessionController` |
| FM-I1.5 | Stress, fuzz, concurrency isolation, fail-closed malformed events |
| FM-I2 | Real ExecutionGateway via controller-built immutable `ToolIntent`; local echo/noop only |
| FM-I3 | Durable session/event projections; restart recovery without auto-continuation |
| FM-I4 | Bounded admission, queue fairness, resource reservations, timeout taxonomy |

M385 D10 ordered the first real-world harness candidate after the fake as **LocalModelHarness**
(read-only / advisory local turns). M369–M376 already inventoried local models and certified
**with limitations** that **no model is role-qualified** for operational agentdev seats on this host.

The primary decision question for FM-I5:

> Can SaathiOS safely support one bounded local text-generation runtime as an untrusted
> AgentHarness driver without granting the model direct tool, credential, filesystem, browser,
> network, scheduling, approval, execution, or trading authority?

---

## Decision summary (required answers)

| # | Decision | Answer |
| --- | --- | --- |
| 1 | Is LocalModelHarness architecturally approved? | **Yes**, as an **untrusted** `AgentHarness` driver under `HarnessSessionController`. Design-only until FM-I6. |
| 2 | Which local runtime? | **`OLLAMA_SELECTED`** — Ollama **0.32.5** already installed and user-running. |
| 3 | Process ownership? | **`USER_MANAGED_RUNTIME`** — SaathiOS connects only; never starts/stops/kills Ollama. |
| 4 | Initial model? | **`qwen2.5:1.5b`** for FM-I6 synthetic harness proof only (digest pinned). Not role-qualified (M376). |
| 5 | Model download required? | **No** for FM-I6 entry. Download remains **operator-only**, never automatic. |
| 6 | Permitted endpoint? | **`http://127.0.0.1:11434`** only (fixed config; no model-supplied endpoints). |
| 7 | Non-loopback endpoints? | **Prohibited** unless a future security ADR + certification separately allow. |
| 8 | Cloud fallback? | **Prohibited.** No paid-provider fallback. No automatic model switching. |
| 9 | Max concurrent local inference sessions? | **1** active local inference session on the 8 GB Mac. |
| 10 | Context / output bounds (FM-I6 defaults)? | **Context ≤ 2048 tokens** effective window; **output ≤ 512 tokens**; reserved output headroom 256. |
| 11 | Streaming required? | **Yes** — true NDJSON stream decoding preferred; single-shot allowed only as degraded path with audit. |
| 12 | Cancellation? | Cooperative cancel via harness `request_cancel` + HTTP cancel/close; timeouts fail-closed; **no process kill**. |
| 13 | Health / readiness? | Multi-state model: runtime health ≠ model ready ≠ harness authorized ≠ production certified. |
| 14 | Tool proposals? | Strict structured proposals only; controller rebuilds authority; free-form “run this” stays text. |
| 15 | Prompt injection? | Model untrusted; schema validation; EG/approval/TG boundaries; quarantine on forgery. |
| 16 | Data classification for FM-I6? | **Synthetic / non-sensitive test content only.** No patient, trading, credential, or production data. |
| 17 | What FM-I6 may implement? | One `LocalModelHarness` adapter + tests behind entry gates; loopback Ollama client; no lifecycle ownership. |
| 18 | What remains prohibited? | See §Explicit prohibitions. |

---

## Architectural placement

```text
Surface / Mission / Chat (future callers)
        ↓
agent_runtime (RunState authoritative)
        ↓
HarnessSessionController  ← trusted mediator (admission, events, ToolIntent, EG)
        ↓
LocalModelHarness         ← untrusted AgentHarness driver (this ADR)
        ↓  HTTP loopback only
User-managed Ollama       ← external process (not owned by SaathiOS)
        ↓
Model weights (qwen2.5:1.5b)  ← untrusted model
```

**Composition, not replacement:**

| Existing system | Relationship |
| --- | --- |
| `AgentHarness` protocol | LocalModelHarness **implements** it |
| `HarnessSessionController` | Sole trusted mediator; mints event IDs / sequences |
| `HarnessSessionGovernor` (FM-I4) | Admission, concurrency=1 for local harness class, budgets |
| `HarnessDurableStore` (FM-I3) | Projections only; recovery never auto-resumes inference |
| `ExecutionGateway` + `ToolIntent` | Sole side-effect path; controller builds ToolIntent |
| `saathi.inference.adapters.ollama.OllamaEngine` | **Reuse patterns only** — not a second control plane; harness must not bypass controller |
| `saathi.agentdev` M369–M376 | Qualification evidence reused; not authority to run production roles |
| `ApplicationHarness` | Remains distinct (argv tools) |
| `AgentSessionAdapter` | Unchanged; engineering plane only |
| Trading Guardian | Absolute veto; financial execution remains PROHIBITED |

---

## Permanent invariants (reaffirmed)

1. RunState remains authoritative for platform runs.
2. LocalModelHarness session state remains a projection.
3. HarnessSessionController remains the trusted mediator.
4. ExecutionGateway remains the sole authoritative external side-effect path.
5. ToolIntent remains controller-built and immutable.
6. The local model may emit tool proposals only.
7. The local model may never execute a tool directly.
8. Approval state remains outside the model and harness.
9. Credentials remain outside the model and harness.
10. Provider and runtime configuration remain governed.
11. Resource limits remain enforced by FM-I4 policies and governor.
12. Durable session projections remain governed by FM-I3.
13. Recovery never automatically resumes inference.
14. AgentSessionAdapter remains engineering-specific and unchanged.
15. ApplicationHarness remains distinct.
16. Trading Guardian retains absolute veto authority.
17. No private chain-of-thought may be persisted or exposed.
18. The runtime and model are untrusted components.
19. Capability declaration never grants permission.
20. Production certification remains false.

---

## Runtime selection evidence

| Candidate | Installed? | Running? | Decision |
| --- | --- | --- | --- |
| **Ollama 0.32.5** | Yes (`/usr/local/bin/ollama` → Ollama.app) | Yes (user PIDs; `127.0.0.1:11434`) | **SELECTED** |
| llama.cpp `llama-server` 10180 | Yes (`/opt/homebrew/bin/llama-server`) | No process; no model inventory wired | Rejected for FM-I6 first path |
| Direct Transformers (in-process) | Not as a harness runtime | N/A | Rejected — process isolation + 8 GB risk |
| LocalAI | Not installed | N/A | Rejected |
| Separate OpenAI-compatible server | None besides Ollama’s optional `/v1` | N/A | Not selected as primary |

**Selection code:** `OLLAMA_SELECTED`

Rationale: already present, inventory (`ollama list`) works, loopback endpoint exists, existing inference adapter patterns, Apple Silicon suitable, no new binary install for FM-I6. Limitations documented (IPv6 `*:11434` bind; user-managed only).

---

## Model selection evidence

| Model | Size (disk) | Params | Quant | Tools | License | 8 GB fit | FM-I6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **qwen2.5:1.5b** | 986 MB | 1.5B | Q4_K_M | yes | Apache-2.0 | **Best** | **SELECTED** |
| qwen2.5-coder:3b | 1.9 GB | 3.1B | Q4_K_M | yes | Qwen Research | Marginal | Deferred |
| qwen3:4b | 2.5 GB | 4.0B | Q4_K_M | yes (+thinking) | Apache-2.0 | Tight under pressure | Alternate only |
| qwen3:8b | 5.2 GB | 8.2B | Q4_K_M | yes | Apache-2.0 | **Unsuitable** (M370 exclude) | Rejected |
| gemma4:e2b | 7.2 GB | 5.1B | Q4_K_M | yes | Apache-2.0 | **Unsuitable** | Rejected |

**Pinned identity for FM-I6 (when implemented):**

- Name: `qwen2.5:1.5b`
- Digest (M376 inventory): `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`
- Runtime: Ollama ≥ 0.32.x (version check fail-closed if major policy changes)

**Selection class:** harness **plumbing proof model**, not M376 role-qualified model.
All agentdev roles remain `NO_QUALIFIED_MODEL` per ROUTING_POLICY.json.

---

## Process ownership

**Decision:** `USER_MANAGED_RUNTIME`

| Concern | Owner |
| --- | --- |
| Startup / shutdown | User / Ollama.app |
| Crash recovery | User / OS / Ollama |
| Health observation | LocalModelHarness reports; does not heal by restart |
| Model load / unload | User / Ollama defaults; harness may request chat which may load model |
| Model download | **Operator only**; harness never pulls |
| Port / bind | User Ollama config; harness validates loopback target only |
| Locks / multi-client | Assume multi-client possible; SaathiOS concurrency limit = 1 session |
| Stale process | Observe + fail closed; **never kill arbitrary PIDs** |

---

## Network policy

| Rule | Value |
| --- | --- |
| Allowed endpoint | `http://127.0.0.1:11434` (configurable only via operator config, same host constraints) |
| Allowed hosts | `127.0.0.1`, `localhost`→127.0.0.1 only after resolve-to-loopback check, `::1` optional if dual-stack policy later certifies |
| Reject | Non-loopback IPs, external hostnames, redirects, proxy env inheritance for harness client, cloud URLs |
| Cloud fallback | Prohibited |
| Model-supplied endpoints | Prohibited |
| Download URLs | Prohibited in harness path |
| Telemetry to third parties | Not assumed; harness does not enable |

**Security finding (environment):** Ollama currently also listens on `*:11434` (IPv6). FM-I6 must still **connect only** to loopback. Operator should rebind Ollama to loopback-only before any multi-tenant or network-exposed use. Does not block design approval with limitations.

---

## Responsibility boundary

### LocalModelHarness may own

- Loopback connection to selected runtime
- Request formatting and bounded context construction (from controller-supplied safe inputs)
- Turn submission and stream decoding
- Cooperative cancellation **request** toward runtime/HTTP
- Health and resource **reporting**
- Model-output normalization into harness event payloads
- Safe tool-proposal **extraction** (non-authoritative)

### LocalModelHarness must never own

- Authentication, RBAC, approval, credentials
- Tool execution, ExecutionGateway invocation, ToolIntent construction
- Filesystem / browser / external network / shell authority
- Scheduling authority, budget policy authorship, persistence authority
- Certification, deployment, trading authority
- Runtime process lifecycle (start/stop/kill)
- Model download or cloud routing

---

## Explicit prohibitions (carry-forward)

- Implement LocalModelHarness without FM-I6 owner authorization
- Start/stop/kill Ollama or any user process
- `ollama pull` / `ollama run` / inference from this design milestone
- Connect Claude Code, Codex, OpenCode, Pi, or cloud providers
- Add API keys, OAuth, provider SDKs as harness secrets
- Subprocess-backed model adapters for FM-I6 first path
- Browser, shell, filesystem mutation tools for the local model
- Unrestricted repository access
- External network egress from harness client
- Live trading or financial execution
- Persist or expose private chain-of-thought
- Treat capability declaration as permission
- Production certification

---

## FZ-01 freeze disposition

| Item | Disposition |
| --- | --- |
| FZ-01 production activation | **RETAINED** |
| LocalModelHarness **design** | **ALLOWED** (this ADR — docs only) |
| LocalModelHarness **implementation** | **STILL FROZEN** until FM-I6 owner authorization + entry gates |
| FZ-02 / FZ-07 commercial / eng adapters | **RETAINED** |
| FZ-08 ambient credentials | **RETAINED** |

---

## Alternatives considered

| Option | Outcome |
| --- | --- |
| Reject all local model path | Rejected — M385 D10 + host has suitable small model; path is designable with limits |
| Select llama.cpp server first | Deferred — binary present but no integrated inventory/ops path; higher FM-I6 cost |
| In-process Transformers | Rejected — isolation and memory risk on 8 GB |
| SaathiOS-managed Ollama lifecycle | Rejected for FM-I6 — kill/start authority too dangerous |
| Select qwen3:4b first | Deferred as default — better quality but tight on 8 GB under observed pressure; alternate if operator freezes other workloads |
| Role-qualified production local agent | Rejected — M376 says `NO_QUALIFIED_MODEL` for all roles |
| Use `OllamaEngine` as AgentHarness | Rejected as control-plane merge — reuse HTTP patterns only behind harness protocol |

---

## Consequences

### Positive

- Clear untrusted-driver path for local inference under existing FM-I1–I4 stack
- Evidence-based runtime and model pins without forcing downloads
- Explicit network, ownership, and data-classification limits for 8 GB Mac

### Negative / limitations

- Host under memory pressure (high swap); even 1.5B model needs free-memory gates
- M376: no model role-qualified; FM-I6 is plumbing, not product intelligence certification
- Ollama IPv6 wildcard bind is an environment residual risk
- User-managed runtime means “unavailable” is a normal state
- True streaming must be implemented carefully (existing `OllamaEngine.stream` is single-shot)

### Neutral

- `saathi.inference` remains the governed provider plane for non-harness callers
- Agentdev qualification artifacts remain evidence, not runtime authority

---

## Implementation status and next gate

| Item | Status |
| --- | --- |
| FM-I5 design | **Complete** (this ADR + design doc) |
| LocalModelHarness source | **Present (FM-I6)** — internal non-production |
| FM-I6 | **Complete with limitations** — see FM_I6 implementation report |
| Production | **False** |

---

## References

- Full design: `docs/agent-runtime/FM_I5_LOCAL_MODEL_HARNESS_DESIGN.md`
- Protocol: `saathi/agent_runtime/harness/protocol.py`
- Types: `saathi/agent_runtime/harness/types.py`
- Governor: `saathi/agent_runtime/harness/governance.py`
- Existing Ollama adapter (non-harness): `saathi/inference/adapters/ollama.py`
- Qualification: `docs/evidence/m369_m376/`, `docs/ai-development/local-model-routing-policy.md`
- Parent ADRs: ADR-AGENT-HARNESS-INTERFACE, ADR-TOOLINTENT-IMMUTABLE-CONTRACT, ADR-EXECUTIONGATEWAY-SPECIFICATION
