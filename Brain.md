# Brain.md — The Living Brain of SaathiAI

> **What this document is:** The canonical living constitution of SaathiAI. It summarizes platform state, vision, active priorities, architectural principles, core capabilities, known limitations, and strategic decisions. It is the first document any human or coding agent should read before working on SaathiAI. It does not replace the SES documents — it points to them.
>
> **What this document is not:** A technical specification. Engineering specs live in `docs/SES/v1.0/`. This document tells you *what we are building and why*. The SES documents tell you *exactly how*.
>
> **Update cadence:** After every significant decision, capability addition, or architectural change. Not after every commit.

---

## 1. The One-Line Vision

SaathiAI is an AI Operating System — a platform that runs autonomous departments, manages its own memory, produces multimedia content, learns from every outcome, and gets smarter with every day it operates.

---

## 2. What SaathiAI Is

SaathiAI is not a chatbot. It is not a content scheduler. It is not a collection of scripts.

It is a **platform** — one set of shared capabilities (agents, memory, voice, studio, discovery) deployed across multiple products, continuously improving itself through a learning loop that feeds production outcomes back into platform intelligence.

**The test for every new feature:** "Does this make SaathiAI a better AI Operating System, or does it solve only one product's problem?"

If the answer is the latter, the feature belongs in the product layer, not the platform. If the answer is the former, it belongs in the shared platform and all products benefit.

---

## 3. Current Platform State

### Platform M30 connector conformance and certification (2026-07-17)

* **Module:** `saathi.connectors.conformance` — specification, sandbox harness, fingerprint, drift, revoke, CLI.
* **Platform production certification (M25)** ≠ **connector behavioral certification (M30)**; both may be required for ACTIVE.
* **States:** UNASSESSED → ASSESSING → CERTIFIED | CERTIFIED_WITH_LIMITATIONS | FAILED | ENVIRONMENT_BLOCKED; also STALE, REVOKED.
* **Eligibility:** ACTIVE/CANARY require fresh CERTIFIED*; unassessed/failed/stale/revoked/env-blocked cannot activate.
* **Built-ins assessed:** `gov.http`, `gov.mcp`, `gov.browser`, `gov.local_tool` → CERTIFIED_WITH_LIMITATIONS (sandbox ≠ live provider).
* **Activation eligibility:** certification + production cert + readiness + policy + approval; default rollout remains OFF.
* **Drift/revoke:** fingerprint change → STALE; revoke preserves evidence and blocks ACTIVE.
* **Does not** enable live SaaS, OAuth, API keys, cloud inference, or Trading Guardian.
* **M31:** operator authorize only.

### Platform M29 connector identity and trust registry (2026-07-17)

* **What a connector is:** deterministic `ConnectorManifest` + registry resolve — never import path/filename.
* **Modules:** `saathi.connectors.registry` (trust, capabilities, validation, deps, docs CLI, builtins, persistence); extended gov registry/runtime.
* **Trust levels:** INTERNAL … PROHIBITED; approval floor + rollout eligibility + capability ceiling are registry-owned.
* **Capability classes:** READ/WRITE/EXECUTE/HTTP/MCP/BROWSER/… cannot exceed trust.
* **CLI:** `python -m saathi.connectors.registry docs` — catalog + trust/capability/rollout summaries.
* **Does not** enable live SaaS, OAuth, API keys, cloud inference, or Trading Guardian.
* **M30:** completed (conformance + certification).

### Platform M28 canonical connector migration (2026-07-17)

* **Canonical path:** Caller → ToolIntent → ExecutionGateway → GovernedConnectorRuntime → adapter.
* **M28 modules:** `gateway_bridge`, `side_effects`, `compat`, `bypass_guard`; default connector family handler on UniversalBoundary.
* **Legacy:** `manager.execute` wrapped (simulated only; live adapters fail closed); platform ExecutionEngine fail-closed without gateway.
* **Side-effect classes:** READ_ONLY … PROHIBITED; FINANCIAL/ACCOUNT_CHANGE/trading blocked; caller cannot override class/rollout/adapter/approval.
* **Bypass:** production connector bypasses = 0 (AST scan + allowlist).
* **Does not** enable live SaaS, OAuth, cloud inference, or Trading Guardian.
* **M29:** completed (identity + trust registry).

### Platform M27 governed connector framework (2026-07-17)

* **Canonical module:** `saathi.connectors.gov` — single governed execute path for connector kinds.
* **Lifecycle:** REGISTERED → VALIDATED → READY / DEGRADED / DISABLED / DRAINING / FAILED.
* **Adapters:** HTTP (GET/POST/PUT/PATCH/DELETE), MCP (reuses `mcp_governance`), browser (reuses `saathi.browser`), local tools (allowlist only).
* **Rollout:** inherits M26 modes; default OFF; ACTIVE requires production certification + connector certification (M30) + READY connector.
* **Security:** domain/op allowlists, secret redaction, no API keys in code, trading connectors forbidden.
* **Does not** enable cloud inference, live OAuth, or new SaaS accounts.
* **M28:** completed (migration + gateway enforcement).

### Platform M26 production inference operations (2026-07-17)

* **Canonical lifecycle:** `python -m saathi.inference.ops` — start/status/readiness/health/drain/stop/restart/recover.
* **Health ≠ readiness:** health = ops process; readiness = safe to accept governed work now (typed READY/DEGRADED/ENVIRONMENT_BLOCKED/POLICY_BLOCKED/DRAINING).
* **Resource guardian:** reuses M25 memory rule (`available >= 0.8 + model_budget`); concurrency cap default 1; no auto model delete; idle unload off by default.
* **Rollout modes:** OFF (default) / SHADOW / CANARY / ACTIVE / DRAINING; ACTIVE requires computed production certification; rollback → OFF.
* **Provider supervision:** session-level states; does **not** claim Ollama PID ownership.
* **Incidents + events:** privacy-safe, deduplicated; no raw prompts/outputs.
* **M25 certification package preserved** under dual evidence + package artifacts.
* **Cloud fallback disabled**; Trading Guardian unengaged; residual exceptions 0.
* **M27:** operator authorize only — do not auto-start.
* **Roadmap note:** M21.39 “connectors M26” deferred; this M26 is ops per operator authorization.

### Platform M25 production certification closeout (2026-07-17)

* **Live local provider:** historically certified (dual evidence); current host may be MEMORY_BLOCKED without erasing PASS.
* **Package evidence store:** `saathi.inference.cert_evidence` → `docs/evidence/m25/cert/` (full suite, secret scan, critical checks).
* **Runtime gate states:** PASS / FAIL / STALE / MISSING / ENVIRONMENT_BLOCKED (no NOT_TESTED placeholders for package gates when disk is empty → MISSING).
* **production_certified=true** when every mandatory gate is PASS and package evidence is fresh for the package fingerprint.
* **Fingerprint policy:** code/policy/schema/model identity — not temporary RAM or discover re-runs.
* **Freshness:** 14-day TTL; STALE requires re-record.
* **Architecture:** `docs/M25_PRODUCTION_CERTIFICATION.md`.
* **Residual exceptions = 0**; cloud fallback disabled; Trading Guardian unengaged.
* **M26:** operator authorize only — do not auto-start.

### Platform M22 governed provider implementation (2026-07-17)

* **Provider HTTP/SDK execution** confined to `saathi/inference/adapters/` (`http_providers`, `grounding`, `agent_provider`, existing engines).
* **`llm.generate`** is a pure compatibility facade (ModelRouter + `invoke_family`); no provider URLs or keys in `saathi/llm.py`.
* **Agent** constructs no OpenAI/Anthropic clients; uses `build_agent_session`.
* **Research grounding** uses `adapters.grounding.grounded_generate` only.
* **Residual EXPLICIT_LEGACY_EXCEPTION count:** 0 in path table; manifest exceptions reduced to **3** (chat M23; cloud/openai_compat M24).
* **Release-check** enforces facade purity + M22 credential scan; `production_certified=false`.
* **Local-first**; cloud fallback off; Trading Guardian unengaged; no live provider cert in M22.

### Platform M21.4 runtime consolidation & production gate (2026-07-17)

* **Canonical production-configuration gate:** `python -m saathi.inference.runtime_gate` (also `python -m saathi.m20_console runtime-readiness`).
* **One authority map** for request contract, caller policy, provider descriptors, availability, cost, failure taxonomy, retry/failover, circuit breaker, kill switches, residual paths/manifest, bypass guard, release check, production config, certification decision.
* **Release-check integrated** into `saathi.ops.release_gate` — inference architecture failure blocks canonical release.
* **Certification invariant:** `production_certified=false` unless every mandatory gate is genuinely PASS (live provider, full suite, secret scan, critical checks included). Partial/static evidence cannot certify.
* **Gate states** include PASS/FAIL/BLOCKED/NOT_TESTED/ENVIRONMENT_BLOCKED — never collapse NOT_TESTED or ENVIRONMENT_BLOCKED to PASS.
* **Residual exceptions** (post-M22): 3 remaining compatibility wraps; M21.4 freeze was 7.
* **Kill-switch matrix** covers chat, llm.generate, agent, server/research tools, cheap_ask, prose_clean, gateway.
* **Local-first**; cloud fallback default off; live Ollama typically ENVIRONMENT_BLOCKED without operator install; Trading Guardian unengaged.

### Platform M21.3 residual inference paths (2026-07-17)

* **Canonical path authority:** product caller → approved adapter → `InferenceRequest` / preflight → contract + caller policy → M21.2 provider governance → ModelRouter → governed adapter or explicit legacy sink.
* **Residual-path elimination policy:** every path is CANONICAL / COMPATIBILITY_WRAPPED / TEST_ONLY / FAKE / BLOCKED / EXPLICIT_LEGACY_EXCEPTION — never UNKNOWN or DIRECT_PROVIDER_BYPASS.
* **Compatibility adapters** preserve public APIs (`chat_adapter`, `cheap_ask`, `prose_clean`, `ask_llm`) without second gateways.
* **Release-check authority:** `python -m saathi.inference.release_check` fails closed on new bypasses, new `llm.generate` sites, duplicate request models, enabled trading callers, raw log flags.
* **Caller identity required;** transitional `unknown` is FORBIDDEN/disabled in all environments.
* **Chat** is COMPATIBILITY_WRAPPED (not full rewrite); legacy sink expiry M23.
* **Provider bypass prohibited** outside exact allowlisted adapters/residuals.
* **Local-first**; cloud fallback default off; `production_certified=false`; Trading Guardian unengaged.

### Platform M21.2 inference governance (2026-07-17)

* **Canonical provider decision** before any governed attempt: capability → availability → cost/privacy → kill/circuit → ranked selection.
* **Availability states** are explicit (KILLED…AVAILABLE); adapter existence ≠ available.
* **Failure taxonomy** drives hard vs soft, retry, failover, circuit impact.
* **Failover defaults off**; no implicit cloud; unknown paid price fails closed.
* **Circuit breaker** is provider-scoped, process-local (restart clears).
* **Local-first**; `production_certified=false`; Trading Guardian unengaged.
* Modules: `saathi.inference.provider_decision`, `availability`, `cost_policy`, `circuit_breaker`, `failure_taxonomy`.

**As of 2026-07-02**

| Layer | Status | Key Documents |
|-------|--------|--------------|
| Foundation & Standards | ✅ Complete (L3) | SES-000 series (A–F) |
| Architecture | ✅ Complete (L3) | SES-001 |
| Agent System | ✅ Complete (L3) | SES-002 |
| Memory & Knowledge Graph | ✅ Complete (L3) | SES-003 |
| Voice OS | ✅ Complete (L3) | SES-004 |
| Execution Infrastructure | ✅ Complete (L1) | Phase 3.1 ToolIntent, Phase 3.2 ExecutionGateway |
| AI Studio | 🔄 Writing | SES-005 |
| Autonomous Engineering | 📋 Queued | SES-006 |
| Mission Control | 📋 Queued | SES-007 |
| Business OS | 📋 Queued | SES-008 |
| Learning OS | 📋 Queued | SES-009 |
| Discovery Engine | 🔄 Writing | SES-010 |
| Security & Guardrails | 📋 Queued | SES-011 |
| Event Fabric | 📋 Queued | SES-012 |
| Compliance & Governance | 📋 Queued | SES-013 |
| Product Framework | 📋 Queued | SES-014 |
| Financial Intelligence | 📋 Queued | SES-015 |
| Research Engine | 📋 Queued | SES-016 |
| World Model | 📋 Queued | SES-017 |
| Dream Engine | 📋 Queued | SES-018 |
| Deployment & Infrastructure | 📋 Queued | SES-019 |
| Future Roadmap | 📋 Queued | SES-020 |

**Overall specification maturity: ~25%**
Foundation is solid. The creative engine (AI Studio), autonomous engineering, and mission control are the next milestone.

---

## 4. Products

SaathiAI is the platform. These are the products built on it.

| Product | Purpose | Status | Domain |
|---------|---------|--------|--------|
| **pielts** | Free IELTS practice with instant band scores | Live | pielts.web.app |
| **Mr. Yeti** | IELTS content creator (YouTube, TikTok, Instagram) | Building | @pieltsapp |
| **HCG POS** | Hospital canteen point-of-sale | Live | Internal |
| **HCG Live Signal** | Real-time canteen analytics (NOT crypto) | Live | Internal |
| **Travel Platform** | Nepal travel booking | Future | TBD |

Every product capability that can be generalized belongs in the platform. Every platform capability is available to all products.

---

## 5. Long-Term Vision

SaathiAI evolves through five phases:

**Phase 1 — Personal AI OS** *(now)*
One operator (Ajay). Five products. Core platform capabilities: agents, memory, voice, studio, discovery. The system learns from every interaction and improves over time.

**Phase 2 — Autonomous Company**
The platform runs multiple departments autonomously: Engineering, Studio, Discovery, Research, Finance. Human operator sets strategy and approves high-stakes decisions. Agents handle execution.

**Phase 3 — Multi-Operator Platform**
Multiple operators can run their own SaathiAI instance. Organization-level memory, permission management, federated knowledge (platform rules shared; personal data isolated).

**Phase 4 — AI-Native Business Infrastructure**
SaathiAI becomes the operating system for AI-native businesses — complete with financial intelligence, legal compliance, HR, customer intelligence, and strategic planning.

**Phase 5 — World Model + Dream Engine**
SaathiAI develops a persistent model of the external world (SES-017) and a Dream Engine (SES-018) that sets long-horizon goals, decomposes them into strategies, and autonomously pursues them across all departments.

---

## 6. Architectural Principles

These ten principles govern every engineering decision. When in doubt, ask which principle applies.

| # | Principle | The Rule |
|---|-----------|---------|
| AP-01 | Platform First | Build capabilities once. Reuse everywhere. No product-specific duplicates. |
| AP-02 | Provider Abstraction | All LLM, TTS, STT, storage calls through `app/providers/`. No direct SDK imports in business logic. |
| AP-03 | SQLite First | SQLite for all server-side state. Migration to Postgres is a config change, not a rewrite. |
| AP-04 | Agent Contracts | Every agent declares a 13-field contract before implementation. No contract = no agent. |
| AP-05 | Safety by Classification | Actions are L1–L5. Classification is deterministic. Approval gates are automatic. |
| AP-06 | Memory Promotes, Not Forgets | Nothing expires without the Promotion Engine evaluating it first. |
| AP-07 | Observe Before Acting | Context Assembly runs before every significant LLM call. Agents that skip memory skip intelligence. |
| AP-08 | Stream Everything | No pipeline stage waits for the previous stage to complete. Streaming end-to-end. |
| AP-09 | Measure Everything | Opik traces all LLM calls. OpenObserve receives all structured logs. No invisible operations. |
| AP-10 | Renderer Registry | Rendering backends, LLM providers, TTS providers — all are swappable without business logic changes. |
| AP-11 | Intelligence Decides, Automation Executes | The SaathiAI brain makes decisions; n8n, browser automation, shell, cloud deploys, and APIs are executors it invokes. Automation is never the brain. n8n executes workflows the brain designs — it does not decide. |
| AP-12 | Independently Testable | Every subsystem is unit-, integration-, load-, and failure-recovery-testable in isolation, and observable. Dependencies are injected, not imported. A subsystem that can't be tested alone isn't done. |
| AP-13 | Event-First Integration | Subsystems publish events and subscribe to events; they do not call each other directly unless absolutely necessary. Storage → Event Fabric → {Mission Control, Telegram, Analytics, Learning Engine}, not Storage → Mission Control. Keeps SaathiAI loosely coupled as it grows. |
| AP-14 | Autonomy Is Earned, Not Assumed | Every increase in autonomous capability must be matched by an equivalent increase in **governance, observability, and recoverability**. A new autonomous power ships only with its safety classification, its audit trail, and its undo/kill path. Capability without governance is a regression, not progress. |
| AP-15 | Knowledge Promotion Is Evidence-Driven, Not Occurrence-Driven | A pattern becomes knowledge because the *evidence* supports it (verification count, source diversity, time consistency, cross-product reach) — not merely because it was observed. Seeing something once, or a hundred times from one source, is not the same as knowing it. Every knowledge item carries its source trace and can answer *"why do I believe this?"* |
| AP-16 | Contradictory Knowledge Is Reviewed, Never Silently Replaced | When new knowledge conflicts with existing promoted knowledge, both are kept and linked, and the conflict is routed to review. History of reasoning is preserved; the platform never quietly overwrites what it used to believe. |
| AP-17 | Promotion Is Deterministic Before AI-Assisted | Candidate discovery, clustering, evidence scoring, and state transitions are deterministic and testable. An LLM may *assist* pattern extraction, but it never decides promotion, contradiction, or state. Governance stays predictable and auditable. |
| AP-18 | Learning Proposes, Never Mutates | The Learning Engine never edits a prompt, a config, or a core document directly. It produces explicit, governed **proposals** — a capability improvement, a knowledge candidate, a Brain/Business/Wisdom candidate, an ADR candidate, or an engineering task — that a human (or an approval policy) accepts. Improvement is measurable and reversible: prefer an A/B experiment to a silent replacement. |
| AP-19 | Relationships Are First-Class Knowledge | A fact is valuable; a relationship between facts is often more valuable. The Knowledge Graph models edges (ACHIEVED_BY, GOVERNS, CONTRIBUTES_TO, SUPERSEDES, DERIVED_FROM …) as first-class, so the platform can answer questions no isolated memory can — *which capabilities contribute to the financial goal, which ADR introduced this rule, why do we use Renderer Y now.* Departments query `KnowledgeGraph`, never a backend, never Cypher (AP-02). |
| AP-20 | Human Documents Are Derived Artifacts, Not Primary Storage | The authoritative source is Knowledge → Graph → Memory. `Brain.md`, `Business.md`, `Wisdom.md`, and the style guide are **published views** rendered from that source, never the database. The Publication Engine proposes structured updates a human approves; markdown renders only after approval. This prevents document drift forever. |

---

## 5b. Development Rule #1 — Documentation Stays One Milestone Ahead, Not One Year Ahead

The permanent working discipline for the Engineering Phase:

1. **Document what you're about to build** (the current milestone's slice).
2. **Build it.**
3. **Test it.**
4. **Update the documentation with what actually changed.**

Do NOT document entire future systems months before implementation — it produces specs that drift from reality. SES-001 through SES-020 exist as a roadmap; only the milestone in flight gets detailed, reconciled-against-code specification. Progress is judged by **running, tested code**, not by document count.

> **Phase marker (2026-07-02):** SaathiAI has moved from the **Architecture Phase** to the **Engineering Phase**. From here, `BUILD_STATUS.md` is the source of truth for what is real; SES docs describe intent.

> **Phase marker (2026-07-03):** M1 — AI OS Core **complete** (`v0.1.0-alpha`). Six production platform capabilities. Now in **M2 — Learning Runtime**: SaathiAI learns from completed work and measurably improves future decisions without manual prompt edits.

---

## 5c. Development Rule #2 — Ecosystem Integration Is Mandatory

> No new autonomous capability may be implemented unless it integrates with **Memory, Event Fabric, Mission Control, Runtime Governance, and the Learning Engine** where applicable.

Every future capability becomes part of the ecosystem rather than an isolated feature. A capability that publishes no events, records no memory, surfaces nothing to Mission Control, and bypasses governance is a silo — and silos violate AP-01 (Platform-First). Build capabilities once, reuse everywhere, improve continuously.

---

## 5d. Development Rule #3 — Integration Sprint After Every Milestone

The platform's biggest risk is no longer missing features — it's staying cohesive as it grows. After every major milestone, run an Integration Sprint that requires:

1. Every capability registered in the **Platform Capability Registry**.
2. Every new feature emits standardized events to the **Event Fabric**.
3. Every business activity creates **Episodes** for the Learning Runtime where appropriate.
4. Every major subsystem exposes **KPIs** to Mission Control.
5. Every significant architectural decision reflected in the governance docs (`Brain.md`, `Business.md`, `Wisdom.md`, Writing & Speaking Style).

This keeps SaathiAI a unified AI operating system, not a collection of disconnected modules.

---

## 6b. Memory Layer L6 — Platform Wisdom (the constitution)

Beyond the ordinary memory tiers (L0 working → L5 archive), SaathiAI has a **constitutional** layer that must never be buried among ordinary memories:

**L6 — Platform Wisdom** is not facts. It contains the rules that govern how SaathiAI thinks and acts:
- Engineering & Architecture Principles (AP-01 … AP-14)
- Development Rules (#1 docs-one-milestone-ahead, #2 ecosystem-integration)
- Business Principles, Coding Standards, Safety Policies, Decision Frameworks

Examples: *AP-11 — Intelligence Decides, Automation Executes.* *AP-14 — Autonomy is earned, not assumed.*

These are the constitutional rules. The Learning Engine and Brain Synchronizer (M2) may propose **candidates** for L6, but promotion into it is the highest-governance action — human-approved only, never auto-promoted. L6 is where `Brain.md`'s principles live; ordinary learned patterns live in L2 semantic memory and below.

---

## 7. Core Capabilities

### 🏷️ Platform Capabilities at v1.0 (build once, reuse everywhere, improve continuously)

**Storage Intelligence — v1.0 (2026-07-02)** — the first capability to reach this bar. Code-complete, tested (32 tests), reusable. `saathi/storage/`: Disk Watchdog, File Lifecycle Engine (the only sanctioned deleter; PERMANENT files never auto-deleted), Cleanup Engine (executes only Lifecycle-authorized deletions), Predictive Storage Engine (per-renderer temp profiles — LTX/Wan/Open-Sora/ComfyUI/FFmpeg), Telegram Alerts, Storage Database, `storage.*` event vocabulary on the Event Fabric.

> **Reuse mandate:** From v1.0 onward, **every** product — AI Studio, pielts, HCG POS, HCG Live Signal, and any new application — uses the Storage Intelligence service for file management. No product implements its own disk/cleanup/archival logic. This is AP-01 (Platform-First) and AP-10 (Capability Reuse) made real. (Live-wiring into the running process — 1-min watchdog poll + real Telegram + scheduled cleanup — is the remaining deploy step before it is "running in production.")

Current platform capabilities (from SES-000F Capability Registry):

**Agent Capabilities:** Multi-step reasoning, tool use, BMA Loop, parallel workflow execution, human approval gates

**Memory Capabilities:** 6-tier memory (L0–L5), Knowledge Graph (SQLite Phase 1-3, Neo4j Phase 4), Context Assembly, Memory Promotion Engine, Learning Engine

**Voice Capabilities:** 11-stage streaming pipeline, Conversation State Machine (11 states), Speaker Identity (enrollment + verification), Barge-In, Continuous Dialogue, SSML prosody, OmniVoice TTS

**Studio Capabilities (in spec):** AI Director, Storyboard Engine, Character Consistency (IC-LoRA), Renderer Registry, Audio Pipeline, QA Pipeline, Publishing Pipeline, Real-Time Streaming Avatar

**Discovery Capabilities (in spec):** Technical SEO, GEO (AI Search Optimization), Video SEO, Social Discovery, Keyword Intelligence, Backlink Authority, Competitor Intelligence, Reputation Monitoring, Pre-Publish Optimization

**Storage Intelligence Capabilities (in spec, SES-019A):** File Lifecycle Engine (policy-driven Permanent/Archive/Working/Temporary/Disposable classes), Predictive Storage Engine (pre-render safety check), Disk Watchdog (80/90/95% thresholds), Infrastructure Department service ownership, Event-driven storage via Event Fabric (SES-012)

---

## 8. Architecture Decisions (Key)

These are the major decisions already made. They are not up for re-evaluation without a formal ADR.

| Decision | What Was Decided | Why |
|----------|-----------------|-----|
| SQLite as primary database | SQLite with WAL mode for all server-side state | Zero-dependency, fast, local-first; migration to Postgres is a config change |
| Provider abstraction mandatory | No direct LLM SDK imports in business logic | Enables model swapping without rewriting agents |
| 7 LLM labels, not model names | `screening`, `standard`, `reasoning`, `multimodal`, `fast`, `long`, `private` | Agents specify intent, not model; routing is the platform's job |
| BMA Loop as the cognitive loop | 9-phase Observe→Understand→Reason→Plan→Execute→Verify→Evaluate→Learn→Update Memory | Gives agents introspective capability and a formal learning hook |
| SafetyHarness L1–L5 | Deterministic 5-level action classification | No guessing about approval requirements; audit trail automatic |
| Memory tiers L0–L5 | Working → Episodic → Semantic → KG → Org → Archive | Each tier has different lifecycle, access policy, and backend |
| AI Director above Storyboard | Script (what) → AI Director (how) → Storyboard (scenes) → Rendering | Separation makes each layer independently improvable |
| Renderer Registry (not hardcoded) | `BaseRenderer` interface; each backend is a registered adapter | New rendering engines (Runway, Kling, etc.) require only one new file |
| Discovery Engine (not "SEO") | SEO is one channel of seven; Discovery Engine covers all | Future-proof: AI Search, YouTube, Social, App Store all equally important |
| Dream Engine as highest-level orchestrator | Dream→Goals→Strategy→Projects→Departments→Agents→Execution→Evaluation→Learning→Dream | Long-horizon goal setting separated from tactical execution |
| Policy Engine for autonomy governance | Every autonomous action passes through policy evaluation | Broader than safety; governs spending, publishing, data access, deployment |
| Architecture freeze at SES-020 | After SES-020, new ideas become ADRs; existing SES documents evolve incrementally | Prevents constant redesign; lets engineering focus on delivery |
| Storage Intelligence as a formal platform capability | Infrastructure Department owns Disk Watchdog, Lifecycle Engine, Cleanup Engine, Archive Manager, Backup Manager, Cloud Sync, Predictive Storage Engine, Storage Analytics; no other department deletes files directly — they submit lifecycle requests | Prevents the Mac's SSD (or any render node) from filling silently; makes storage measurable and policy-driven instead of ad-hoc cleanup scripts |
| No render starts without a Predictive Storage Engine safety check | Studio Director estimates peak disk usage from the storyboard before entering production; postpones and triggers cleanup if unsafe | A render that runs out of disk mid-job wastes compute and produces nothing; better to know upfront |
| Storage events flow through the Event Fabric (SES-012), not direct calls | `render_started`, `upload_verified`, `cleanup_requested`, `storage_critical`, etc. are published/subscribed, not inline function calls between departments | Decouples "a render finished" from "someone must clean up" — keeps departments independent |
| ToolIntent as universal execution contract (Phase 3.1) | Every external action (connector call, LLM request, publish, email, webhook) is represented as an immutable ToolIntent | Enables idempotency, audit trail, approval workflow, and deterministic authorization; all connectors and agents go through ExecutionGateway, not direct API calls |
| ExecutionGateway as single execution authority (Phase 3.2) | All external actions route through one gateway that validates, authorizes, approves, manages credentials, executes, and records | Prevents authorization bypass; unifies audit trail; enables cost control and retry strategy |
| Immutable identity prevents authorization bypass (Phase 3.1) | Idempotency key computed once at creation; deep copy on input/output isolates external mutation; all approval decisions based on intent state at creation time | If authorization decisions could be invalidated by later mutation, the whole approval workflow becomes unreliable |

---

## 9. Active Priorities

**July 2026**

1. Complete SES-005 (AI Studio) — flagship document, unlocks Mr. Yeti autonomous production
2. Complete SES-010 (Discovery Engine) — ensures all published content is discoverable
3. Write SES-006 (Autonomous Engineering) — platform self-improvement capability
4. Write SES-007 (Mission Control) — single operational interface for all products
5. Write SES-011 (Security & Guardrails) — Policy Engine, prompt injection protection
6. Write SES-012 (Event Fabric) — NATS event bus, the nervous system of the platform

---

## 10. Known Limitations

These are honest gaps. They exist because the platform is being built incrementally.

| Limitation | Impact | Planned Fix |
|-----------|--------|------------|
| Nepali STT accuracy ~85% WER | Voice OS in Nepali is usable but imperfect | Fine-tune Whisper medium on Nepali corpus (Phase 3) |
| Knowledge Graph is SQLite adjacency tables (not Neo4j) | Graph queries are slower; complex traversals limited | Neo4j integration in Phase 4 |
| No vector search yet (Qdrant Phase 4) | L2 Semantic Memory uses keyword search only | Qdrant + nomic-embed-text in Phase 4 |
| Rendering is manual (no IC-LoRA automation yet) | Mr. Yeti character consistency not automated | AI Studio implementation (SES-005) |
| No live Discovery Engine | SEO is manual; no automated crawl/audit | SES-010 implementation |
| Single operator only | No multi-user, no org isolation | Phase 3 |
| No Policy Engine | Autonomy governance relies on SafetyHarness only | SES-011 |
| No Event Fabric | Departments communicate via API, not event bus | SES-012 |

---

## 11. The Three-Layer Operating Model

```
Layer 1: SES Documents (stable engineering specifications)
    docs/SES/v1.0/SES-001 through SES-020
    Authoritative. Versioned. Architecture decisions live here.
    Changes through formal ADR process after SES-020 freeze.

Layer 2: Living Operational Documents (evolve with the project)
    Brain.md        — Platform state, vision, priorities, decisions
    Business.md     — Business strategy, revenue model, market position
    Writing and Speaking Style.md — Communication rules for all agents and content

Layer 3: Codebase (the implementation)
    ~/SaathiAI/
    Implements what SES documents specify.
    Guided by Brain.md for priority and direction.
```

A coding agent should:
1. Read `Brain.md` to understand context and current priorities
2. Read the relevant SES document for the specific subsystem
3. Implement according to the spec, not according to assumptions

---

## 12. World Model Architecture (SES-017 preview)

The World Model is the shared external intelligence layer. Instead of every department running its own external data collection:

```
Internet
    │
    ▼
Research Engine (SES-016) — collects, crawls, synthesizes
    │
    ▼
World Model (SES-017) — shared, deduplicated external knowledge
    │
    ▼
Knowledge Graph (SES-003) — integrates world knowledge with platform knowledge
    │
    ▼
All Departments — access world knowledge without duplicate collection
```

**Benefits:** One source of truth for external world. No duplicate crawling. Consistent context across all agents. Cheaper inference (fewer external API calls).

---

## 13. Dream Engine Architecture (SES-018 preview)

The Dream Engine is the highest-level orchestrator — the part of SaathiAI that sets long-horizon goals and decomposes them into executable strategies.

```
Dream (long-horizon goal: "Mr. Yeti reaches 100k subscribers")
    │
    ▼
Goals (monthly subscriber growth target, content volume target)
    │
    ▼
Strategy (content mix, posting frequency, collaboration plan)
    │
    ▼
Projects (this month's 30 videos, SEO optimization sprint, channel audit)
    │
    ▼
Departments (AI Studio, Discovery Engine, Analytics)
    │
    ▼
Agents (execute production, publish, monitor)
    │
    ▼
Execution (videos published, analytics collected)
    │
    ▼
Evaluation (did we hit the goal? what worked?)
    │
    ▼
Learning (update strategy, update prompts, update KPIs)
    │
    ▼
Next Dream (revised or new long-horizon goal)
```

The Dream Engine is what transforms SaathiAI from a task executor into a long-term collaborator.

---

## 14. Policy Engine (SES-011 preview)

Every autonomous action passes through policy evaluation before execution. This is broader than the SafetyHarness (which classifies actions by safety level). The Policy Engine evaluates:

- **Authorization:** Is this agent permitted to take this action at all?
- **Budget:** Does this action exceed the spending limit?
- **Approval:** Does this context require a human to sign off?
- **Rate:** Has this action type been executed too many times recently?
- **Data access:** Is this agent allowed to access this data scope?
- **Time:** Is it appropriate to execute this at this time of day?

The Policy Engine is the governance layer that makes autonomous operation trustworthy. Without it, autonomous agents are powerful but ungoverned. With it, autonomy is bounded, auditable, and correctable.

---

## 15. SES Document Index

| Document | Title | Maturity |
|----------|-------|---------|
| [SES-000](docs/SES/v1.0/SES-000_MASTER_ROADMAP.md) | Master Roadmap | L3 |
| [SES-000A](docs/SES/v1.0/SES-000A_DOCUMENT_STANDARD.md) | Document Standard | L3 |
| [SES-000B](docs/SES/v1.0/SES-000B_GLOSSARY.md) | Glossary | L1 |
| [SES-000C](docs/SES/v1.0/SES-000C_ARCHITECTURE_PRINCIPLES.md) | Architecture Principles | L1 |
| [SES-000D](docs/SES/v1.0/SES-000D_CODING_STANDARD.md) | Coding Standard | L1 |
| [SES-000E](docs/SES/v1.0/SES-000E_REPOSITORY_INDEX.md) | Repository Index | L1 |
| [SES-000F](docs/SES/v1.0/SES-000F_CAPABILITY_REGISTRY.md) | Capability Registry | L1 |
| [SES-001](docs/SES/v1.0/SES-001_ARCHITECTURE.md) | Architecture | L3 |
| [SES-002](docs/SES/v1.0/SES-002_AGENT_SYSTEM.md) | Agent System | L3 |
| [SES-003](docs/SES/v1.0/SES-003_MEMORY_AND_KNOWLEDGE_GRAPH.md) | Memory & Knowledge Graph | L3 |
| [SES-004](docs/SES/v1.0/SES-004_VOICE_OS.md) | Voice OS | L3 |
| [SES-005](docs/SES/v1.0/SES-005_AI_STUDIO.md) | AI Studio | 🔄 Writing |
| [SES-006](docs/SES/v1.0/SES-006_AUTONOMOUS_ENGINEERING.md) | Autonomous Engineering | 📋 Queued |
| [SES-007](docs/SES/v1.0/SES-007_MISSION_CONTROL.md) | Mission Control | 📋 Queued |
| [SES-008](docs/SES/v1.0/SES-008_BUSINESS_OS.md) | Business OS | 📋 Queued |
| [SES-009](docs/SES/v1.0/SES-009_LEARNING_OS.md) | Learning OS | 📋 Queued |
| [SES-010](docs/SES/v1.0/SES-010_DISCOVERY_ENGINE.md) | Discovery Engine | 🔄 Writing |
| [SES-011](docs/SES/v1.0/SES-011_SECURITY_GUARDRAILS.md) | Security & Guardrails | 📋 Queued |
| [SES-012](docs/SES/v1.0/SES-012_EVENT_FABRIC.md) | Event Fabric | 📋 Queued |
| [SES-013](docs/SES/v1.0/SES-013_COMPLIANCE_GOVERNANCE.md) | Compliance & Governance | 📋 Queued |
| [SES-014](docs/SES/v1.0/SES-014_PRODUCT_FRAMEWORK.md) | Product Framework | 📋 Queued |
| [SES-015](docs/SES/v1.0/SES-015_FINANCIAL_INTELLIGENCE.md) | Financial Intelligence | 📋 Queued |
| [SES-016](docs/SES/v1.0/SES-016_RESEARCH_ENGINE.md) | Research Engine | 📋 Queued |
| [SES-017](docs/SES/v1.0/SES-017_WORLD_MODEL.md) | World Model | 📋 Queued |
| [SES-018](docs/SES/v1.0/SES-018_DREAM_ENGINE.md) | Dream Engine | 📋 Queued |
| [SES-019](docs/SES/v1.0/SES-019_DEPLOYMENT_INFRASTRUCTURE.md) | Deployment & Infrastructure | 📋 Queued |
| [SES-020](docs/SES/v1.0/SES-020_FUTURE_ROADMAP.md) | Future Roadmap | 📋 Queued |

---

## 16. Recently Accepted Decisions

| Date | Decision | Rationale |
|------|----------|----------|
| 2026-07-02 | AI Director placed above Storyboard Engine | Script (what) / AI Director (how) / Storyboard (scenes) separation makes each layer independently improvable |
| 2026-07-02 | SES-010 renamed to Discovery Engine | "SEO" is one channel of seven; platform must cover AI Search, YouTube, Social, App Store equally |
| 2026-07-02 | Renderer Registry mandated for AI Studio | New rendering engines require only one new adapter file; no changes to Studio Director or pipeline logic |
| 2026-07-02 | Dream Engine as highest-level orchestrator | Long-horizon goal setting must be separated from tactical department execution |
| 2026-07-02 | Policy Engine added as SES-011 | Autonomy governance broader than safety; covers spending, publishing, data access, timing, rate |
| 2026-07-02 | World Model as shared external intelligence layer | One source of truth for external world; prevents duplicate crawling across departments |
| 2026-07-02 | Architecture freeze planned after SES-020 | After SES-020, all new ideas become ADRs; SES documents evolve incrementally |
| 2026-07-02 | Brain.md + Business.md + Writing Style.md as three living documents | Operational guidance lives here; SES documents are stable engineering specs |

---

## M5 — Investment Intelligence Department (v0.4.0-finance, 2026-07-03)

The financial specialization of the AI-OS: a governed decision-support platform where every
recommendation is explainable, every execution audited, every outcome preserved, and every
completed trade feeds learning. Built as a chain of deterministic engines (AP-17), all
side-effects injected (AP-12): Research Department (+ Research Confidence Framework) →
Opportunity Intelligence (+ Opportunity Memory) → Investment Pipeline (InvestmentCase) →
Portfolio Intelligence (+ Impact Simulator + Capital Reserve Engine) → Execution Layer
(immutable Intent, broker-independent connectors, paper-first, idempotent recovery) → Trade
Journal (append-only financial Platform Memory) → Investment Learning Runtime (proposes into
M2, never mutates) → Financial Mission Control (consumer) → Executive Financial Integration
(+ Cross-Department Priority Engine). Certified in `docs/M5_INTEGRATION_SPRINT.md`.

**M5 principle (AP-14 applied to capital):** no trade bypasses human approval or the Governance
Engine — financial actions are L4, and an ExecutionIntent can only be born from an approved,
executable InvestmentCase. Learning proposes; the human disposes.

---

*Last updated: 2026-07-03*
*Next update: After the v0.4.0-finance stabilization window (paper-trading + live business data)*

---

## Auto-Repair Loop (reliability spine)

SaathiOS repairs its own recoverable failures through `saathi/repair/` — a
production-safe pipeline: **Failure → Evidence → Classify → Root cause → Policy
→ Rollback point → Minimal patch → Focused tests → Full suite → Verify runtime
→ Local commit → Report**. See `AUTO_REPAIR_LOOP.md`.

- **Failure classification** — 21 categories (IMPORT_ERROR … EXECUTION_BYPASS …
  CONNECTOR_AUTH_ERROR … EVENT_BUS_ERROR … UNKNOWN); each carries confidence,
  subsystem, and suspected files.
- **Evidence model** — read-only capture. Env vars recorded as *presence*
  booleans, never values. All free-text redacted for secrets on ingest.
- **Repair policy** — Level 0 diagnose-only, Level 1 safe-local (edit + local
  commit), Level 2 approval-required, Level 3 prohibited (push/deploy/credential/
  send/trade/history-rewrite — never autonomous).
- **Verification ladder** — focused → subsystem → full suite → server import →
  route-count smoke. Success = target recovered AND no new regressions AND route
  count intact AND secret scan clean; otherwise auto-rollback.
- **Stopping conditions** — secret risk, unsafe git state, external
  credential/payment/deploy needed, 2 failed attempts per fingerprint, low
  confidence, unknown root cause. Never loops infinitely.
- **Rollback** — pre-repair HEAD recorded per incident; unrelated dirty work
  blocks auto-repair; restore via `saathi repair rollback <id>`.
- **Anti-hallucination** — task-execution repairs verify the execution *trace*,
  not the final text. No tool call → "the task was not executed." Missing
  credentials → "connector is not connected or authenticated." Never fabricates.

### Reliability extensions (Repair 3)

- **Critical regression manifest** (`saathi/repair/critical_checks.json`): 11
  blocking checks — event bus API/emission/stream, studio tracking, intake
  tagging, BFF contract + dream pct + regression pack, execution gateway +
  finance trade layer, repair self-tests — plus server import + route count.
- **Quality records**: baseline (`data/repair_baseline.json`, updated only
  after full-ladder success), known-failure registry
  (`data/known_failures.json`, detects new/recurring/resolved/returned/
  signature-changed), journal (`artifacts/repairs/`, secret-redacted JSON+MD).
- **Bounded loop modes**: inspect / diagnose / repair --test / loop
  --max-cycles (1..10, fingerprint no-progress detection) / report / critical.
  Exit codes 0-7 documented in AUTO_REPAIR_RUNBOOK.md.
- **Canonical dream progress**: `financial_mission_control.dream_progress_pct`
  — the single source of truth; percentage semantics (1.0 == 1% of
  DREAM_TARGET), defensive against zero/negative/NaN inputs.
- **CEO Home DI rule**: explicit `Signals` drive the payload (tests/previews);
  no Signals → real recorded Mission revenue. Regression from f80a37f fixed.

---

## M8 — Saathi Chat (central intelligence interface)

`saathi/chat/` — every other subsystem integrates through this chat.

**Architecture (data flow):**
```
user text → ChatEngine.send()
  → memory retrieval (related conversations + mission knowledge, automatic)
  → attachment RAG (chunk scoring → context + citations)
  → project context (project_ref resources)
  → ToolIntent → ExecutionGateway (validate/authorize/risk/approve/queue)
  → ChatLLMAdapter → Model Router (Anthropic/OpenAI/DeepSeek/Qwen/GLM/
    Groq/Gemini/Ollama — provider-extensible)
  → sanitize → evidence → persist (message + execution + citations)
  → rolling summary + auto-checkpoint every 8 messages
```
Models are never called directly by the API layer; every inference and tool
call is a gateway-audited ToolIntent with an execution record.

**Store** (`data/chat.db`, 11 normalized tables): conversation, message
(edit chains = version history), attachment, memory_link, citation,
execution, tool_invocation, summary, project_ref, agent_run, checkpoint.
Soft delete + restore — no conversation is ever hard-lost; checkpoints are
restorable full snapshots.

**API** `/api/v1/chat/*` (auth inherited): conversations CRUD/search/
restore, messages (send + SSE streaming, edit-and-resend, regenerate,
versions, citations), attachments, tools, checkpoints/restore, agents.

**Agents** (Layer 9): planner/researcher/coder/reviewer/architect/writer/ceo
— role-prompted runs recorded in agent_run; delegate() chains agents with
provenance (delegated_by).

**Honesty invariants:** LLM failure → "The task was not executed — …" (never
fabricated replies); unknown tools → status=blocked with reason (never faked
results).

**UI:** `saathi-os/app/chat` — sidebar (search/pinned/recent/folders/project),
streamed messages, agent selector, execution timeline + memory links +
agent runs + checkpoints panel.

**Critical manifest:** `chat.saathi_chat_m8` → tests/test_chat.py (blocking).

---

## M9 — Unified Memory Engine

`saathi/memory/engine/` — production memory behind the M8 ChatEngine's stable
interface. Reuses `platform.py` scopes/retention + `evidence.find_contradictions`.

**Lifecycle:** observe → extract (bounded, deterministic) → classify → store →
embed → link → retrieve → rank → reinforce → decay → forget.

**Retrieval:** hybrid = semantic (local numpy embeddings, real cosine,
vectorized matmul) + keyword + recency + importance + confidence + context +
feedback, one canonical ranking function with per-result explanation and MMR
diversity. Namespace list = the privacy firewall (retrieval only reads listed
scopes). Graph expansion (1-hop relations) complements vectors.

**Embeddings:** provider-neutral. Default = `LocalDeterministicEmbedder`
(numpy, dependency-free, deterministic) → semantic works offline. ST / Ollama
adapters share the contract and `available()`-gate; cloud adapters are the
extension point. `embedding_version` tracked; `reindex` is bounded + resumable.

**Memory types:** working, conversation, episodic, semantic, procedural, user,
business, project, agent, document. Schema: 14 normalized tables in
`data/memory.db` (memory_item/version/source/embedding/relation/access/
feedback/policy/namespace/summary/conflict/tombstone, retrieval_run/result).

**Lifecycle guarantees:** delete = tombstone + embedding drop → never
retrievable (restorable re-embeds). Conflicts (opposing polarity, same topic)
flagged, never auto-resolved. Supersede preserves history. Decay spares pinned
+ semantic/platform_wisdom retention. Stored content is untrusted data with
provenance — never executed (prompt-injection safe).

**Chat integration:** `MemoryEngine.retrieve_for_chat` feeds ChatEngine before
model execution (scope-checked, thresholded, token-budgeted, with citations);
user turns are observed back into memory (bounded extraction). ExecutionGateway
enforcement unchanged; no direct model calls.

**API** `/api/v1/memory/*` (auth inherited): list/search/create/item/update/
pin/feedback/delete/restore/conflicts/reindex/runs/health.
**CLI** `python -m saathi.memory.cli`: inspect/search/health/reindex/conflicts/
stats/export/decay (read-only cmds don't mutate; exit codes 0/1/2).
**Manifest:** `memory.engine_m9` (blocking).

---

## M10 — Multi-Agent Runtime

`saathi/agent_runtime/` — bounded, observable, gateway-only agent orchestration.

**Flow:** objective → strategy → task DAG → memory-scoped agent turns (via
ExecutionGateway) → verify (evidence) → independent review → bounded retry →
checkpoint → outcome. No agent calls a provider/connector/terminal/FS directly.

**8 agents** (config-driven, versioned): planner, researcher, architect,
builder, reviewer, executor, writer, ceo. Each has allowed/denied tools, memory
scopes, risk ceiling, budgets, delegation permissions, output contract.
Planner + CEO cannot self-approve.

**State machine** (durable, validated): created→planning→awaiting_approval→
approved→queued→running→delegated→verifying→reviewing→completed + paused/
cancelled/timed_out/blocked/failed/rolled_back/partially_completed. Illegal
transitions raise; terminal states have no exits.

**Risk model** 0–4 (maps to gateway L0–L4): read-only / local-reversible /
local-mutation / external-side-effect / high-impact. Risk ≥ local-mutation
needs explicit user approval; high-impact stays manual-only. Denied at
tool-check when over an agent's ceiling.

**Delegation:** narrowing-only permissions (child ⊆ parent tools/scopes/risk);
limits on depth (3), children/agent (4), total agents (12), repeats. No loops.

**Budgets:** tokens/cost/wall/steps/tool-calls/retries/delegation-depth/
artifacts/parallel — runs stop safely + report partial. **Retry:** transient +
progress + budget only; no-progress fingerprint stops.

**Memory:** M9 scoped retrieval per agent/task (never widens). **Gateway:**
every action a ToolIntent; a static regression test scans runtime for direct
provider/subprocess bypasses. **Events:** `agentrun.*` on the fabric bus.

**Schema:** 19 tables in `data/agent_runtime.db`. **Strategies:** single/build/
architect_build/document/business/broad_research (config-driven).
**API** `/api/v1/agents/*`, **CLI** `python -m saathi.agent_runtime.cli`,
**Chat:** `ChatEngine.start_orchestration` (multi-agent activates only when
selected/justified; simple asks stay single-turn). **Manifest:**
`agents.runtime_m10` (blocking).

---

## M12 — Voice OS

`saathi/voice_os/` — real-time speech interface for Saathi Chat. Voice never
calls a model provider or tool directly: every final transcript resolves
through `saathi.chat.engine.ChatEngine` (Solo) or `ChatEngine.start_orchestration`
(Team, the M10 Orchestrator), and voice approvals resolve through the same
`Orchestrator.approve()` ownership/expiry-checked path the M11 UI buttons use.

**Canonical flow:** microphone (browser) → VAD → STT → transcript pipeline
(dedupe/normalize/command-detect) → ChatEngine/Orchestrator → response
segmentation → TTS → playback. Barge-in: new speech immediately cancels
`speechSynthesis` playback client-side and records `stop_latency_ms` server-side.

**Session/turn model:** 14-state session state machine (created…completed/
cancelled/failed, validated transitions, illegal raises); voice_turn persists
transcript/response/execution/agent_run linkage. Raw audio is **never**
retained by default — `retain_raw_audio` is opt-in per session.

**Providers (provider-neutral, real-first):**
- STT: `DeterministicSTT` (test) · `FasterWhisperSTT` (**real**, installed,
  verified via a genuine TTS→STT round trip in tests) · `BrowserPassthroughSTT`
  (carries the browser's own real webkitSpeechRecognition output).
- TTS: `DeterministicTTS` (test) · `SayTTS` (**real**, macOS `say`, verified
  producing real audio bytes) · `BrowserSpeechSynthesisTTS` (marker — real
  synthesis happens client-side via `window.speechSynthesis`).
- Cloud adapters (OpenAI/ElevenLabs-compatible) are contract-ready extension
  points only — no keys in this environment, never claimed as tested.

**Commands:** bounded exact-phrase recognition (stop/pause/resume/repeat/
cancel/approve/deny/mute/mode-switch/…) — confidence-gated, never fuzzy;
approval commands still require the full ownership+expiry check, never a
keyword shortcut.

**Segmentation:** strips markdown/code/tables/citations/URLs before TTS;
splits on sentence/clause boundaries within a bounded length.

**API** `/api/v1/voice/*` (HTTP/SSE — no WebSocket; STT/TTS happen
client-side so no bidirectional low-latency channel is needed). **CLI**
`python -m saathi.voice_os.cli` (labels real-adapter vs deterministic-fallback
test results explicitly). **UI:** collapsible `VoiceControl` in Saathi Chat
using real `SpeechRecognition`/`SpeechSynthesis` — optional, never replaces
text chat.

**Backend freshness (Phase 24):** `GET /api/v1/system/version` — the M11 live
smoke test discovered a days-old backend process serving pre-M8 code; this
endpoint exposes commit/process-start/route-count so staleness is detectable.

**Manifest:** `voice.voice_os_m12` (blocking).

**Honesty note:** live browser microphone permission and a real spoken
utterance were not exercised in this sandboxed session (no `getUserMedia`
grant available to the automation). Real local adapters (faster_whisper,
macOS `say`) and the full deterministic pipeline were genuinely tested.

---

## M13 — AI Studio (end-to-end content workflows)

`saathi/studio_os/` — idea → reviewed, exportable, optionally-published content.
Reuses M10 (orchestration + approvals), M9 (memory/learning), M12 (voice/TTS),
ExecutionGateway (all provider/FFmpeg calls), the event bus. NOT a new
orchestrator/memory/approval/agent system.

**Flow:** objective → M10-orchestrated planning/scripting (real ChatEngine) →
real local media stages → versioned checksummed artifacts → review → approval →
export/publish. Every stage persists an artifact + status + cost.

**Project state machine:** 15 states (draft…completed/partially_completed/
cancelled/failed/archived, validated transitions, illegal raises).

**Artifacts:** 25 types, versioned (new supersedes prior latest of same
type+stage), checksummed; media binaries on disk (storage_uri), never in SQLite.

**Real local providers (verified):** Pillow images (genuine PNG), FFmpeg
render/probe/thumbnail/mux (gateway-routed, argument-safe list form — no shell
injection), macOS `say` narration (shared with M12). Cloud image/video
(Flux/Veo/HeyGen/ComfyUI) + real publishing = honest deterministic/dry-run;
capability matrix marks them configured:false, never "tested."

**Disk safety (core, not optional — user has hit disk exhaustion):** real
`shutil.disk_usage` preflight HARD-GATES every generation (refuses if free space
would drop below a 5GB margin or breach the project quota); checksum dedup,
partial/temp cleanup, path confinement (traversal rejected).

**Budget:** dry-run estimate + hard stop — a generation is refused before it
exceeds the project budget; local providers cost $0.

**Publishing:** approval-gated + verified-artifact-gated; idempotency keys stop
duplicates; `live=True` with no configured connector is refused honestly (no
fabricated receipt/URL); dry-run records status='dry_run' with no fake URL.

**Studio agents:** 7 roles (content_strategist/script_writer/storyboard_agent/
visual_director/seo_agent/brand_reviewer/publisher) registered INTO the M10
registry; publisher is EXTERNAL_SIDE_EFFECT + requires_approval.

**API** `/api/v1/studio-os/*` (distinct from the legacy /api/v1/studio
dashboard). **CLI** `python -m saathi.studio_os.cli` (render-smoke does a REAL
ffmpeg render; read-only cmds never mutate; publish enforces approval).
**Manifest:** `studio.studio_os_m13` (blocking).

**Honesty note:** the full short-video workflow was verified end-to-end
producing 11 real artifacts (real PIL image → real FFmpeg video → real say
narration → real muxed final_video → real extracted thumbnail, all ffprobe-
verified). Cloud media generation, real social publishing, and live browser
Studio UX were NOT verified (no keys/accounts/getUserMedia in this environment).

---

## M13.5 — Production Hardening (ops toolkit)

`saathi/ops/` — operations toolkit, read-only by default, mutation explicit:
- **identity.py**: safe runtime identity (commit/branch/api_version/schema_versions/
  route_manifest); `compatible()` lets the frontend detect a stale/incompatible
  backend (the M11 bug). `/api/v1/system/version` (+ `/version/compat`).
- **config_check.py**: env validation, secrets shown only as PRESENT/ABSENT,
  flags a tracked firebase key.
- **storage.py**: global disk report + thresholds (ok/warning/block/critical);
  preview-first cleanup (never deletes user artifacts).
- **db_integrity.py**: real `PRAGMA integrity_check` + fk_check on all 5 app dbs.
- **backup.py**: REAL checksum-verified backup (dbs + redacted config manifest;
  excludes secrets/media); restore into an ISOLATED dir (refuses live-dir
  overwrite + path-traversal archives); verify re-checks checksums + integrity +
  schema. **Real drill passed**: 5 dbs, all checksums match, all integrity ok.
- **release_gate.py**: `release-check` with stable exit codes 0-12; runs
  storage/config/db/**backup+restore**/strong-credential-secret-scan gates.
- **process.py**: backend listener + stale-process detection (running commit vs
  working tree); never kills unknown processes.
- **cli.py** / `python -m saathi.ops`: status/health/config-check/storage/cleanup/
  db-check/backup/restore/verify-restore/release-check/identity.

**Frontend**: AI Studio workspace (`/studio-os`) on the real /api/v1/studio-os/*
(no mock data); STUDIO_OS dock entry. Version-mismatch compat endpoint.

**Manifest**: `ops.hardening_m13_5` (blocking). Docs: readiness matrix +
release gates + security + DR + deploy + perf + ops runbook.

**Verdict: STAGING READY.** Env-blocked (honest): authenticated browser
workflows, live approval click, cloud media providers, real social publishing,
real staging deploy + live rollback. Everything locally verifiable is
implemented, tested, and (backup/restore) recovery-proven.

---

## M14 — CEO OS (unified operating + decision layer)

`saathi/ceo/` — orchestrates existing systems; NOT a separate AI brain, NOT a
new dashboard fork. Reuses M10 (mission execution + approvals), M9 (memory),
M13 (studio), ExecutionGateway, event bus, and the verified BFF/`dream_pct`
contracts (both now in the critical manifest so they can't regress).

**Source-of-truth decisions:** canonical entities live in `data/ceo_os.db`
(business/goal/kpi/metric_observation/decision/risk/opportunity/budget/
financial_entry/review/alert/brief). Missions are NOT a new entity — a CEO
mission IS an M10 orchestration run.

**Evidence requirement:** every value carries an `EvidenceTier` — observed /
calculated / inferred / forecast / recommended / unavailable. A recommendation
is never presented as a verified fact. A KPI with no observation returns
UNAVAILABLE, never a guessed value.

**Deterministic priority rules:** `priority.score` is a transparent weighted
sum with a per-factor explanation (`PRIORITY_WEIGHTS`). An LLM may only
recommend weight adjustments; deterministic logic controls execution.

**KPI percentage convention:** reuses the verified `dream_progress_pct`
(1.0 == 1% of DREAM_TARGET); regular KPIs use value/target*100. Ratio-vs-pct
regression guarded by tests.

**Financial semantics:** actual / estimated / forecast / unknown are SEPARATE
states — an estimate is never summed into actual revenue. Personal vs business
scopes are explicitly labeled.

**Authorization boundaries:** CEO Agent (M10 `ceo`, READ_ONLY, can_self_approve
=False) only PROPOSES decisions (status=proposed); protected states
(approve/reject/implement) require an authenticated user via the API — an agent
has no user identity to reach them. No CEO-direct execution; no self-approval;
no fabricated metrics.

**API** `/api/v1/ceo/*` (routes 304→305). **CLI** `python -m saathi.ceo.cli`
(read-only lists + brief; mission/decision/budget mutations are API-only,
authz-gated). **Frontend**: CEO OS workspace `/ceo` (real API, evidence tiers
visible, no mock data). **Manifest**: `ceo.ceo_os_m14` + `bff.contract_pack`.

## M15 — Universal Connector Platform + Spec-Driven Governance

`saathi/connectors/platform/`: one governed integration layer. Canonical
connector/tool/result models with a non-downgradable risk floor (0–4),
provider-neutral capability catalog, registry seeding 11 connectors / 28 tools
with **honest integration-status labels** (live-tested | deterministic-adapter-
tested | contract-ready | environment-blocked). Credential **references** only
(metadata; secrets resolved in-process, redacted from errors). Durable store
`data/connectors.db` (accounts, cred refs, executions with unique idempotency,
approvals bound to the exact-action input hash, webhook dedup, sync checkpoints,
rate buckets, failures).

**ExecutionEngine is the sole execution boundary** — every action routes through
the ExecutionGateway (governance pass recorded as `provenance.gateway_ref`),
then connector-native enforcement: lifecycle gate (only executable states),
approval binding (risk ≥ 3, single-use, expiring; risk 4 manual-only),
idempotency replay, rate limits, failure classification, and the hard rule that
**uncertain / non-idempotent failures never auto-retry**. Health platform
(no creds → environment-blocked, never faked green), webhook platform
(HMAC + freshness + replay defense), resumable checkpointed sync, and MCP tools
ingested as **untrusted** connectors (risk clamped UP, gateway-routed, cannot
self-approve).

**Objective B — governance.** Native offline Spec Kit wrapper (NOT vendored;
gstack is a SaaS starter, not Spec Kit): `.specify/memory/constitution.md` (v1.0,
8 articles), `.specify/presets/saathios/`, `saathi/specs/{traceability,cli}.py`
(`python -m saathi.specs.cli version|health|init|validate|converge`),
`specs/m15-universal-connectors/` (spec/plan/tasks/traceability.json/convergence).
Convergence gate: every requirement mapped to an artifact + a passing test.
**M15 verdict: CONVERGED (19/19), DEVELOPMENT READY** — core spine test-green;
live authenticated connector workflows unverified (no creds), connector API + UI
remain. Ops: `connectors.db` in backup/db-integrity APP_DBS, schema `connectors:m15`,
critical manifest → m15. Tests: `tests/test_m15_connectors.py`, `tests/test_m15_specs.py`.

## M15.1 — Connector Platform Staging Completion

Promotes M15 toward STAGING READY without rebuilding the core. Adds the
authenticated REST API `saathi/connectors/platform/api.py` mounted at
`/api/v1/connectors/*` (owner-scoped via `request.state.user_id`, same auth as
CEO/chat routers): registry/capability/tool/account/health/metrics/execution/
approval/webhook/sync routes. Every route enforces authentication + connector/
account ownership; cross-user access → 403; **raw secrets never returned, never
in error bodies**; all execution flows through the ExecutionEngine (gateway
provenance on every result). New mutation paths avoid legacy collisions
(`/accounts/connect`, `/executions`).

**Credential hardening** (`credentials.resolve_for_account`): validates owner +
connector + scope BEFORE any backend lookup, typed `CredentialScopeError`,
revoked/expired fail immediately, minimal secret lifetime; wired into the engine
secret getter. **Integration funnel** (`integration.py`): the ONE surface Chat/
M10 Agents/CEO OS/Voice use — `describe_action` (surfaces exact risk/approval for
spoken confirmation), `run` (gateway-routed; agents can't self-approve),
`ceo_evidence_tier` (a connector FAILURE stays *unavailable*, never faked to
zero/success). **Migration** (`migration.py`): legacy ledger + `scan_direct_calls`
(0 violations in the platform package) guarding Constitution Art. I. **UI**:
`/connectors` rewritten on the real platform API with honest integration-status
states, approval panel bound to exact action, execution history, env-blocked
states — Next build passes (34/34 pages, `/connectors` compiled). **Observability**:
`store.metrics()` over a genuine sample (no fabricated p95).

Ops: route manifest → m15, critical manifest → m15.1 (+12 blocking checks).
Tests: 33 new (`test_m15_1_{api,integration,live_local,ui}.py`). Evidence honesty:
local_fs/local_git **LIVE TESTED**; GitHub/browser/sqlite deterministic; gmail/
gcal/gcontacts/telegram/publishing **environment-blocked** (no creds, not faked);
deploy contract-ready; interactive browser smoke environment-blocked (build
verified only). **Verdict: STAGING READY** for the local + governance surface;
cloud live-mutation + browser smoke remain environment-blocked pending creds.
Note: gstack is an optional external Claude/Codex dev-workflow toolkit, not a
Spec Kit implementation or SaathiOS dependency.

## M15.2 — Agent Security Red-Team Harness

`saathi/security/redteam/`: SaathiOS-owned, isolated, **deterministic** adversarial
harness proving M8–M15.1 boundaries hold under attack. Deterministic probes are
**authoritative**; a judge/LLM opinion never confirms or clears a finding.
HackAgent (Apache-2.0) integrated as an **optional, pinned (0.3.0), local-only,
cloud-sync-off** dev-security dependency — advisory only, never on the production
path; absent here → honestly `environment_blocked`. Config guards: production/
public targets **blocked** (in-process/loopback only), secrets redacted from every
artifact, budgets bound attacks/time/tokens.

Corpus `security/redteam/attacks/corpus.yaml` (v1, 20 attacks) binds 1:1 to
deterministic probes (`probes.py`) that drive real attacks against isolated
in-process targets (temp connectors.db, isolated user vs attacker identity):
prompt/indirect injection, goal hijack, tool misuse, approval bypass (changed-
input/replay/forged), privilege/delegation (agent no self-approve), memory
poisoning, cross-user isolation, secret extraction, MCP clamp, webhook replay,
unsafe retry, CEO evidence. Finding model (deterministic vs advisory-judge),
severity, baseline + compare, sanitized report + release-gate (blocks on
Critical/High), CLI (`python -m saathi.security.redteam.cli
health|list-attacks|run|report|baseline|compare`), read-only report API
`/api/v1/security/redteam/*` (prod-disabled, authenticated).

**Found + fixed a real CRITICAL**: ExecutionEngine did not verify account
ownership — the M15.1 API did, but the funnel/agents call the engine directly, so
cross-user execution succeeded (probe ISO-001). Root-cause fix in
`execution.py` (ownership + account/connector match enforced in the engine);
re-run 20/20 hold, regression-protected, no M15/M15.1 regression. Ops: critical
manifest → m15.2 (+11 blocking checks). Tests: `test_m15_2_{security,harness}.py`.
Spec Kit `specs/m15-2-agent-security/*` + threat-model (STRIDE) CONVERGED 15/15.
**Verdict: SECURITY STAGING READY** — deterministic controls green, 0 Critical/High
confirmed, remediation regression-tested; adversarial-model (HackAgent), live
browser/Voice, and live cloud connector attack paths remain environment-blocked
(needed for SECURITY PRODUCTION READY).

## M15.3 — Enterprise Connector Platform

Hardened M15 into an enterprise integration platform (no parallel framework),
`saathi/connectors/platform/enterprise/`:
- **Scope engine** (`scopes.py`): one evaluator, EXACT scope match, structured
  reason codes (CONNECTOR_SCOPE_MISSING, ACCOUNT_REVOKED, MANUAL_ONLY_RISK4…),
  wired into `ExecutionEngine` BEFORE approval. Enforced for accounts that track
  scopes (real OAuth); local/deterministic accounts pass (other gates still apply).
- **OAuth 2.0 + PKCE lifecycle** (`oauth.py`): begin (state+PKCE+nonce), callback
  validation (constant-time state, exact redirect-URI, same-user binding),
  scope-reduction detection, **refresh must not widen scopes**. Live token
  exchange/refresh injectable → environment-blocked here (no IdP). Raw tokens
  never persist on the flow.
- **Resilience** (`resilience.py`): circuit breaker scoped connector:account:
  operation (one failing account doesn't trip the connector; half-open recovery),
  layered rate limiter (user/connector/account/operation). Breaker wired into engine.
- **Error taxonomy** (`errors.py`): 21 stable categories → retryable/user_action/
  operator_action, redacted detail.
- **Live-validation** (`live_validation.py`): modes contract/deterministic/sandbox
  vs live_read_only/reversible/side_effect; CI runs safe only; live credentials-
  gated; honest verification matrix (configured != healthy != live-tested).

Canonical execution path unchanged: ownership (M15.2) → scope engine → circuit
breaker → risk/approval binding → gateway → adapter → evidence. Red-team expanded
to **29 attacks (29/29 hold)**: OAuth state substitution / wrong-user callback /
refresh scope widening, account substitution after approval, missing-scope denial,
circuit breaker, SSRF path traversal, provider-error secret leak, backup secret
exclusion. **Found + fixed a real CRITICAL** (SECRETLEAK-001): redactor stopped at
"Bearer", leaking the token; now consumes `Bearer <token>` + token shapes
(sk-/ghp_/xoxb-/AKIA). Ops: critical manifest → m15.3 (+10 checks). Tests:
`test_m15_3_enterprise.py` (21). Spec Kit CONVERGED 12/12. **Verdict: CONNECTOR
STAGING READY** — enterprise controls deterministically verified + red-team-tested,
ownership/approval intact, 0 Critical/High; live OAuth/refresh/provider + browser
env-blocked (needed for CONNECTOR PRODUCTION READY). Incident runbook:
docs/runbooks/CONNECTOR_INCIDENT_RESPONSE.md.

## M16 — Unified Control Center

`saathi/control_center/`: ONE read/observation + safe-control layer over the
canonical subsystems. **Not an execution engine** — never calls providers, never
writes subsystem stores, never bypasses ExecutionGateway; mutations are rendered
as ActionDescriptors pointing ONLY at canonical subsystem APIs (proven:
test_control_api_is_read_only, test_actions_point_at_canonical_apis).

`aggregator.py`: bounded aggregation; each subsystem read wrapped in `guarded()`
→ `Cell{value, source, status(ok|degraded|unavailable), observed_at,
degraded_reason, age_sec}`. One failing source degrades to a typed cell, never
crashes the page. Overview composes real cells: connectors health, security
red-team release-gate + baseline, connector metrics, release gates, event bus,
live-validation matrix. Attention items ranked (critical→info), real + actionable.
`search.py`: federated, **owner-scoped** (accounts/approvals/executions filtered
by caller; connectors/operations are public capability info), secret-free.
`api.py`: `/api/v1/control/*` READ-ONLY (GET/HEAD), authenticated, owner-scoped;
partial failure degrades, never 500. `cli.py` read-only. UI `/control` on the
real API with source+freshness, honest degraded/unavailable states, bounded
refresh paused when tab hidden.

Canonical rule: Control Center holds NO source of truth; every value carries its
source + freshness. Ops: route manifest → m16, critical manifest → m16 (+7
checks). Tests: `test_m16_control_center.py` (11, incl. cross-user search
isolation + no-bypass). Spec Kit CONVERGED 10/10. **Verdict: CONTROL CENTER
STAGING READY** — Overview/search/governance real-data-backed, owner-scoped,
honest on partial failure, cannot bypass subsystem policy. Interactive browser
verification, live provider data, and real-time streaming remain environment-
blocked (bounded polling is not claimed as streaming) — required for CONTROL
CENTER PRODUCTION READY.

## M17 — Universal Computer Agent

`saathi/computer_agent/`: SaathiOS operates desktop apps + browsers by registering
computer operations as M15 connector tools — **no new execution engine, no
app-specific code**. Every action flows through ExecutionEngine → ExecutionGateway
→ M15.2 ownership → M15.3 scope/circuit → risk/approval → evidence.
- perception.py: canonical UIElement + Screen model (one schema for all providers).
- providers.py: provider abstraction (Playwright/CDP/accessibility/OCR/vision),
  deterministic default; **live desktop control environment-blocked** (importable
  != verified; honestly reported; SAATHI_COMPUTER_LIVE gate).
- operations.py: vision/desktop/browser_agent connectors with EXPLICIT risk —
  read L0, click/type/scroll L2, upload/download/send L3 (approval), delete/
  purchase/run_binary L4 (manual-only) — + post-action **visual verification**
  (unverified → uncertain; never assume success).
- replay.py: sanitized replayable timeline (password/OTP/token/secret → [REDACTED]).
- agent.py: runner via the M15 funnel (describe-before-act + gateway-routed step).
Red-team +5 (34/34 hold): destructive-needs-approval, password-not-in-replay,
agent-no-self-approve-purchase, cross-user desktop isolation, never-assume-success.
Control Center Computer Center cell + /api/v1/control/computer (live_desktop_control
= environment_blocked). Ops: route+critical manifest → m17. Tests:
test_m17_computer_agent.py (12). Spec Kit CONVERGED 10/10. **Verdict: DESKTOP
STAGING READY** — perception→gateway-routed execution→verification→sanitized-replay
spine deterministically verified + red-team-tested, no bypass. Live desktop/browser
actuation on real authenticated apps remains environment-blocked (needed for
DIGITAL WORKER PILOT/PRODUCTION READY).

## M17 hardening — computer-agent security boundary

session.py (ComputerSession consent boundary: auth user + device + allowed apps/
origins/file-roots + risk ceiling + expiry + emergency stop; **no control without
a live session**), intent.py (ComputerActionIntent + InteractionLayer API>DOM>
accessibility>OCR>coordinate; coordinate never default when a structured element
exists; mutation requires postcondition; sensitive args redacted), sensitive.py
(sensitive-field detection + pause-for-user, no capture; **CAPTCHA/MFA/biometric
bypass refused**), policy.py (origin/app allow-lists, download/upload/file-root
confinement with traversal + symlink-escape rejection, shell + AppleScript
injection guards; page/AX text is untrusted data), recovery.py (obstacle
classifier: CAPTCHA/MFA/login/permission → pause_for_user; irreversible+uncertain
→ stop_uncertain; no budget → stop_no_progress). Agent enforces active-session +
allow-lists + sensitive-pause before every action; emergency_stop(). Control
Center /control/computer page (honest provider availability). Red-team **46/46**
(+12: page-inject, traversal, symlink, AppleScript/shell, CAPTCHA/MFA, sensitive-
not-recorded, emergency-stop, app-allowlist, coord-not-default). Ops: critical
manifest m17 (+10 hardening checks). Tests: test_m17_hardening.py (21). Spec Kit
CONVERGED 17/17. **Verdict: COMPUTER AGENT STAGING READY** — perception → session-
gated gateway-routed execution → verification → sanitized replay, with consent
boundary, sensitive-input protection, injection guards, and recovery all
deterministically verified + red-team-tested. Live browser/desktop actuation on
real authenticated apps remains permission/dependency-blocked (needed for DIGITAL
WORKER PILOT/PRODUCTION READY).

## M17.1 — live browser validation (genuine)

Real browser control WITHOUT install/permission: system Chrome launched headless
with a bounded loopback --remote-debugging-port + isolated --user-data-dir,
driven over CDP via a minimal STDLIB websocket (browser_driver.py) — the ONLY
place a real browser is driven; agents reach it through ComputerAgent →
ExecutionEngine → ExecutionGateway → ComputerAdapter → live driver (no bypass).
A genuine workflow (live_workflow.run_browser_smoke) launches Chrome, loads a
local test site, reads real DOM, fills a non-sensitive field, clicks submit,
**verifies the real confirmation text**, captures a real screenshot to the
git-ignored pilot workspace, PAUSES on the password field (never typed/recorded),
and closes cleanly (process exit + isolated-profile cleanup). permissions.py
reports honest readiness (browser headless = granted, no permission needed;
macOS Accessibility/Screen-Recording = user_action_required; TCC never self-
granted). workspace.py confines all test files to data/computer-agent-pilot
(git-ignored, never committed/uploaded). live_report.py classifies every
capability honestly (live-browser-tested / permission-blocked / dependency-
blocked / environment-blocked). Red-team +6 (52/52): CDP-loopback-only,
isolated-profile, origin-switch-blocked, download-confined, no-control-after-
lock, screenshot-confined. Ops: critical manifest m17.1 (+4 checks). Tests:
test_m17_1_live.py (9; 4 real live-browser). **Verdict: DIGITAL WORKER PILOT
READY (browser)** — real controlled browser workflow verified through the gateway
with sensitive-input protection + redacted replay + clean teardown. Native-desktop
(Finder/TextEdit/Accessibility) is **permission-blocked** (macOS TCC not granted);
OCR/vision dependency-blocked; authenticated + external side-effect environment-
blocked. Not PRODUCTION READY.

## M17.2 — native macOS activation (honest live reads)

Canonical `macos_driver.py` is the ONLY place native APIs (NSWorkspace/Quartz/
AXUIElement/AppleScript) are called; native ops registered as the `macos`
connector so they route through ExecutionEngine → ExecutionGateway (no bypass).
`macos_permissions.py`: real probes — AXIsProcessTrusted (Accessibility),
CGPreflightScreenCaptureAccess (Screen Recording), executable identity (TCC binds
to the interpreter; stable venv path, adhoc-signed). **Genuinely live-desktop-
tested** (real macOS through the gateway): application enumeration (NSWorkspace,
real bundle IDs + PIDs), application/process identity verification (spoofed PID
REJECTED), screen capture (real screencapture PNG, confined to git-ignored pilot
workspace, probe deleted for privacy). **Permission-blocked** (AXIsProcessTrusted
= False here): AX tree, Finder/TextEdit/menu/app-switch/keyboard actuation.
**Environment-blocked** (no interactive GUI session): app activation, Electron,
multi-monitor. Native pilot workspace data/computer-agent-pilot/native (git-
ignored, symlink-free, never committed). Red-team +5 (57/57): spoofed-PID
rejected, no-native-control-without-allowed-session, native file-root confinement,
screenshot-confined, AX-label-injection-stays-data. Ops: critical manifest m17.2.
Tests: test_m17_2_native.py (9; 4 real live-desktop reads). Native driver boundary
rule: no native action from Chat/Voice/agents/shell/AppleScript-helper — only
ComputerAdapter → gateway → MacDriver. **Verdict: NATIVE DESKTOP STAGING READY** —
real macOS reads (enumeration/identity/screen-capture) verified through the
gateway; Finder/TextEdit actuation permission-blocked pending an Accessibility
grant + interactive session (browser pilot from M17.1 stays DIGITAL WORKER PILOT
READY separately). Not native DIGITAL WORKER PILOT READY (no Finder/TextEdit
workflow completed).

## M17.3 — Agent-Native Application Harness Platform

`saathi/application_harness/`: lets agents operate applications through structured
CLI harnesses BEFORE browser/visual control. Design informed by HKUDS/CLI-Anything
(Apache-2.0) — **no code copied** (THIRD_PARTY_NOTICES.md). Capability resolution
order: connector_api → trusted_harness → dom_cdp → accessibility → ocr_vision →
coordinate (resolver.py). **ApplicationHarnessAdapter is the sole subprocess
boundary**: argv-only (never shell=True), sanitized minimal env (no inherited
secrets), minimal PATH, file-root confinement + symlink/traversal rejection,
output-size cap, process-group cleanup. service.run_harness_action is the only
governed entry (ownership + trust + risk/approval gated); no agent/chat/frontend
reaches the adapter directly. **Trust lifecycle** (trust.py): discovered→…→
approved→trusted; no skip/backward; APPROVED needs deterministic+security+license
+exact-source evidence AND a human (agents cannot self-promote); source change
resets trust; quarantine blocks. **Importer** (importer.py): CLI-Anything registry
read-only → every entry external_untrusted; rejects shell chains / traversal /
bad install schemes (17/79 rejected in the real registry). **Independent
verification** (verify.py): ffprobe/magic-bytes/checksum + XXE-safe XML + ZIP-slip-
safe archives + oversize/secret-pattern rejection — a process `status:success` is
NEVER trusted alone. **FFmpeg pilot** wraps the existing canonical tool:
probe_media (risk 0) + transcode (risk 1), LIVE-tested end-to-end through the
gateway with independent ffprobe verification. Red-team +11 (68/68): untrusted/
quarantined blocked, source-resets-trust, agent-no-self-promote, shell-inject
rejected, adapter argv-only, import-untrusted, fake-success-not-accepted, XXE,
ZIP-slip, oversize. Ops: critical manifest m17.3 (+9). Tests: test_m17_3_harness.py
(19; 2 live ffmpeg). **Verdict: AGENT-NATIVE APPLICATION PILOT READY** — one real
application harness (FFmpeg) executes through ExecutionGateway, produces a verified
artifact, trust + source pinning enforced, cross-user blocked. LibreOffice/Blender
dependency-blocked. Not PRODUCTION READY.

## M17.4 — Multi-Application Harness Platform

Generalizes M17.3 (no new execution path). discovery.py (real app detection:
NSWorkspace/Applications/which/brew; Win/Linux contract-ready). installer.py:
staged secure install (inspect→hash→dependency→path-hijack-check→smoke→register)
+ rollback; refuses arbitrary URL / embedded command / unknown method / unpinned
source / unsafe binary path. lifecycle.py: update RESETS trust (backup for
rollback), disable/quarantine/revoke/uninstall block execution + preserve
evidence. limits.py: RLIMIT CPU/AS/FSIZE preexec + wall-clock + artifact cap wired
into the adapter. verify.py expanded to 15+ formats (OpenXML docx/pptx/xlsx with
ZIP-slip + zip-bomb guard, jpeg, mov/mkv/mp4, mp3/wav via ffprobe, dir-tree).
pilots/apps.py: LibreOffice/Blender/Kdenlive/Inkscape/ImageMagick defs — present→
approved, absent→dependency-blocked (never faked). Control Center harness cell.
Red-team +7 (75/75): path-hijack, install-URL, update-hijack, revoke, zip-bomb,
dep-blocked, resource-limits. Ops: critical manifest m17.4. Tests:
test_m17_4_multiapp.py (12; 2 live ffmpeg verifier). **Verdict: HARNESS PLATFORM
STAGING READY** — platform generalized + hardened; only FFmpeg live (others
dependency-blocked). Not MULTI-APPLICATION PILOT READY (needs >=2 apps live), not
PRODUCTION READY.

## M17.5 — second live application harness (SQLite)

Closes M17.4's "one live app" gap. saathi/application_harness/pilots/sqlite_harness.py
wraps the system sqlite3 CLI in the harness contract, routed through the SAME
service→adapter→gateway path (no new execution path). Ops: inspect_schema (risk0,
-readonly), query_readonly (risk0, -readonly — writes blocked at the engine),
safe_mutation (risk2, reversible, pilot-workspace DB). Untrusted SQL rejects
dot-commands (.shell/.import/.output), ATTACH/DETACH, PRAGMA, VACUUM,
load_extension, multi-statement (;), and oversized SQL; table identifiers
validated (no name injection); mutation SQL built from constants + a validated
identifier only. Independent verification opens the DB directly (PRAGMA
integrity_check + table count) — the sqlite3 exit/word is never trusted alone.
Red-team +3 (78/78): dot/attach/injection rejected, identifier injection rejected,
two-live-apps present. Ops: critical manifest m17.5. Tests: test_m17_5_sqlite.py
(14; 4 live sqlite). **Verdict: MULTI-APPLICATION PILOT READY** — TWO real apps
(FFmpeg + SQLite) run through the trusted-harness path with independent
verification + cross-user isolation. Not PRODUCTION READY.

## M17.6 — third live application harness (jq)

Autonomous-loop milestone. saathi/application_harness/pilots/jq_harness.py wraps
the system jq CLI (JSON transformation) through the SAME service->adapter->gateway
path. transform op (risk 0, no side effects). Untrusted jq FILTER validated
against a denylist (env/$ENV/input/inputs/include/import/getpath/input_filename/
modulemeta/@sh/$__loc__/debug) + length bound; input file-root confined; argv-only
(-c -e, no --rawfile/--slurpfile/--args). Independent verification parses jq stdout
as JSON (verify_json_stdout) — jq's exit is never trusted alone; empty/non-JSON ->
not success. Red-team +3 (81/81): env/file/shell filters rejected, three-live-apps,
invalid-output-not-success. Ops: critical manifest m17.6. Tests: test_m17_6_jq.py
(17; live jq). **Three live application harnesses across three distinct categories:
FFmpeg (media) + SQLite (database) + jq (data transformation)** — all through one
governed, independently-verified path. Verdict: MULTI-APPLICATION PILOT READY
(strengthened). Not PRODUCTION READY.

## M17.9 — durable run ledger, concurrency safety, recovery ops

Autonomous-loop milestone. Upgrades M17.8's single-process append-only JSONL run
journal into a transactional SQLite run ledger (saathi/application_harness/
run_ledger.py) beneath the SAME service->adapter->gateway path — no second
execution engine; the adapter is byte-unchanged and ledgers state via a journal
drop-in. Explicit state set {queued,starting,running,cancellation_requested,
cancelled,succeeded,failed,timed_out,crash_recovered,blocked,stop_uncertain} with
a fail-closed transition graph. One write primitive: BEGIN IMMEDIATE + terminal/
edge/require_from/stale-version checks + compare-and-set on state_version +
transition-row insert -> exactly one caller wins each transition. Proven with real
spawned PROCESSES (not threads): one-claimant-per-run, deterministic cancel/
complete race, many heartbeat writers, cross-process recovery, db-lock handling.
Terminal states immutable (no resurrection); ownership-safe cancel; exactly-once
idempotent crash recovery that never overwrites a live process; heartbeats +
stuck-run classification (active/heartbeat_stale/process_missing/cancellation_stuck
/terminal); recovery ops (inspect/list/reconcile/reconcile-stale/mark-recovery/
transitions/cleanup). JSONL migration is read-only, backed-up, provenance/timestamp-
preserving, malformed-injection-rejecting, idempotent, reversible. CLI ledger ops
are admin-maintenance-only (SAATHI_HARNESS_ADMIN=1; actor = verified local OS
identity; audited) — NO caller-supplied --requester/--owner is ever trusted for
authorization; only aggregate ledger-health is open. Control Center harness cell
gains an owner-safe run_ledger read model + ledger_health. Ledger db added to the
release backup/restore + integrity gates. Red-team +19 deterministic probes
(duplicate claim, stale writer, terminal resurrection, cross-user cancel, run-id
substitution, pid reuse, process-group substitution, idempotency collision, forged
heartbeat/recovery, migration injection, malformed JSONL, db path traversal,
symlink db, secret injection, unbounded history, lock DoS). Ops: 11 dedicated
BLOCKING critical-manifest entries (ledger.*). Tests: test_m17_9_run_ledger.py
(33) + concurrency (6, spawn) + live/backup-restore (7) + redteam (19) +
integration (9) = 74. **Verdict: RUN LEDGER STAGING READY** — transactional state,
terminal immutability, one-claimant multi-process proven, ownership isolation,
deterministic races, exactly-once crash recovery, restart + backup/restore
persistence, safe reversible migration, green blocking manifest, real Control
Center read model — all through the single adapter boundary. NOT production-ready
(multi-user load, production monitoring/alerting, deployment, incident-response
drill outstanding). Pause/resume/checkpoint = contract_ready only (process
suspension is NOT application checkpointing; transactional run state is NOT
exactly-once external side effects; uncertain outcomes stay stop_uncertain;
recovery never blindly repeats non-idempotent work).

## M17.10 — harness run monitoring & deterministic stuck-run alerting

Autonomous-loop milestone. Bounded first slice of "production monitoring" (the
roadmap gated it on a bounded design existing). Extends the M17.9 run ledger +
Control Center attention + event bus — NO second monitoring stack. Ledger gains a
run_alert store (same DB) with a partial-unique dedup index
(idx_alert_dedup(state_key) WHERE status!='resolved') so at most one non-resolved
alert exists per (run_id, alert_class): raise_alert is idempotent (INSERT OR
IGNORE), resolve_alerts flips open->resolved and is auto-called on every terminal
transition (complete) and crash reconcile, and acknowledge_alert is admin-audited +
fail-closed. Deterministic severity: process_missing/cancellation_stuck=high,
heartbeat_stale=medium. New run_monitor.py HarnessRunMonitor.sweep() classifies
active runs via the ledger's existing classify(), raises dedup alerts for
heartbeat_stale/cancellation_stuck, reconciles process_missing through the M17.9
idempotent live-safe path (the ONLY run mutation — never reruns work, never
overwrites a live process), and self-heals (resolves alerts for runs that became
active again). Deterministic: now/thresholds/is_alive injectable, no randomness, so
a tick-schedule causes no alert storms or replay dupes. Control Center harnesses()
cell exposes owner-safe run_alerts; _attention() folds harness stuck-run alerts
into the ranked list (kind harness_run, link /control/harnesses); overview() passes
the harness cell. CLI +3 admin-maintenance commands (SAATHI_HARNESS_ADMIN=1;
verified OS identity; audited): runs-monitor, run-alerts, alert-ack. Proven with
real spawned PROCESSES: 6 concurrent sweeps over one stuck run -> exactly 1 alert,
integrity ok. Restart persistence proven. Ops: 2 dedicated BLOCKING critical-
manifest entries (ledger.monitor_alerting, ledger.monitor_control_center_contract).
Tests: test_m17_10_run_monitor.py (15). Full suite 1598 passed / 1 skipped / 0
failed. Server 308 routes. Release exit 0. Secret scan clean. Trading Guardian NOT
engaged (no financial/external/portfolio/autonomous-execution surface). **Verdict:
HARNESS RUN MONITORING STAGING READY** — deterministic dedup self-resolving stuck-
run alerting over the ledger, surfaced through existing attention + event bus, with
admin-audited acknowledge and a green blocking manifest. NOT production (external
alert transports email/Slack/PagerDuty, scheduled sweeps, multi-user load, incident-
response drill outstanding). Backward compatible: additive CREATE TABLE IF NOT
EXISTS; M17.9 fully preserved; revert = single-commit rollback.

## M17.11 — scheduled run monitoring & reliable alert delivery

Autonomous-loop milestone. Makes the M17.10 monitoring substrate operationally
useful. Additive run_alert_delivery table in the SAME ledger DB (FK to run_alert),
unique idem_key=alert_id:channel:destination:fingerprint so one active delivery per
alert+channel+destination+payload version. States pending/attempting/delivered/
retry_wait/suppressed/terminal_failed/cancelled; CAS under BEGIN IMMEDIATE; lease-
based claim (claim_owner/claim_at) for concurrency; delivered/suppressed/cancelled
immutable, terminal_failed immutable except audited admin retry. Bounded
DETERMINISTIC retry RETRY_SCHEDULE=(0,60,300,900,3600)s, MAX 5 → terminal_failed;
next_attempt_at persisted (restart-safe); injectable clock, no real sleeps, no LLM.
Policy: only OPEN alerts create deliveries (acknowledged→none), unknown class fails
closed, resolved/acknowledged suppress pending (wired into resolve_alerts +
acknowledge_alert), fingerprint=sha256(run_id|class|severity) is the payload
version. notify.py: AlertTransport Protocol, LocalFileTransport (durable owner-safe
JSONL under gitignored data dir, credential-free, fingerprint-idempotent, never
fakes success), DisabledTransport/UnconfiguredTransport fail closed,
NotificationDispatcher (enqueue policy + lease-claim dispatch + reclaim_stale for
crash-after-claim). run_scheduler.py MonitorScheduler: one named job
harness.monitor.sweep, idempotent register/start, overlap lock, DEFAULT DISABLED
(SAATHI_HARNESS_MONITOR_ENABLED=1), restart-safe (reclaim leases + resume retry_wait),
sweep_started/finished/failed events; mirrors storage svc.start(interval_seconds=60)
— not a new framework. Control Center harnesses() cell: owner-safe run_deliveries +
delivery_health + monitor_schedule; _attention folds terminal delivery failures
(kind harness_notification, high). CLI +4 admin-maintenance commands (verified OS
identity, audited): notify-dispatch, alert-deliveries, retry-delivery, monitor-
schedule-status. Send-before-persist: at-least-once via local transport idempotency
+ stale-claim reclaim; uncertainty never hidden. Proven with real spawned PROCESSES:
concurrent create dedups to 1, concurrent claim 1 winner, concurrent dispatch 1
durable line, stale claim reclaimed. Events: harness.notification.queued/attempted/
delivered/retry_scheduled/suppressed/terminal_failed/admin_retry +
harness.monitor.sweep_started/finished/failed. Ops: 7 dedicated BLOCKING critical-
manifest entries (notification.*). Tests: test_m17_11_notification_delivery.py (34).
Full suite 1613 passed / 1 skipped / 0 failed. Server 308 routes. Release exit 0.
Secret scan clean. Backward compatible: additive CREATE TABLE IF NOT EXISTS;
M17.9/M17.10 preserved; terminal runs immutable; revert = single-commit rollback.
Trading Guardian NOT engaged (no financial/external execution; no alert triggers a
trade; no delivery/ack authorizes financial action; notification stays advisory-
compatible). **Verdict: RELIABLE LOCAL ALERT DELIVERY STAGING READY** — NOT
production (external transports Telegram/email/Slack/PagerDuty are fail-closed stubs,
auto scheduling, multi-user load, incident-response drill outstanding).

## M17.12 — governed multi-harness pipeline

Autonomous-loop milestone (start/rollback 22c2fe0, M17.11). M17.8–M17.11 proved
single-run execution + monitoring + delivery — clearing the roadmap gate on the
"multi-harness pipeline" candidate. Makes the four proven live apps (FFmpeg/SQLite/
jq/zip) composable into ONE governed, deterministic, SEQUENTIAL, fail-closed
workflow. KEY: this is an ORCHESTRATOR, NOT a second execution engine — every step
runs through the SAME governed service.run_harness_action (ownership → trust →
risk/approval → the sole adapter → INDEPENDENT verification). Additive pipeline_run
+ pipeline_step tables in the SAME ledger DB; pipeline_run PK-unique (concurrent
duplicate create → one winner); unique (pipeline_id, step_index); state
pending→running→{succeeded|failed}, terminal immutable; owner-safe field
projections; secret-shaped names rejected. NOTE: a single harness action is NOT
process-journaled (adapter journal only wired for M17.8), and QUEUED only
transitions to STARTING/CANCELLED/BLOCKED/STOP_UNCERTAIN — so NO synthetic per-step
`run` row is fabricated; the pipeline_step record IS the durable per-step ledger
entry. pipeline.py PipelineRunner: one confined per-pipeline workspace = the SOLE
file_roots; artifact wiring exposes a producing step's output to later steps by name
inside the workspace (StepContext.artifacts); fail-closed short-circuit on the first
non-success (blocked/failed/timeout/uncertain/approval_required/unknown-or-non-
executable harness/plan-builder exception) → pipeline failed at that step, later
steps NEVER run. Defence-in-depth confinement: reject BEFORE execution an
absolute/`..`/realpath-escaping produces or verify_target. Approval gates honoured:
risk≥3 → approval_required unless StepPlan.approved (no silent elevation), risk 4
manual-only. Steps declared in TRUSTED Python (like the pilots) via a plan callable —
untrusted spec-JSON parsing deferred. Control Center harnesses() cell: owner-safe
pipelines + pipeline_health; _attention folds failed pipelines (kind
harness_pipeline, high). CLI: pipeline-health (always, aggregate), pipelines +
pipeline-inspect (admin-gated, verified OS identity, owner-safe). LIVE chain proven:
sqlite safe_mutation → data.db → zip pack → bundle.zip, both independently verified,
artifact wired end-to-end (bundle contains the exact db). Multi-PROCESS concurrent
create dedups to exactly 1. Ops: 7 dedicated BLOCKING critical-manifest entries
(pipeline.*); full manifest 146 checks green. Tests: test_m17_12_harness_pipeline.py
(21). Backward compatible: additive CREATE TABLE IF NOT EXISTS; M17.9/10/11
preserved; revert = single-commit rollback (two unused tables remain). Trading
Guardian NOT engaged (approval gates strengthened, never bypassed). **Verdict:
GOVERNED MULTI-HARNESS PIPELINE STAGING READY** — NOT production (parallel/branching
DAGs, pipeline retry/resume/checkpoint, untrusted spec ingestion, multi-user load
outstanding).

## M17.13 — autonomous mission engine

Autonomous-loop milestone (start/rollback 186a72f, M17.12). Puts one layer ABOVE
the pipeline so a Mission = one business objective (today's IELTS lesson, daily CEO
brief, kitchen inventory audit …). HIERARCHY: Mission → Pipeline → Harness Step →
Adapter → Verification → Ledger. KEY: a Mission NEVER executes a tool — it holds an
objective + strongly-typed validated params + an approval requirement + a reference
to a TEMPLATE, and DELEGATES to the existing M17.12 PipelineRunner (which delegates
to the sole governed run_harness_action). NO second execution engine / trust model /
DB / scheduler / approval path. Additive mission + mission_run tables in the SAME
ledger DB: mission PK-unique (concurrent duplicate create → one winner);
mission_run UNIQUE(mission_id, attempt); state machine
draft→(approval_required|approved)→queued→running→{completed|failed|cancelled|
blocked} enforced by an explicit graph (anything unlisted rejected, fail closed);
terminal immutable; owner-safe field projections; params secret-rejected on write and
stored as owner-safe JSON (declared inputs like date/difficulty are safe to surface;
argv/output/secrets are NOT). mission.py MissionEngine: create (validate_params —
strong coercion, required checks, enum bounds, unknown-key rejection BEFORE any
execution; bool is NOT a valid int/float), approve (external approver → approved),
enqueue (no-approval mission auto-approves→queued; approval-required mission that
isn't approved is moved to approval_required and NOT queued — no silent elevation),
run (queued→running, build the trusted pipeline steps from the template, delegate ONE
PipelineSpec, then completed ONLY if pipeline ok else failed — no partial success;
any exception → MISSION_EXCEPTION failed; missing template → MISSION_TEMPLATE_MISSING
failed), launch (enqueue+run convenience), cancel/block (active→terminal),
retry (rejected unless the mission is FAILED; a failed retry CLONES a NEW mission
instance correlated to its parent — terminal stays immutable). begin_mission_run is
guarded (only queued; no double-run). Owner isolation on every op (mismatch rejected,
never executes). Templates declared in TRUSTED Python (like the pilots) — shipped
default `data_bundle` = the proven sqlite→zip chain as one objective; untrusted
mission-spec JSON deferred. RECURRENCE modeled as instance-per-occurrence (templates
produce instances); a live scheduler is deferred (mirrors M17.11's opt-in stance).
Control Center harnesses() cell: owner-safe missions + mission_health; _attention
folds failed missions (kind harness_mission, high) and approval_required missions
(medium). CLI: mission-health (always, aggregate), missions + mission-inspect +
mission-history + mission-run + mission-retry (admin-gated, verified OS identity,
owner-safe; mission-run launches under the mission's OWN stored owner, approval-
required halts at approval_required). LIVE proven: a mission completes via a real
delegated governed pipeline (data.db→bundle.zip, independently verified); a pipeline
failure fails the mission. Multi-PROCESS concurrent create dedups to exactly 1. Ops:
7 dedicated BLOCKING critical-manifest entries (mission.*). Tests:
test_m17_13_mission_engine.py (32). Backward compatible: additive CREATE TABLE IF NOT
EXISTS; M17.9–M17.12 preserved; revert = single-commit rollback (two unused tables
remain). NOTE: the pre-existing `saathi/missions/` business-content package is a
DIFFERENT lineage and is untouched — the mission engine lives in
`saathi/application_harness/mission.py`. Trading Guardian NOT engaged (approval gates
strengthened, never bypassed). **Verdict: AUTONOMOUS MISSION ENGINE STAGING READY** —
NOT production (untrusted spec ingestion, live scheduling/event triggers, parallel
missions, multi-user load outstanding).

## M17.14 — governed mission scheduler & trusted event triggers

Autonomous-loop milestone (start/rollback 73fd251, M17.13). Adds the WHEN layer
ABOVE the MissionEngine: SCHEDULING SITS ABOVE MissionEngine and delegates down —
Scheduler/Trusted-Event → Mission instance → MissionEngine → PipelineRunner →
run_harness_action → Adapter → verification → ledger. NO DIRECT EXECUTION PATH: the
scheduler NEVER runs a pipeline/harness/adapter/shell/tool (STATIC TEST asserts
scheduler.py + event_triggers.py reference no PipelineRunner/run_harness_action/
adapter/subprocess/Popen — the only downward call is MissionEngine.create/launch/
inspect). NO second scheduler DB / job runner / execution engine / approval system /
event bus / ledger. Additive tables in the SAME ledger DB: mission_schedule,
mission_occurrence (UNIQUE dedup_key), mission_event_trigger, mission_event_receipt
(UNIQUE dedup_key). DURABLE OCCURRENCES: each due time → exactly ONE occurrence
(unique dedup_key = schedule_id:normalized_due_at:version; concurrent creators, one
winner — proven multi-thread AND multi-process). Each occurrence → at most ONE
mission via a DETERMINISTIC mission id = ms_+sha(occurrence_id), so a crash-after-
create re-attempt reconciles the existing mission (create returns duplicate) rather
than making a second. LEASE CLAIMING: claim_occurrence = atomic BEGIN IMMEDIATE CAS
(pending/due-retry_wait + no live lease → claimed w/ bounded lease); active lease NOT
stealable; expired lease recoverable. RESTART RECONCILIATION: reconcile() scans
stale-lease occurrences — no mission → requeue pending; mission terminal/approval →
finalize occurrence from it; mission mid-flight → re-launch (idempotent) then
finalize; never duplicates. Occurrence state machine pending→claimed→running→
{succeeded|failed|blocked|approval_required|cancelled}, plus retry_wait (infra only)
and pending/expired; terminal immutable; SUCCEEDED only if the LINKED mission
completed (never "mission created"). Schedule types one_time/interval/daily/weekly
(cron deliberately omitted); UTC internal, daily/weekly wall-clock via zoneinfo so
DST is library-handled (a daily 06:00 job stays 06:00 local across DST; spring-
forward day = 23h — proven). Schedule states active→{paused,completed,disabled,
invalid}, terminal never reactivates; paused/disabled generate nothing. RETRY: infra-
only via shared RETRY_SCHEDULE [0,60,300,900,3600]s→terminal_failed; NEVER for
approval/owner/template/param/verification/mission-outcome. APPROVAL & OWNERSHIP
PRESERVED: approval-required scheduled mission STOPS at approval_required (never auto-
approved); owner consistency checked BEFORE the engine (occurrence.owner==schedule
.owner), mismatch executes nothing; risk-4 stays manual-only under the unchanged
run_harness_action. TRUSTED EVENT ALLOWLIST: ingest_event accepts only
TRUSTED_EVENT_TYPES (harness.pipeline.failed/succeeded, harness.mission.completed/
failed, harness.notification.terminal_failed, system.daily_rollover,
ceo.review.requested); a trigger STATICALLY binds owner+template+static params; a
payload can never choose template / change owner / alter risk / grant approval
(forbidden mappings refused at registration); only allowlisted SCALAR payload fields
mapped, unexpected/secret/nested rejected; durable receipt (unique
trigger_id:source_event_id) dedups repeats to ONE mission; receipts store no raw
payload. Opt-in interval runner scheduler_runner.py (default DISABLED via
SAATHI_MISSION_SCHEDULER_ENABLED=1; overlap-safe, restart-safe; no OS/cron/cloud).
Control Center: owner-safe scheduler cell + attention (invalid schedule / failed +
approval_required occurrence / stale lease / trigger-rejection threshold). CLI:
scheduler-health (always) + 11 admin-gated owner-safe (schedules, schedule-inspect,
schedule-create typed, pause/resume/disable, occurrences, occurrence-inspect,
occurrence-reconcile, triggers, trigger-inspect). Ops: 8 BLOCKING scheduler.*
manifest checks. Tests: test_m17_14_mission_scheduler.py (49). VALIDATION: 49 new;
214 harness-lineage+CC regression; full suite 1736 passed / 1 skipped / 0 failed
(+49 over 1687); 8 scheduler.* manifest GREEN via runner; release gate exit 0
(db/backup/restore true) + dedicated backup/restore test; secret scan clean; git
diff --check clean. Backward compatible: additive CREATE TABLE IF NOT EXISTS; M17.8–
M17.13 preserved; revert = single-commit rollback (four unused tables remain).
Trading Guardian NOT engaged (scheduler/event modules contain no trading surface —
asserted; scheduling never converts advisory into execution permission). Commit:
this invocation (see git log); rollback point 73fd251. **Verdict: GOVERNED MISSION
SCHEDULING & TRUSTED EVENT TRIGGERS STAGING READY** — NOT production (cron, public
webhooks, untrusted JSON defs, distributed/parallel scheduling, production auto-
scheduling outstanding).

## M17.15 — governed pipeline retry, resume & checkpoints

Autonomous-loop milestone (start/rollback 4cad92a, M17.14). A failed/interrupted
pipeline CONTINUES FROM ITS LAST INDEPENDENTLY VERIFIED STEP instead of restarting.
KEY: RECOVERY REUSES ONLY VERIFIED CHECKPOINTS, and ONLY A CONTIGUOUS VALID PREFIX
is reusable — reuse stops at the first invalid/missing/changed step and every later
step reruns; no already-verified step reruns unless its checkpoint is invalid.
RESUME STILL USES PipelineRunner and run_harness_action — recovery is IMMEDIATELY
AROUND the existing PipelineRunner (static test asserts pipeline_recovery.py has no
run_harness_action/adapter/subprocess/Popen reference; the only downward call is
PipelineRunner.execute_resume). NO second pipeline/execution engine, retry
framework, verification path, or ledger. Additive ledger tables: pipeline_checkpoint
(UNIQUE per pipeline_id,step_index; status valid|invalid|superseded|
missing_artifact|verification_failed) + pipeline_recovery (attempt/max/next_retry/
lease/state retry_wait|resuming|exhausted|recovered|stop_uncertain). A checkpoint is
written ONLY after a SUCCESS+verified step (blocked/failed/uncertain/approval_required
never reach that branch). FINGERPRINTS (deterministic, canonical, never raw secrets;
stable across restart): step_fingerprint = harness/op identity + workspace-normalized
argv + produces + verify_kind + verify_target + approved + RISK + APPROVAL
requirement; dependency_fingerprint = ordered prior step names + their artifact
fingerprints; artifact_fingerprint = sha256 of file bytes. ARTIFACT INTEGRITY IS
CHECKED BEFORE REUSE: artifact must exist, realpath inside the workspace, and
fingerprint match — a missing/modified/escaping artifact invalidates the checkpoint
and reruns its producing step (downstream not reused). CHECKPOINT REUSABLE only if
owner + pipeline + step identity + step/dependency fingerprints + verify policy +
verification passed + artifact intact + not invalidated all hold — fail closed on any
mismatch. RETRY IS CATEGORY-ALLOWLISTED AND BOUNDED: only transient/infra categories
(timeout/transient_lock/fs_contention/adapter_timeout/resource_unavailable/
interrupted) auto-retry, on the shared deterministic RETRY_SCHEDULE
[0,60,300,900,3600]s → exhausted; approval/owner/verification/param/path-escape/
secret/manual-only/cancellation/tamper/fingerprint-mismatch/unknown NEVER auto-retry
(unknown category fails closed). APPROVAL IS NOT IMPLIED: risk + approval requirement
are in the step fingerprint, so INCREASED RISK invalidates checkpoint reuse and the
step reruns and stops at approval_required; resume/retry never elevate; risk-4
manual-only via unchanged run_harness_action; operator may INVALIDATE a checkpoint but
NEVER mark one valid (no force-success). reopen_pipeline = the ONE governed, audited,
attempt-bounded exception to pipeline terminal immutability (complete_pipeline stays
immutable for normal runs; M17.12 tests unchanged). CONCURRENCY: lease-based recovery
claim (one resumer wins; active lease not stealable; expired reclaimable; concurrent
resume/retry → one resumed run). CRASH RECONCILE prefers reconciliation over duplicate
execution (now-succeeded → recovered; uncertain → retry_wait, never assume success;
verification-uncertain → stop_uncertain). MISSION INTEGRATION: a mission's failed
pipeline resumes IN PLACE (same pipeline_id/workspace) — no duplicate mission/
occurrence; owner preserved; mission terminal reflects the resumed result. Control
Center: owner-safe recovery cell + attention (retry exhausted/high, stop_uncertain/
high, missing-artifact checkpoint/high, other invalid checkpoint/medium). CLI:
pipeline-recovery-health (always) + 7 admin-gated owner-safe (checkpoints,
checkpoint-inspect, recovery-history, recovery-reconcile, invalidate-checkpoint,
resume, retry). Ops: 9 BLOCKING pipeline_recovery.* manifest checks. Tests:
test_m17_15_pipeline_recovery.py (35). VALIDATION: 35 new; 249 harness-lineage+CC
regression; full suite 1771 passed / 1 skipped / 0 failed (+35 over 1736); 9
pipeline_recovery.* manifest GREEN via runner; release gate exit 0 (db/backup/restore
true) + dedicated backup/restore test; secret scan clean; git diff --check clean.
Backward compatible: additive CREATE TABLE IF NOT EXISTS; M17.8–M17.14 preserved;
revert = single-commit rollback (two unused tables remain). Trading Guardian NOT
engaged (recovery module has no trading surface — asserted; recovery adds no execution
path so no trading action can be retried/resumed). Commit: this invocation (see git
log); rollback point 4cad92a. **Verdict: GOVERNED PIPELINE RETRY / RESUME / CHECKPOINT
STAGING READY** — NOT production (parallel/branching DAGs, distributed/remote/cloud
checkpoints, untrusted pipeline JSON, cross-owner reuse, production auto-scheduling
outstanding).

## M17.16 — governed bounded parallel & branching pipeline graphs

Autonomous-loop milestone (start/rollback 5bc8317, M17.15). The pipeline gains a
small, deterministic, ACYCLIC graph: ONE fork, N independent branches, ONE explicit
join barrier (bounded diamond A→(B,C)→D). KEY CONSTITUTIONAL FACTS: (1) STILL ONE
ENGINE — no second pipeline/execution/DAG engine, scheduler, retry framework,
checkpoint system, approval system, or ledger. The new dependency-aware bounded
executor (saathi/application_harness/pipeline_graph.py) wraps the EXISTING M17.12
PipelineRunner and calls the SAME PipelineRunner._run_step for EVERY step. (2) EVERY
branch step (root, each branch, join) still executes through run_harness_action
(ownership → trust → risk/approval → the sole adapter → INDEPENDENT verification →
durable ledger + M17.15 checkpoints). (3) The JOIN requires ALL upstream branch
dependencies verified — the dependency mechanism IS the barrier; no partial/"best
effort" join. (4) GRAPH RESUME uses a DEPENDENCY-CLOSED reusable-checkpoint set (not
a linear prefix): a step is reusable only if all its deps are reusable/fresh; the
first invalid step + all descendants rerun; valid independent siblings stay reused.
(5) A branch failure is FAIL-CLOSED — no new downstream work starts, the join never
runs, already-running siblings settle honestly, unstarted siblings are cancelled, the
pipeline finalizes failed; partial completion is NEVER labelled succeeded. (6) OWNER
and APPROVAL remain PER-STEP — parallelism implies no collective approval; one branch
cannot approve another; risk-4 stays gated; risk increase changes the step
fingerprint and invalidates reuse. BOUNDS (exist + tested): ≤16 steps, ≤4 concurrent
workers, ≤4 branch fork width, ≤1 fork, ≤1 join. CONCURRENCY: one bounded
ThreadPoolExecutor(max_workers=concurrency); no unbounded threads, no shell
orchestration, no distributed/remote workers; per-step durable claims
(pipeline_step_claim) give exactly-once execution + crash-safe reclaim; graph launch
dedups on the pipeline_run PK. DETERMINISM: validation, Kahn topo order (declaration-
index tie-break), ready ordering, branch keys (min name of weakly-connected
component), sorted dependency fingerprints, reusable-subgraph, and final result
(success ⇔ all steps succeeded) are all timing-independent. LEDGER (additive): tables
pipeline_graph / pipeline_dependency / pipeline_branch / pipeline_step_claim (the
graph IS a pipeline_run — reuses pipeline_step + pipeline_checkpoint unchanged);
integrity report now counts graphs/branches/dependencies/step_claims (backup/restore
verified). MISSION: a MissionTemplate.build_graph launches a bounded graph through
the SAME PipelineRunner via GraphPipelineRunner — no second mission/occurrence path;
mission history shows the graph pipeline id + branches + join + result. CONTROL
CENTER: owner-safe graph cell (graph_pipelines/graph_health/graph_branches) +
attention (failed graph→join blocked/high; failed|stop_uncertain|blocked branch/high;
approval_required branch/medium); cross-owner hidden. CLI: pipeline-graph-health
(always) + 6 admin-gated owner-safe (pipeline-graph, pipeline-branches,
pipeline-branch-inspect, pipeline-graph-history, pipeline-graph-reconcile,
pipeline-graph-resume — resume driven through the owning mission template, no
arbitrary graph JSON; no force-success/force-valid/skip/adapter/approval-bypass).
OPS: 13 BLOCKING pipeline_graph.* manifest checks. TESTS:
test_m17_16_parallel_pipeline.py (44). LIVE PROOF: real bounded sqlite(root) →
sqlite||sqlite(2 branches, concurrent, each verified) → zip(join) diamond; validated
before exec; branches confined to declared deps; fail-closed proven (branch fail →
join never runs); partial reuse proven (A+C reused, B+D rerun); tamper invalidates
branch+join; duplicate launch + duplicate resume deduped; crash before join reuses 3
reruns 1. Backward compatible: additive CREATE TABLE IF NOT EXISTS; M17.8–M17.15
preserved (sequential pipeline + recovery unchanged); revert = single-commit rollback
(unused tables remain). Trading Guardian NOT engaged (graph layer asserted free of
broker/withdraw/leverage/rebalance/place_order/trade_execution/portfolio_/
exchange_execution surfaces; parallelism changes WHEN safe steps run, not HOW they
are governed). Commit: this invocation (see git log); rollback point 5bc8317.
**Verdict: GOVERNED BOUNDED PARALLEL/BRANCHING GRAPH STAGING READY** — NOT production
(cyclic/nested-fork graphs, dynamic graph mutation, untrusted graph JSON, distributed/
remote execution, cross-owner delegation, production auto-scheduling, live trading all
remain OUT).

## M17.17 — governed graph mission scheduling & recovery integration

Autonomous-loop milestone (start/rollback e7207dd, M17.16). Completes the lifecycle
integration so a SCHEDULED occurrence (or trusted event) can launch a GRAPH-backed
mission, survive interruption, resume through the EXISTING graph + recovery layers, and
settle the mission AND scheduler occurrence EXACTLY ONCE. KEY CONSTITUTIONAL FACTS:
(1) NO NEW EXECUTION PATH. Scheduler/trusted-event → mission occurrence → MissionEngine →
existing PipelineRunner → existing bounded graph executor (M17.16) → run_harness_action →
adapter → INDEPENDENT verification → existing ledger/checkpoints/claims/recovery.
(2) SCHEDULER STILL DELEGATES ONLY TO THE MISSIONENGINE — fresh execution flows through
engine.launch (never the graph executor directly, asserted); the scheduler module does
NOT import the graph executor or PipelineRecovery. (3) MISSIONENGINE REMAINS THE MISSION
AUTHORITY — new methods resume_graph_mission / settle_recovered / reconcile_running_mission
+ _classify_graph_failure live in MissionEngine; the scheduler/coordinator never duplicate
mission lifecycle logic. (4) GRAPH RECOVERY STAYS IN THE EXISTING RECOVERY LAYER — the
coordinator only REQUESTS it via engine.resume_graph_mission → GraphPipelineRunner.resume;
it computes no checkpoint/graph-ready/branch-retry/claim logic. (5) HONEST STATE
PROPAGATION — graph succeeded→mission completed→occurrence succeeded; graph failed
(transient)→mission failed→occurrence DEFERRED retry_wait→succeeded after recovery; graph
approval-required branch→mission BLOCKED(GRAPH_APPROVAL_REQUIRED)→occurrence
approval_required (join never runs, never auto-approved); graph stop_uncertain/verification
→mission BLOCKED(GRAPH_STOP_UNCERTAIN)→occurrence blocked (fail closed); success is NEVER
invented while recovery is pending. (6) IDEMPOTENCY IS LAYERED + DURABLE (not memory-only):
one occurrence/due (dedup_key), one mission/occurrence (deterministic id), one graph/mission
run (pipeline_run PK), one recovery/graph (recovery claim), one claim/step, one join, one
DETERMINISTIC recovered mission (ms_rec_<sha(parent)>), one final settlement (terminal
immutable). A resume already claimed by another worker short-circuits (resume_in_progress)
and stays recoverable. (7) MISSION IMMUTABILITY — a failed graph mission is NOT reopened;
recovery records the resumed result on a LINKED retry mission, preserving the original
failure as audit truth. (8) RESTART RECONCILIATION covers crash windows: F (graph terminal,
mission running → reconcile_running_mission) and G (mission terminal, occurrence unsettled →
settle_occurrence_from_mission), plus cases A–J documented in RECONCILIATION_SEMANTICS.
(9) RETRY reuses M17.15 allowlist + [0,60,300,900,3600]s; approval/owner/invalid/tamper/
verification/unknown never auto-retry; a non-retryable failed graph settles terminal at once
(no relaunch storm). (10) OWNER consistent end to end; any mismatch fails closed. DATABASE:
NO new tables — reuses existing records + one READ-ONLY helper (pipelines_for_correlation on
the existing correlation_id column); M17.8–M17.16 data/backup/restore/integrity preserved;
revert = single-commit rollback. SCHEDULER change is ADDITIVE + DEFAULT-OFF (graph_recovery
flag; M17.14 behavior unchanged). TEMPLATES: trusted graph-backed mission templates
(graph_data_bundle: sqlite root → 2 verified sqlite branches → zip join); a schedule/event
payload can NEVER supply graph/deps/harness/command/risk/approval/owner/concurrency.
CONTROL CENTER: coord.health owner-safe (graphs/recovery/occurrences/missions + attention:
approval_required_scheduled_graph, stop_uncertain_graph, retry_exhausted, failed_graph_branch);
cross-owner hidden; no raw commands/payloads/artifacts/secrets. OPS: 12 BLOCKING
scheduled_graph.* manifest checks (194 total green). TESTS:
test_m17_17_scheduled_graph_recovery.py (31, deterministic — injected clocks/runners,
barriers, no sleeps). Regression: M17.13–M17.16 160 green; full suite 1844 passed / 1
skipped / 0 failed. LIVE PROOF (credential-free): scheduled one_time schedule → 1 occurrence
→ dispatch → graph (root, 2 concurrent verified branches, zip join) → mission completed →
occurrence succeeded; repeat sweep = no duplicate; injected retryable branch_b failure →
durable recovery state → recover reuses root+branch_a checkpoints, reruns only branch_b +
join once → mission (linked retry) completed → occurrence succeeded (idempotent); crash F/G
reconciled; approval-required branch propagates without running the join. Trading Guardian
NOT engaged (integration + engine recovery modules asserted free of trading/broker/
withdraw/leverage/transfer/order-submission surfaces). Commit: this invocation (see git
log); rollback point e7207dd.
**Verdict: GOVERNED SCHEDULED GRAPH RECOVERY STAGING READY** — NOT production (production
auto-scheduling, distributed/multi-region recovery, untrusted graph JSON, dynamic graph
mutation, public webhooks, live trading all remain OUT).

## M17.24 — eliminate residual ungoverned browser dispatch paths

Autonomous-loop milestone (start/rollback f2f262f, M17.23). Closes every
production-reachable path that could initiate browser activity without the
canonical GovernedBrowser → ExecutionGateway boundary. KEY CONSTITUTIONAL FACTS:
(1) ONE BROWSER ENTRY — GovernedBrowser.execute is authoritative; BrowserAdapter
is technical-only after authorization. (2) PRODUCTION SINGLETON FAIL-CLOSED —
BrowserService(allow_direct=False) routes open/extract/screenshot/download through
governance; _open_direct is reserved for the adapter and injected test harnesses.
(3) LEGACY TOOLS FAIL CLOSED — agent-browser CLI, AppleScript social post, and
chatgpt_browser refuse raw actuation unless SAATHI_ALLOW_RAW_BROWSER=1 (never a
production default); navigate-class agent tools may delegate into GovernedBrowser.
(4) CONTEXT ATTRIBUTION — missing actor, missing mission/run when required,
invalid/expired approval, cancelled/paused mission, disabled schedule, untrusted
trigger, unauthorized retry, resume without checkpoint, and mission-id forgery
all DENY before adapter dispatch. (5) STATIC GUARDRAIL — saathi/browser/guard.py
AST-scans product code for forbidden playwright/selenium/LiveBrowserDriver imports
and subprocess browser launch patterns outside an explicit allowlist; blocking
critical checks browser.dispatch_guard_present, browser.no_ungoverned_driver_imports,
browser.direct_dispatch_blocked, browser.context_attribution_enforced,
browser.trading_isolation. (6) TRADING ISOLATION — trade/payment browser actions
require Trading Guardian authorization; generic browser approval is insufficient;
ordinary browse does not engage saathi.execution.trade; no live trading added.
(7) HUMAN BROWSER — /api/v1/human/test records a governed intent first and only
enqueues raw human-browser work with approval_id or raw env; claim/complete remain
queue relays (no browser on the VM). (8) EVIDENCE — success and denial emit
execution records + security timeline; secrets redacted (password/token/cookie
values). TESTS: test_m17_24_browser_dispatch_governance.py (30). Docs:
M17_24_BROWSER_DISPATCH_AUDIT.md, M17_24_ARCHITECTURE.md. Inventory: 20 paths,
0 UNGOVERNED_BLOCKING remaining. Trading Guardian unengaged for non-trading work.
**Verdict: ALL PRODUCTION BROWSER DISPATCH PATHS GOVERNED** — NOT production
(full human-browser workflow migration, live interactive service-mode sessions,
production host allowlists, and deploy remain OUT).

## M17.25 — governed interactive browser sessions, actions, and human handoffs

Autonomous-loop milestone (start/rollback caca1da, M17.24 complete). Extends the
governed browser boundary from dispatch/navigation into full interactive
execution without a second browser engine. KEY CONSTITUTIONAL FACTS:
(1) InteractiveBrowser is the canonical interactive API — open_session / act /
request_handoff / resume / close — always entering GovernedBrowser →
ExecutionGateway. (2) SESSION OWNERSHIP — durable BrowserSessionStore records
actor, mission/run, domains, allowed action classes, leases, checkpoints, and
handoff state; cross-actor and cross-mission access fail closed; expired and
cancelled sessions cannot act. (3) ACTION TAXONOMY — read_only, low_interactive,
sensitive_input, external_effect, financial, prohibited; clicks are not treated
as submits; navigation approval NEVER authorizes external_effect or financial
actions. (4) COMMIT BOUNDARY — submit/publish/book require dedicated approval,
idempotency_key, pre-commit checkpoint, single execution, and ledger replay for
duplicates; uncertain outcomes enter reconciliation and are not blindly retried.
(5) TARGET SAFETY — role/label/test_id preferred; ambiguous and missing targets
denied; raw coordinates blocked; sensitive selectors elevate class; secrets never
stored in the action ledger. (6) HUMAN HANDOFF — CAPTCHA/MFA/uncertain targets
become paused_for_human with checkpoint + lease release; human claim/complete/
decline; resume re-validates domain, fingerprint, ownership, and policy; dual
control prevented. (7) PRODUCTION RAW BLOCK — SAATHI_ALLOW_RAW_BROWSER is ignored
when SAATHI_ENV is production; normal interactive work needs no raw override.
(8) TRADING — financial browser actions require Trading Guardian authorization;
ordinary click/navigate leave trade.py unengaged. MODULES: gov_session.py,
interactive.py; agent_browser click/fill/type delegate to InteractiveBrowser.
TESTS: test_m17_25_interactive_browser.py (34). Critical checks +5 browser.*
interactive. Docs: M17_25_INTERACTIVE_BROWSER_AUDIT.md, M17_25_ARCHITECTURE.md.
**Verdict: INTERACTIVE BROWSER SESSIONS, ACTIONS, AND HUMAN HANDOFFS GOVERNED**
— NOT production (live Playwright service-mode interactive still needs live
session adapter; full human-browser workflow migration remains larger scope).

## M17.26 — production browser adapters, domain policy, evidence redaction, workflow migration

Autonomous-loop milestone (start/rollback 7b21915, M17.25 complete). Connects
governed interactive sessions to production-safe adapter execution without a
browser-engine rewrite. KEY CONSTITUTIONAL FACTS:
(1) CANONICAL ADAPTER CONTRACT — attach_session / validate / health / navigate /
inspect / act / capture_evidence / pause / resume / reconcile / close_session;
adapters receive fully validated GovernedActionRequest and never decide auth,
policy, approval, TG, domain, or retry. (2) PRODUCTION ADAPTER —
ProductionBrowserAdapter binds live/sandbox CDP to session_id; scoped pages only;
ownership+lease before every action; DEGRADED blocks high-risk; disconnect →
reconciliation; reconnect revalidates page/domain/kill-switch; no unmanaged
browser on attach failure; raw page objects never exposed. (3) HUMAN MAC —
same contract; takeover pauses agent; concurrent control denied; bounded to
browser app; human completion ≠ approval; raw osascript blocked outside
allowlisted backend. (4) DOMAIN POLICY — DomainPolicyService per
development/test/staging/production; production deny-by-default HTTPS-only; no
localhost/private/file/javascript/data/wildcards; normalize trailing-dot/IDN/
mixed-script/alt-IP; exact host or explicit subdomain-of root (never substring);
redirect/popup revalidation. (5) WORKFLOW MIGRATION — workflow step schema
rejects script/eval bypass; execute_workflow_step → InteractiveBrowser.act;
CAPTCHA/MFA → handoff; legacy raw fail-closed. (6) EVIDENCE — classify PUBLIC→
PROHIBITED_CAPTURE; modes ALLOW→SUPPRESS; deterministic masks before persist;
OCR optional secondary only; traces/video disabled by default; cookies/storage
never logged; alerts privacy-safe. (7) MONITORING — adapter health, domain
denial, redaction failure, uncertain effect, reconnect exhaustion; Control
Center snapshot without secrets. (8) TRADING — financial still TG-only; trading
screenshots TRADING_SENSITIVE; no live trading capability. MODULES:
domain_policy, adapter_contract, production_adapter, human_mac_adapter,
evidence_redaction, workflow_migrate, adapter_monitor; interactive/governed/
guard/policy wired. TESTS: test_m17_26_production_browser.py (90+). Critical
checks +5 browser.* production. Docs: M17_26_PRODUCTION_BROWSER_AUDIT.md,
ARCHITECTURE, DOMAIN_POLICY, EVIDENCE_REDACTION.
**Verdict: PRODUCTION BROWSER ADAPTERS, DOMAIN POLICY, WORKFLOW MIGRATION, AND EVIDENCE REDACTION GOVERNED**
— NOT full production deploy (live CDP still needs managed loopback endpoint +
binary; human signed-queue workflows remain isolated; pixel OCR not required).

## ECP M17.24 — External Capability Program foundation (2026-07-15)

**Scope:** Register Priority 1–3 external repositories in SES-000E Part 6; adapt
GSAP + Loop Engineering as project Grok skills; document MCP inventory; correct
false “Complete” integration claims for OpenMontage/OpenJarvis/claude-video
adapters (stubs remain). **No** clones, services, or runtime pilots.

**Skills:** `.grok/skills/frontend-gsap`, `saathios-loop-engineering`,
`external-integration-audit`, `external-service-health`.

**MCP:** `docs/integrations/MCP_PROJECT_INVENTORY.md` + project
`.grok/config.toml` (empty pilots). Home codebase-memory documented; headroom
flagged broken.

**Trading Guardian:** Not engaged. Vibe-Trading / Fincept registered research-only.

**Verdict: ECP FOUNDATION REGISTERED — NOT runtime integration**
**Next permitted:** ECP M17.25 Continuum pilot (explicit authorization only; license gate).

## M23 — Chat system prompt layering authority (2026-07-17)

Chat system prompts are composed only by `saathi.chat.context.compose_system_prompt`
with deterministic layer order: CANONICAL_BASE → AGENT_ROLE → PRODUCT_POLICY →
USER_STYLE → CONVERSATION_OVERRIDE → PROJECT → SUMMARY → MEMORY → KNOWLEDGE →
TOOL_POLICY. Callers must not build provider-specific message lists. Raw composed
system prompts are not emitted in logs. Tool and trading authority are never
granted by prompt text alone.

## M32 — Governed provider-adapter pilot (2026-07-18)

`saathi/connectors/providers/` adds a **provider-adapter boundary** that sits
ABOVE the M27 connector adapter transport and NEVER decides authority. The pilot
is `saathi.echo.v1` (local deterministic simulator) bound to connector `gov.http`,
READ_ONLY, credential-free, OFF/SHADOW only.

- **Provider verification vs connector certification**: provider verification is an
  *additional* eligibility layer, never a replacement. Execution eligibility ANDs
  M25 production cert + M30 connector cert + M32 provider verification + provider
  config readiness + M31 account/credential readiness + rollout + approval.
- **Normalized contracts**: `normalize_request` rejects injection fields
  (headers/endpoint/auth/retry/timeout/cookie/api_key); `normalize_response` strips
  tokens/cookies/authorization/stack traces and bounds size. Raw provider responses
  never escape the adapter boundary.
- **Retry & idempotency**: deterministic retry taxonomy; retry only when idempotent
  + budget + deadline + credential + approval + not-quarantined + rollout +
  unchanged fingerprint. Idempotency binds to a request fingerprint scoped by
  connector|provider|account|key; cross-scope reuse and changed payloads fail closed.
  Non-idempotent writes never auto-retry.
- **Provider health & quarantine** are distinct from connector health, account
  readiness, and credential quarantine. 3 consecutive malformed → auto-quarantine;
  recovery is explicit only.
- **SHADOW semantics**: full governance over the local simulator; output is
  `authoritative=False`; cannot activate rollout, create account links, or store
  credentials. CANARY/ACTIVE prohibited and rejected. Highest verification claimed =
  `SIMULATION_VERIFIED` (local ≠ live).
- **Eligibility reads never mutate evidence state** (M31 correction preserved):
  `resolve_provider_verification` reports STALE on drift but never writes; only
  explicit `verify_provider` / `check_provider_drift(mark_stale=True)` mutate.
- The M32 provider runtime is an allowlisted governed call site in
  `gov/bypass_guard.py` (like `gov/runtime.py`); provider-adapter bypasses = 0.
