# M20.1 — OpenJarvis Selective Integration Design (Slice A)

**Status:** Implemented (bounded)
**Starting commit:** `f4065d681456f1603ce69ca02a5bdf7a00b6864b`
**OpenJarvis reference commit:** `2e68e227b78876d2c82e375b07a456d3aa97835d`
**Licence posture:** Apache-2.0 reference only — **no OpenJarvis source vendored**

---

## Goal

Strengthen SaathiOS inference with a unified engine contract, model capability catalogue, hardware-aware fit checks, bounded benchmarks, and router observation bridge — without replacing SaathiOS architecture.

## Non-goals

- Running OpenJarvis as a process or second OS
- Second ModelRouter / scheduler / memory / event bus / agent runtime
- Auto model downloads
- Active self-learned routing
- Auto-import of community skills
- Engaging Trading Guardian

## Architecture

```
Agent / Mission / Chat
        │
        ▼
SafetyHarness / Approvals (unchanged)
        │
        ▼
ExecutionGateway (unchanged) ── local-llm-inference ToolIntent
        │
        ▼
ModelRouter  ◄──── sole selection authority
        │            (labels × privacy × cost × latency × availability)
        │
        ├─ ProviderSpec chain (existing)
        │
        ▼
saathi.inference (NEW, default-disabled)
   ├─ EngineRegistry          # adapter instances only
   ├─ InferenceEngine         # generate/stream/health/list_models/…
   ├─ adapters (ollama, openai_compat, cloud callers, fake)
   ├─ ModelCatalogue          # provenance-aware metadata
   ├─ HardwareProfile         # M2 8 GB fit / disk pressure
   ├─ discovery / runtime     # health, fallback, retries, timeouts
   ├─ benchmarks              # opt-in suite
   ├─ router_bridge           # advisory observations + hard filters
   └─ skills_gate             # third-party skill policy (no auto-import)
```

### Authoritative systems

| Concern | Authority |
|---------|-----------|
| Model selection | `saathi.model_router.ModelRouter` |
| Side effects / approvals | `ExecutionGateway` + `SafetyHarness` |
| Memory governance | existing memory + knowledge services |
| Trading | Trading Guardian only (unengaged here) |
| Config | env vars via `saathi.inference.config` (no second framework) |

### What was adapted vs referenced

| Item | Treatment |
|------|-----------|
| InferenceEngine method surface | **Adapted concept** (original SaathiOS ABC) |
| Engine discovery / health probes | **Adapted concept** |
| ModelSpec-style catalogue fields | **Adapted concept**; smaller original catalogue |
| Mount blocked patterns | **Adapted concept** in `skills_gate` |
| Latency bench idea | **Adapted concept**; SaathiOS fixture suite |
| OpenJarvis agents/scheduler/memory OS | **Rejected** |
| OpenJarvis source files | **Not copied** |

## Configuration (default-safe)

| Env var | Default | Meaning |
|---------|---------|---------|
| `SAATHI_INFERENCE_ENABLED` | false | Master switch for new runtime paths |
| `SAATHI_OPENJARVIS_COMPAT` | false | Compat flag only (does not start OJ) |
| `SAATHI_ALLOW_CLOUD_FALLBACK` | false | Cloud fallback policy |
| `SAATHI_DEFAULT_ENGINE` | ollama | Preferred local engine id |
| `SAATHI_ENGINE_DISCOVERY` | false | Runtime probes |
| `SAATHI_ENGINE_HEALTH_INTERVAL` | 300 | Seconds (for future schedulers) |
| `SAATHI_INFERENCE_TIMEOUT` | 60 | Request timeout |
| `SAATHI_INFERENCE_MAX_RETRIES` | 1 | Bounded 0–3 |
| `SAATHI_HARDWARE_AUTO_DETECT` | true | Profile local hardware |
| `SAATHI_DISK_WARNING_GB` | 25 | Disk pressure threshold |
| `SAATHI_MEMORY_SAFETY_MARGIN_GB` | 2 | Reserved RAM |
| `SAATHI_BENCHMARKS_ENABLED` | false | Live benches |
| `SAATHI_BENCHMARKS_STORE` | true | Persist under `data/benchmarks/` |
| `SAATHI_THIRD_PARTY_SKILLS` | false | Skill gate entry |
| `SAATHI_SKILL_REQUIRE_REVIEW` | true | Review required |
| `SAATHI_SKILL_SANDBOX_REQUIRED` | true | Sandbox required |
| `SAATHI_LEARNING_ROUTING_MODE` | advisory | Never auto-active |

## Module map

| Path | Role |
|------|------|
| `saathi/inference/engine.py` | Contract |
| `saathi/inference/registry.py` | Adapter registry |
| `saathi/inference/catalogue.py` | Model records + provenance |
| `saathi/inference/hardware.py` | M2/8GB profile + fit |
| `saathi/inference/adapters/*` | Ollama, OpenAI-compat, cloud, fake |
| `saathi/inference/discovery.py` | Health discovery |
| `saathi/inference/runtime.py` | Fallback + retries |
| `saathi/inference/benchmarks.py` | Bounded harness |
| `saathi/inference/router_bridge.py` | Observations + governed route helper |
| `saathi/inference/skills_gate.py` | Skill + sandbox policy |
| `saathi/inference/config.py` | Flags |

## Router integration rules

`route_with_governance()` always applies:

1. ModelRouter.route (labels, privacy, cost, prefer, availability)
2. Catalogue capability filters (structured/tool)
3. Hardware memory unfit exclusion for local oversized models
4. Optional advisory reorder by success rate **only within** deterministic keys

Never overridden by learning: safety, privacy, Trading Guardian, approvals, budget, availability, hardware limits, mission constraints.

## Rollback

1. Leave flags at defaults (all off) — package idle.
2. Or delete `saathi/inference/` and `tests/test_m20_1_openjarvis_inference.py`.
3. Existing `saathi/llm.py` + `model_router.py` paths unchanged.
4. Stub `OpenJarvisAdapter` remains non-production until explicitly rewired.

## Known limitations

- Stream path for Ollama/OpenAI-compat is generate-then-yield (not NDJSON token stream yet).
- Energy telemetry unsupported on M2 without a real collector.
- MLX/llama.cpp not fully wired — only if endpoint URLs present.
- ModelGateway / OpenJarvisAdapter stubs not fully productionized this slice.
- Retrieval / sandbox Docker / learning promotion deferred.

## Next bounded milestone (recommended)

**M20.2 delivered:** governed ExecutionGateway/ModelGateway local path (see `docs/M20_2_GOVERNED_LOCAL_INFERENCE_EXECUTION.md`). **Next:** optional opt-in caller migration from direct `llm.generate` (not global chat default); streaming deferred.
