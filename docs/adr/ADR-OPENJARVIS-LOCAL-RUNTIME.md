# ADR: OpenJarvis as Local AI Runtime Adapter

**Date:** 2026-07-10
**Status:** SUPERSEDED (in part by M20.1 Slice A, 2026-07-16; FM-C1 normalized)
**Implementation status:** OpenJarvis is **not** the SaathiOS runtime. SaathiOS-native `saathi.inference` implements the engine contract + catalogue + hardware profile; ModelRouter + inference governance remain authoritative for model selection under policy. Upstream OJ remains Apache-2.0 conceptual reference only.
**Authority impact:** None — historical reference.
**Superseded by:** M20/M21 inference stack documentation and `saathi.inference` source.
**Context:** Local-first AI strategy for SaathiOS; Ollama integration; device-aware model selection

---

## Problem

SaathiOS requires local LLM execution for:
- Energy efficiency (MacBook M2 with 8GB RAM)
- Latency requirements (sub-second model inference)
- Privacy (local device processing before cloud fallback)
- Cost optimization (avoid redundant cloud calls)
- Offline capability (when cloud unavailable)

OpenJarvis is an open-source local-first AI runtime with:
- Ollama integration (local models: Llama, Mistral, Phi, etc.)
- Cloud fallback (seamless fallback to Claude, GPT, etc.)
- Skill system (reusable agent capabilities)
- Scheduling (cron, continuous agents)
- Benchmarking and tracing

**Question:** Should SaathiOS adopt OpenJarvis as the local runtime adapter?

---

## Options (TBD)

Discovery will clarify:
- OpenJarvis architecture and dependencies
- Ollama integration depth and stability
- Skill system compatibility with SaathiOS
- Shell/execution security model
- Licensing (GPL, MIT, Apache, etc.)
- Production maturity
- Active maintenance

---

## Decision: APPROVED (with ModelGateway Architecture)

**OpenJarvis will be ONE adapter in ModelGateway, not the runtime directly.**

Rationale:
- 60-70% of animation pipeline infrastructure already present
- Apache 2.0 licensed (permissive, commercial-friendly, no copyleft)
- Five-primitive architecture (Intelligence, Engine, Agents, Memory, Learning) maps well to animation workflow
- Extensible registry pattern; no core modifications needed
- Event-driven orchestration supports checkpoint-based pipelines
- ModelGateway abstraction prevents lock-in and enables future provider addition

### ModelGateway Architecture

```
ToolIntent (operation="local-llm-inference")
    ↓
ExecutionGateway
    ↓
ModelGateway (provider selection)
    ├─ Ollama (local device, first choice for offline)
    ├─ OpenJarvis (hybrid with Ollama + cloud fallback)
    ├─ Claude API (cloud LLM, fallback)
    ├─ OpenAI API (cloud LLM, fallback)
    ├─ Gemini API (cloud LLM, fallback)
    ├─ Groq API (cloud LLM, fallback)
    └─ Future providers (pluggable)
    ↓
Sanitized Result
```

**Why ModelGateway?**
- OpenJarvis is ONE provider, not THE provider
- Different tasks suit different models (local vs. cloud, speed vs. quality)
- Replacing or upgrading OpenJarvis later doesn't require SystemOS changes
- A/B testing provider variants
- Cost optimization (route cheap tasks to Ollama, expensive to Claude)

**ModelGateway routing decision:**
- Privacy required? Use Ollama (local)
- Offline required? Use Ollama (local)
- Low latency required? Use Ollama or Groq
- High quality required? Use Claude or OpenAI
- Cost optimization? Use Ollama → Groq → Claude
- Cloud unavailable? Fall back to Ollama



---

## Implementation Plan

**Phase 1 (Weeks 1-4):** Foundation + E2E animation workflow
- Extend OllamaEngine for custom animation endpoints (Wav2Lip, Runway, ComfyUI)
- Create AnimationCoordinator agent (wrapping OrchestratorAgent)
- Integrate with ToolIntent (skill invocation)
- Basic memory (asset library) and tracing

**Phase 2 (Weeks 5-7):** Observability + feedback loop
- Implement full TraceStore integration
- Add health checks and diagnostics
- Feedback loop for proposal.sample renders

**Phase 3 (Weeks 8-13):** Learning routing
- Implement learning/router (requires trace data from Phase 2)
- GRPO training on render quality
- Automatic provider selection optimization

**Phase 4 (Weeks 14-16):** Scale + load balancing
- Horizontal scaling (multiple OllamaEngine instances)
- Load balancing for concurrent renders
- Production SLA compliance (99.5% uptime)

**Launch:** M5.1 production readiness by 2026-09-15

---

## ToolIntent Mapping

```
ToolIntent.operation: "local-llm-inference"
  ↓
ExecutionGateway
  ↓
ModelGateway (policy-driven provider selection)
  ├─ Check data sensitivity (private data? use Ollama)
  ├─ Check latency requirement (sub-second? use Ollama or Groq)
  ├─ Check cost constraint (budget? use Ollama)
  ├─ Check cloud availability (offline? use Ollama)
  ↓
Selected provider adapter:

  If Ollama:
    → OllamaEngine (local, M2-friendly model)
    → OrchestratorAgent executes
    → Result sanitized, no network required

  If OpenJarvis:
    → OpenJarvis Skill registry
    → OrchestratorAgent executes
    → Cloud fallback if Ollama unavailable

  If Claude/OpenAI/Gemini:
    → Cloud SDK adapter
    → Credential leased by ExecutionGateway
    → Result sanitized, no secrets exposed

  ↓
Result + Evidence
```

**No direct SDK access.** All cloud models flow through credential manager.


---

## Execution Boundary

All LLM providers (Ollama, OpenJarvis, Claude, OpenAI, Gemini, Groq) remain behind ExecutionGateway + ModelGateway.

Hard rules:
- No direct skill invocation (all via ExecutionGateway)
- No direct SDK imports in application code (all via ModelGateway adapter)
- Credential access only through credential manager (15-min leases)
- No shell execution outside sandbox (OpenJarvis shell plugin disabled)
- No direct Ollama API calls (routed through ModelGateway)
- Cloud credentials never stored in code or config
- Provider selection is policy-driven (ModelGateway), not hardcoded

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Ollama model crashes | Health check + fallback to cloud (Claude API) |
| Memory fragmentation | Bounded asset library + LRU eviction |
| Trace explosion | Sampling + compression |
| Learning feedback loop misalignment | Human-in-loop review before GRPO deployment |

---

**Status:** ✅ APPROVED FOR IMPLEMENTATION
**Documents:** OPENJARVIS_DISCOVERY.md, INTEGRATION_SUMMARY.json
**Next:** Begin Phase 1 implementation (2026-07-15)
