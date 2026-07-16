# M20.1 — OpenJarvis Selective Integration Audit

**Date:** 2026-07-16
**Starting SaathiOS commit:** `f4065d681456f1603ce69ca02a5bdf7a00b6864b`
**OpenJarvis commit audited:** `2e68e227b78876d2c82e375b07a456d3aa97835d`
**OpenJarvis licence:** Apache License 2.0
**Scope:** Selective primitive evaluation only — OpenJarvis is **not** a parallel OS.
**Canonical milestone:** M20.1 — Selective OpenJarvis Primitive Integration (Slice A).
**Numbering decision:** Historical **M18.3** remains the InsForge read-only pilot (`docs/M18_3_INSFORGE_*`). M20.0 is reserved for the Engineering Orchestrator track. This work is **M20.1**. InsForge history is not rewritten.

---

## Governing principle (parallel architecture forbidden)

| SaathiOS authority (source of truth) | OpenJarvis role |
|--------------------------------------|-----------------|
| Mission orchestration | none |
| Approvals / SafetyHarness | none |
| ExecutionGateway | optional engine adapters may execute *only* as handlers |
| Run ledger / scheduler / monitoring | none |
| Memory governance (tiers, retention, ownership) | optional retrieval *backend* under memory only |
| ModelRouter (`saathi/model_router.py`) | informs capability metadata — **does not replace** |
| Control Center / CEO OS / business agents | none |
| Trading Guardian | never engaged by OJ concepts |
| Application integrations | none |

**Hard rule:** One registry, one scheduler, one memory governance layer, one event bus, one agent runtime, one model router, one ExecutionGateway. OpenJarvis may supply *ideas* and *optional adapters*, never second cores.

---

## Local hardware profile (audit target)

| Field | Value |
|-------|--------|
| Chip | Apple Silicon M2 |
| Unified memory | 8 GB |
| Storage (approx.) | ~228 GB |
| Local runtime | Ollama |
| Dedicated VRAM | none (unified memory) |

---

## Component audit matrix

### 1. Inference engine abstraction

| Field | Detail |
|-------|--------|
| **OpenJarvis component** | `InferenceEngine` ABC + registry + discovery |
| **Source paths** | `src/openjarvis/engine/_stubs.py`, `_base.py`, `_discovery.py`, `ollama.py`, `_openai_compat.py` |
| **SaathiOS equivalent** | `saathi/model_router.py` + `saathi/llm.py` + stub `ModelGateway` / `OpenJarvisAdapter` |
| **Maturity** | Router + sync generate path: deterministic-tested. ModelGateway/OpenJarvisAdapter: **stubs**. No uniform async stream/health/list_models/cost/capabilities contract. |
| **Overlap** | Both route LLM work; SaathiOS already has capability labels and fallback chains. |
| **Missing capability** | Uniform engine interface (generate/stream/health/list_models/estimate_cost/capabilities), discovery, normalized errors, retries/timeouts at engine layer. |
| **Integration value** | **High** — closes the gap between router selection and real engine ops without a second router. |
| **Integration risk** | Medium if OJ runtime is vendored; **low** if SaathiOS-native interface reuses concepts. |
| **Licence** | Apache-2.0 — safe to *adapt concepts*; copy requires NOTICE retention. Prefer original SaathiOS code. |
| **M2 8 GB** | Abstraction itself is negligible; engines must not load multiple large models. |
| **Decision** | **INTEGRATE** (Slice A) — SaathiOS-native `saathi.inference` contract. |
| **Evidence** | OJ ABC is a strong pattern; SaathiOS `llm.generate` is provider-family callers without health/stream/capability metadata; ADR already says ModelGateway adapters, not OJ-as-runtime. |

**Parallel architecture answers:**

1. *Why not existing subsystem?* ModelRouter selects; it does not execute health, stream, catalogue, or hardware fit. `llm.py` callers are sync HTTP one-shots without a shared engine registry.
2. *Behind existing interface?* Yes — engines implement execution under ModelRouter + optional ModelGateway; labels stay authoritative.
3. *Second registry/runtime?* No engine *selection* registry that overrides ModelRouter. Engine registry is for *adapters only*.
4. *Authoritative system?* **ModelRouter** for selection; **ExecutionGateway** for side-effectful ops; SafetyHarness for governance.
5. *Rollback?* Feature flag `inference.enabled=false` (default); delete/disable package; prior `llm.generate` path unchanged.
6. *Success metric?* Unit tests for registration/discovery/fallback/timeouts; router tests still pass; no second `route()` authority.

---

### 2. Model registry / hardware compatibility catalogue

| Field | Detail |
|-------|--------|
| **OpenJarvis component** | `ModelSpec`, `BUILTIN_MODELS`, hardware detection |
| **Source paths** | `src/openjarvis/intelligence/model_catalog.py`, `core/types.py` (`ModelSpec`), Rust `hardware.rs` / Python config detect |
| **SaathiOS equivalent** | `ProviderSpec` in `model_router.py` (name, labels, cost, latency, local flag only) |
| **Maturity** | Thin static registry — no context window, quant, RAM/disk estimates, provenance, declared vs detected. |
| **Overlap** | Provider list vs model catalogue — related but different grain. |
| **Missing** | Parameter count, quant, context, privacy_class, capability provenance, fit estimates for M2 8 GB. |
| **Value** | **High** for local-first safe model choice. |
| **Risk** | Low if catalogue is advisory metadata for ModelRouter, not a second router. |
| **Licence** | Apache-2.0; SaathiOS will ship a *smaller original* catalogue with explicit provenance fields (no mass-copy of OJ catalogue). |
| **M2 8 GB** | Catalogue static; fit checks prevent OOM-class choices. |
| **Decision** | **INTEGRATE** (Slice A). |

**Authoritative:** ModelRouter final selection. Catalogue supplies metadata only.

---

### 3. Local/cloud engine discovery and health

| Field | Detail |
|-------|--------|
| **OJ** | `discover_engines`, concurrent health probes |
| **SaathiOS** | `env_availability()` key presence only; Ollama only if `OLLAMA_HOST` set |
| **Missing** | Runtime probe (tags/health endpoints), unhealthy exclusion, discovery cache. |
| **Decision** | **INTEGRATE** (Slice A) — optional discovery behind flag; default no network spam. |

---

### 4. AI benchmarking and telemetry

| Field | Detail |
|-------|--------|
| **OJ** | `bench/latency.py`, throughput, energy modules; evals suite |
| **SaathiOS** | Opik tracer optional; no bounded model/engine comparison harness |
| **Decision** | **INTEGRATE** (bounded harness in Slice A). Energy marked **unsupported** unless measured. |
| **M2 8 GB** | Benchmarks opt-in, single model at a time, small fixtures. |

---

### 5. Retrieval backends (FTS5, BM25, FAISS, ColBERT, hybrid RRF)

| Field | Detail |
|-------|--------|
| **OJ** | `src/openjarvis/memory/*`, tools retrieval |
| **SaathiOS** | Memory tiers + M18.2 codebase memory hybrid + M19 unified knowledge service |
| **Overlap** | **High** — SaathiOS already has hybrid retrieval and governance. |
| **Decision** | **DEFER** for runtime; **AUDIT only** this milestone. Memory governance stays authoritative. |

---

### 6. Standards-compatible skills

| Field | Detail |
|-------|--------|
| **OJ** | `src/openjarvis/skills/*` importer/security |
| **SaathiOS** | `saathi/skills_library` (store/search; execution not auto) + application_harness importer (untrusted) |
| **Decision** | **ADAPT CONCEPT ONLY** — design skill-ingestion gate + tests that block trading/secrets; no community skill auto-import. |

---

### 7. Trace-based routing / learning

| Field | Detail |
|-------|--------|
| **OJ** | `learning/routing`, trace stores, GRPO-style loops |
| **SaathiOS** | Event bus model.selected/fallback; Opik; SafetyHarness deterministic |
| **Decision** | **DEFER** active learning. Slice A may write **advisory** observations into existing traces only. Learned policies cannot override safety/privacy/TG/budget. |

---

### 8. Sandboxed agent execution

| Field | Detail |
|-------|--------|
| **OJ** | `sandbox/mount_security.py`, Docker/Podman runner |
| **SaathiOS** | Application harness limits, SafetyHarness, ExecutionGateway risk/approval |
| **Decision** | **ADAPT CONCEPT ONLY** this milestone — document required sandbox characteristics; strengthen harness later. Mount-escape + secrets tests as pure policy checks. |

---

### 9. Installation and system diagnostics

| Field | Detail |
|-------|--------|
| **OJ** | install tests, doctor-style CLI |
| **SaathiOS** | `saathi/ops/diagnostics.py`, health modules |
| **Decision** | **DEFER** — extend existing diagnostics later; hardware profile covers slice of need. |

---

### 10. Agents, scheduler, MCP, A2A, channels, mining, speech, PEARL

| Decision | **REJECT** as OS cores. Agents/scheduler/MCP already exist in SaathiOS. Mining/speech/channels not needed for Slice A. |

---

### 11. OpenJarvis as runtime / ModelGateway stub

| Field | Detail |
|-------|--------|
| **Current** | `OpenJarvisAdapter` is a TODO stub that always “succeeds” with fake data |
| **Decision** | **REJECT** treating OpenJarvis process as SaathiOS runtime. **ADAPT**: wire ModelGateway ollama path to SaathiOS `InferenceEngine` adapters when flag on; leave OJ process optional future remote. |

---

## Slice selection

| Slice | Scope | Status |
|-------|--------|--------|
| **A — Unified Inference Runtime + Model Capability Registry** | Engine contract, registry, discovery, hardware profile, catalogue, Ollama + OpenAI-compat + existing cloud callers as adapters, benchmark harness, router observation bridge, config flags, tests, docs | **THIS MILESTONE** |
| B — Retrieval backend under memory (if gap proven) | Deferred |
| C — Skill ingestion gate + sandbox hardening | Audit + minimal guards only |
| D — Trace learning promotion pipeline | Deferred |

---

## Explicit non-goals (this milestone)

- Do not install or run OpenJarvis as a service.
- Do not download models.
- Do not vendor OJ Python tree.
- Do not create second ModelRouter, mission engine, memory tier, or Trading Guardian.
- Do not enable cloud fallback by default for sensitive data.
- Do not claim energy measurement.

---

## Licence findings

| Item | Finding |
|------|---------|
| OpenJarvis | Apache-2.0 |
| Direct code copy | **None** in Slice A (original SaathiOS implementation) |
| Conceptual reference | Engine ABC shape, discovery pattern, model-spec fields, mount-block patterns |
| Obligation if later copying | Retain Apache headers + update `THIRD_PARTY_NOTICES.md` with source path + commit |

---

## Success criteria for Slice A

1. Audit (this document) complete.
2. `saathi.inference` present, default-disabled.
3. ModelRouter remains sole selection authority.
4. Deterministic tests pass for engines, hardware, catalogue, router bridge, benchmarks, skill/TG guards.
5. Existing model-router and memory tests still pass.
6. Rollback documented and trivial (flags off / package unused).
7. M2 8 GB fit warnings implemented without downloads.
