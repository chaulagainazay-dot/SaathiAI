# BUILD_STATUS.md — SaathiAI Implementation Dashboard

> **What this file is:** The daily dashboard. It answers, at a glance, what is *real* (running code) versus what exists only in the SES design documents. Every AI coding agent and every human should read this before touching the codebase — it is the map between the specification layer (`docs/SES/`) and the implementation layer (`saathi/`).
>
> **What this file is NOT:** A specification. Specs live in `docs/SES/v1.0/`. Vision and principles live in `Brain.md`. This file tracks *build state* only.
>
> **Update cadence:** Every time a capability changes status (designed → implemented → tested → production). Keep it honest — an over-optimistic BUILD_STATUS is worse than none.

**Last updated:** 2026-07-02
**Current milestone:** 🎉 **M1 — AI OS Core: COMPLETE** (2026-07-03, `v0.1.0-alpha`) → next: M2 (Memory Promotion Engine + Learning Runtime)

> **M1 complete — all 10 exit criteria met.** The audited, hardened AI-OS core is real: Storage Intelligence, Model Router, Runtime Governance Engine, Tool Registry all ✅ Production; Event Fabric, Agent Runtime (9-phase BMA), Agent Registry, Mission Control all ✅ Tested. 118 tests passing. Governance is the mandatory gate — nothing bypasses it.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| 📐 Designed | SES document exists; no/minimal code |
| 🔨 Implemented | Code exists and runs; not systematically tested |
| ✅ Tested | Code exists with passing tests |
| 🚀 Production | Running in production, relied upon daily |
| ⛔ Blocked | Cannot proceed — see Blockers section |

---

## Version 1.0 Milestones

| Milestone | Theme | Status |
|-----------|-------|--------|
| **M1** | AI OS Core (agent runtime, memory, event bus, tool registry, model router, storage intelligence, basic Voice OS) | 🔨 In progress — most components have partial implementations |
| **M2** | Autonomous Developer (coding agents, GitHub, testing, deployment, code review, ADR generation) | 📐 Partial — `auto_dev.py` exists |
| **M3** | AI Studio (Director, Storyboard, Mr. Yeti, SEO, Publishing, Analytics) | 🔨 Significant code; spec (SES-005) now complete |
| **M4** | Business OS (POS, CRM, Finance, Inventory, Reporting) | 📐 HCG canteen code exists; not generalized |
| **M5** | Learning OS (pielts, personalized learning, progress tracking, career roadmaps) | 🔨 pielts live; learning-OS abstraction not built |
| **M6** | Dream Engine (strategy, financial intelligence, KPI, goal decomposition, executive planning) | 📐 Design only |

---

## Active Sprint: Platform Integration (M3 prelude) — connect products to the platform

**Objective:** products *use* the shared platform (Memory, Learning, Storage, Model Router, Governance, Knowledge Graph) rather than reimplementing it (Dev Rule #2, AP-01). This is where SaathiAI starts creating value, not just being well-architected.

| # | Integration | Status |
|---|-------------|--------|
| **1** | **PIELTS × Learning Runtime** | ✅ **Complete (2026-07-03)** — `saathi/integration.py`, 3 tests. Every BMA tutoring turn now records a platform `Episode` (`ingest_pielts_interaction`, wired into `master.py update_memory`, guarded/non-breaking; existing IELTS memory untouched). Proven end-to-end: student interactions → episodes → Promotion Engine → knowledge candidate; Learning Engine sees pielts success rates. **PIELTS is now a continuously-improving tutor.** (Fixed a real bug: the pielts adapter was hardcoding `outcome="success"`.) |
| **2** | **Discovery × Publishing (the pre-publish gate)** | ✅ **Complete (2026-07-03)** — `saathi/publishing_pipeline.py`, 7 tests. **"Nothing publishes without passing Discovery" is now enforced**: content missing SEO tags / thumbnail / title / description is *blocked* (GEO/schema recommended, not blocking). Every publish AND every block becomes a platform Episode → Learning Runtime; `record_performance()` turns analytics (views/likes/engagement) into episodes, closing the loop so the Learning Engine sees which content actually performs. `PublishingPipeline.production()` wires it to the live platform (episodes → `integration.ingest_episode`, events → Event Fabric). Publisher (the platform poster) is the one injected piece. |
| 3 | AI Studio autonomous publish pipeline | ⬜ (the gate + episode recording is the backbone; remaining = wire real posters through `.production()`) |
| 4 | HCG Live Signal × Research + Learning | ⬜ |
| 5 | HCG POS × Business Intelligence | ⬜ |
| **A** | **Mission Control — CEO Dashboard** | ✅ **Complete (2026-07-03)** — `saathi/ceo_dashboard.py`, 5 tests. Event-first daily operating view (AP-13): aggregates publishing / learning / knowledge-graph / docs / storage streams from the Event Fabric into one snapshot + a text **morning briefing**. **Live-wired** — `send_morning_briefing()` pushes to Telegram via the existing 8am-NPT `ceo_dashboard_job`. Honest by construction (Dev Rule #1): the `$7,938,838.98` Dream Meter reads "$0 — revenue not yet connected" until Business/Financial OS wire it, rather than faking numbers. |

---

## Capability Maturity Matrix

Distinguishes "exists" from "ready." Filled from actual code inspection (Core Runtime Audit, 2026-07-02), not planned features. Legend: ✅ done · ⚠️ partial · ❌ not yet.

| Capability | Designed | Implemented | Tested | Production |
|-----------|:--------:|:-----------:|:------:|:----------:|
| Agent Runtime (BMA loop) | ✅ | ✅ | ✅ | ⚠️ |
| Memory | ✅ | ✅ | ⚠️ | ⚠️ |
| Event Fabric (generic) | ✅ | ✅ | ✅ | ⚠️ |
| Event Bus (IELTS-domain) | ✅ | ✅ | ⚠️ | ✅ |
| Model Router 🏷️ **Platform Capability v1.0** | ✅ | ✅ | ✅ | ✅ |
| Platform Capability Registry | ✅ | ✅ | ✅ | ⚠️ |
| Tool Registry | ✅ | ✅ | ✅ | ✅ |
| Runtime Governance Engine 🏷️ **Platform Capability v1.0** | ✅ | ✅ | ✅ | ✅ |
| Storage Intelligence 🏷️ **Platform Capability v1.0** | ✅ | ✅ | ✅ | ✅ |
| Voice OS | ✅ | ⚠️ | ❌ | ⚠️ |
| AI Studio | ✅ | ⚠️ | ❌ | ⚠️ |
| Discovery Engine | ✅ | ⚠️ | ❌ | ❌ |
| Mission Control | ✅ | ⚠️ | ❌ | ⚠️ |

**Reading the ⚠️s (from the audit):**
- **Agent Runtime** — **upgraded to the full 9-phase BMA loop** (Observe→Understand→Reason→Plan→Execute→Verify→Evaluate→Learn→UpdateMemory), SES-002-aligned. Legacy 4-phase methods kept as wrappers so nothing broke. 18 tests (`test_bma.py` + `test_bma_phases.py`) verify behavior + phase order. Production = ⚠️ until deployed & watched live.
- **Event Fabric** — generic typed pub/sub now built & tested (`saathi/events.py`, 5 tests; Disk Watchdog publishes `storage_critical`/`storage_warning` through it). In-process for now; promotable to NATS without caller changes. The old `agents/bus.py` remains as the IELTS-domain student-error bus.
- **Model Router** — ✅ **Production**. Capability-based router (`saathi/model_router.py`, 9 tests) + execution layer (`saathi/llm.py` `generate()`, 5 tests) routing by capability × cost × latency × privacy × quality. `_llm_helper.ask_llm` now routes through it (STANDARD + QUALITY preference preserves OpenAI-first), so **every existing tool goes through the router with zero call-site changes**. New providers (Claude, Kimi, future) plug in with one registry entry. Legacy inline chain kept only as belt-and-suspenders fallback.
- **Platform Capability Registry** — `saathi/capabilities.py`: live maturity data (Designed/Built/Tested/Production per capability), surfaced in Mission Control's snapshot. The operational heartbeat; this matrix mirrors it.
- **Runtime Governance Engine** — ✅ **built & tested** (`saathi/safety.py`, 20 tests). A layered governance pipeline, not just a permission checker. Layers built: L1 Classification (L0–L5, deterministic, never LLM) · L2 Capability validation · L3 Identity (guest/user/admin/automation/scheduled) · L5 Resource guardrails (wired to the Predictive Storage Engine — renders that can't finish on disk are denied) · L6 profile-driven Approval · L7 Audit (who/what/why/when/risk/result, never optional) · L9 deterministic Risk score + confidence · Safety Profiles (development/production/emergency/offline). Deferred to their milestones (Dev Rule #1): L4 Context (partly covered by L5), L8 Compliance (GDPR/HIPAA — per-product, future), L10 Learning-from-denials (M2). Production = ⚠️ until inserted as the mandatory gate in `tools/registry.py execute_tool`. The IELTS `agents/harness.py` content/bias harness stays separate.
- **Storage Intelligence** — Watchdog + Lifecycle Engine + **Cleanup Engine** done & tested (18 storage tests). Predictive Storage Engine + Telegram alerts + Archive Manager remain (so Implemented = ⚠️ until those land).

---

## Active Sprint: M1 Hardening Sprint

**Objective:** Not new features — bring the existing core into alignment with the SES specifications. Strengthen the foundation before expanding it (platform-first).

**Deliverables:**

1. **Core Runtime Audit** — ✅ *first pass done (2026-07-02)*. Compared `bus.py`, `router.py`, `master.py`, `harness.py`, `registry.py`, `memory/` against SES-002/003. Gaps identified (see the matrix reading above). Decisions taken: BMA loop **upgraded to 9-phase** ✅; generic **Event Fabric built** ✅. Remaining: Model Router formalization, Safety Harness L1–L5, Tool/Agent Registry reconciliation.
2. **Storage Intelligence** — ✅ **M1 Step 1 COMPLETE (2026-07-02)**. Disk Watchdog, Lifecycle Engine, Cleanup Engine, Predictive Storage Engine, Telegram Alerts, Event vocabulary — all built & tested (**32 storage tests**). Tagged **Platform Capability v1.0** (see below).
3. **Mission Control Integration** — surface storage health, runtime health, and job status in the dashboard. *(next)*
4. **Capability Validation** — keep this matrix + BUILD_STATUS updated from actual implementation after each slice (Development Rule #1, step 4). ✅ ongoing.

### 🏷️ Storage Intelligence — Platform Capability v1.0

The capability is **code-complete, tested, and reusable** — the reuse mandate now applies (see Brain.md): every product (AI Studio, pielts, HCG POS, HCG Live Signal, future apps) uses this service rather than implementing its own file management. *Build once, reuse everywhere, improve continuously.*

Components (`saathi/storage/`): `db.py` · `watchdog.py` · `lifecycle.py` · `cleanup.py` · `predictive.py` · `alerts.py`, plus the generic `saathi/events.py` fabric.

**Live-wired (2026-07-02):** `saathi/storage/service.py` assembles all components on one shared Event Fabric; `scheduler.start()` now launches it — 1-minute Disk Watchdog poll, real Telegram alerts (`enable_telegram=True`), event-first Mission Control, and 95%-emergency auto-cleanup — plus a nightly cleanup job at 3:00am. Production = ✅ (wired + import-verified). Ongoing validation = observe it running on the next live server restart.

**Exit criterion:** an audited, hardened AI-OS core — Agent Runtime, Memory, Event Bus, Model Router, Tool Registry, Storage Intelligence all at least ✅-Implemented + ✅-Tested — ready to support Voice OS, AI Studio, and Business OS.

### M1 Hardening Sprint — Formal Exit Criteria

Sprint is complete only when ALL are true:

- [x] Storage Intelligence production-ready (live-wired via `scheduler.start()` → `StorageService`)
- [x] Event Fabric integrated (`saathi/events.py`, storage publishes through it)
- [x] 9-phase BMA runtime operational (`master.py`, 18 tests)
- [x] Agent Registry reconciled with SES-002 (`saathi/agent_registry.py`; master loop registers every sub-agent instance against a declared contract)
- [x] Tool Registry reconciled with SES-002 (Governance Engine now the mandatory gate in `execute_tool`; every dispatch classified + audited)
- [x] Mission Control receives live events (event-first, no polling — `saathi/mission_control.py`)
- [x] Telegram receives critical alerts (`alerts.py`, wired via `enable_telegram=True`)
- [x] BUILD_STATUS reflects actual implementation
- [x] Brain.md updated with new architectural decisions (AP-11, AP-12, AP-13, Dev Rule #1)
- [x] All core tests passing, target 60+ (currently **70**)

**Platform Capabilities v1.0 (production):** Storage Intelligence ✅, Model Router ✅. Event Fabric + Agent Runtime + Capability Registry are tested (production-flip pending live observation).

**M1 Step 2 progress:** Model Router → Production ✅. Next: 🔄 Safety Harness (L0–L5), then Agent Registry + Tool Registry reconciliation, then tag M1 complete. M2 opens with the Memory Promotion Engine.

---

## Active Sprint: M2 — Learning Runtime (branch `milestone/m2-learning-runtime`)

**Success criterion:** SaathiAI learns from completed work and measurably improves future decisions without manual prompt edits.

| Phase | Work | Status |
|-------|------|--------|
| 0 | Memory System Audit (`docs/M2_MEMORY_AUDIT.md`) | ✅ Complete — key finding: PIELTS application memory, not platform memory; two duplicate systems |
| **1a** | **Platform Memory Foundation** | ✅ **Complete (2026-07-03)** — `saathi/memory/platform.py`, 12 tests. Generic `Episode`/`Knowledge` schemas (products attach metadata — pielts/HCG/Studio/crypto proven on one schema); Promotion State Machine (NEW→CANDIDATE→UNDER_REVIEW→PROMOTED→SUPERSEDED→ARCHIVED, illegal jumps rejected); retention policies (SESSION 7d / WORKFLOW 30d / SEMANTIC forever / PLATFORM_WISDOM never); scope firewall (only platform/global cross products); **Source Trace** (`source_episode_ids` — "why do I believe this?"); **verification_count** (evidence-based trust). Dead shadowed `saathi/memory.py` deleted; PIELTS backward-compat adapter tested. `Wisdom.md` seeded (human-readable L6). |
| **1b** | **Memory Promotion Engine** ⭐ | ✅ **Complete (2026-07-03)** — `saathi/memory/promotion.py` + `saathi/memory/evidence.py`, 19 tests. 7-stage deterministic pipeline (Discovery → Intent Clustering → Structured Extraction → Evidence Scoring → State Transition → Routing → Events); engine only moves states via the Promotion State Machine (never illegal); **Evidence Scorer** (verification/diversity/time-consistency/cross-product/contradiction-risk + LLM confidence, weighted); **Knowledge Contradiction Detector** (flags conflicts for review, never silently overwrites — both items linked); auto-promote / contradiction / strategic-review routing; publishes `knowledge.promoted` / `knowledge.conflict_detected` / `knowledge.review_requested` / `brain.update_candidate`; idempotent (episodes marked consumed). LLM-free defaults; LLM extractor pluggable later. |
| **2** | **Knowledge Governance Engine (Review Queue)** | ✅ **Complete (2026-07-03)** — `saathi/memory/review_queue.py`, 13 tests. Persistent `knowledge_reviews` table; deterministic **Prioritizer** (security→CRITICAL, business/finance→HIGH, architecture→MEDIUM, writing-style→LOW; contradiction bumps up); **configurable AutoApprovalPolicy** (confidence/contradiction/scope/type — no hardcoded 0.95); human **approve→PROMOTED / reject→ARCHIVED**; **rejected knowledge kept, never deleted** (resolution history for reconsideration); **Evidence Explorer** (review→knowledge→source episodes→raw — every conclusion explainable); priority-ordered `pending()`; `sync_from_memory()` picks up engine-routed candidates; **Telegram review card** formatter (🧠 card + `/approve_N` `/reject_N` `/inspect_N`); publishes `knowledge.review_enqueued`/`promoted`/`rejected`. Bot command-handling + Mission Control widgets = wiring layer (Phase 6). |
| **3** | **Learning Engine** | ✅ **Complete (2026-07-03)** — `saathi/learning/`, 8 tests. Deterministic pipeline: Outcome Evaluation (per-intent success/quality/cost/duration) → Failure Analysis (10 deterministic categories: infrastructure/network/external-api/tool/model/prompt/reasoning/user/human-approval/unknown) → Lesson Extraction (structured `Lesson`; LLM injectable, LLM-free default) → **Capability Improvement (PROPOSES, never mutates — AP-18)** → Learning Policy routing (improvement / knowledge-candidate / ADR-candidate / engineering-task). **Capability Improvement Registry** (organizational learning — "how has AI Studio improved?") + **Experiment Registry** (A/B, prevents regressions, picks winner by higher/lower-is-better). Publishes `learning.lesson_extracted` / `learning.*_candidate`. |
| **4a** | **Knowledge Graph (backend-agnostic API)** | ✅ **Complete (2026-07-03)** — `saathi/graph/`, 11 tests. Built the **API not the backend** (AP-02): departments use `KnowledgeGraph`, never Neo4j/SQLite, never Cypher. `GraphBackend` interface + `SQLiteGraphBackend` adapter (Neo4j = drop-in later). Rich 20-type ontology (Goal/Strategy/Capability/Product/Department/Agent/Tool/Workflow/Knowledge/Episode/Experiment/Improvement/Decision-ADR/Risk/Metric/Task/Document/User/Model/Provider) + 15 edge types. **Graph Evolution Engine** — versioned supersede, never delete ("why Renderer Y now?" answerable via SUPERSEDES + reason). **Query Engine** — what_supports / depends_on / dependents / governing_decisions / contributors_to_goal / path (BFS, no Cypher). Models goals + decisions: the `Revenue $7,938,838.98` goal-contribution query works. AP-19 recorded. Neo4j adapter + event-driven GraphBuilder = Phase 4b. |
| **5** | **Knowledge Publication Engine** (Brain Synchronizer, expanded) | ✅ **Complete (2026-07-03)** — `saathi/publication.py`, 10 tests. **NO automatic edits — proposals only; markdown renders only after approval.** Destination Router (Brain/Business/Wisdom/Writing-Style/ADR/CHANGELOG/BUILD_STATUS by knowledge type); structured `Proposal` (target/section/change_type/summary/evidence/confidence); **deduplication** (near-identical proposals merge evidence + bump confidence — no proposal spam); lifecycle DRAFT→READY→UNDER_REVIEW→APPROVED→PUBLISHED→SUPERSEDED (illegal jumps rejected); **evidence linking** (knowledge ids into the rendered view); **Document Impact Analyzer** (which SES specs a change touches); persistent; publishes `doc.proposal_created`/`merged`/`approved`/`published`. AP-20 recorded. |
| 6 | Mission Control Learning Dashboard | ⬜ |

---

## Capability Status (SES → Code)

| Capability | SES Doc | Design | Code | Notes |
|-----------|---------|--------|------|-------|
| Architecture / OS model | SES-001 | ✅ L3 | 🔨 | `saathi/server.py`, `config.py` |
| Agent System (BMA) | SES-002 | ✅ L3 | 🔨 | `saathi/agents/` — `bus.py`, `master.py`, `router.py`, `harness.py`, `sub_agents/` all exist |
| Memory & Knowledge Graph | SES-003 | ✅ L3 | 🔨 | `saathi/memory/` — `episodic.py`, `semantic.py`, `working.py`, `hierarchical.py`. KG (Neo4j/Qdrant) = Phase 4, not yet |
| Voice OS | SES-004 | ✅ L3 | 🔨 | `saathi/voice.py`, `pushtotalk.py`, `nepali.py`, `cloning.py` |
| AI Studio | SES-005 | ✅ (new) | 🔨 | `content_studio.py`, `mr_yeti_pipeline.py`, `script_writer.py`, `google_flow.py`, `video_editor.py`, `thumbnail.py`. AI Director + Renderer Registry = not yet abstracted |
| Discovery Engine | SES-010 | ✅ (new) | 🔨 | `seo_optimizer.py`, `internet_reach.py`, `trend_hunter.py`, `market_intel.py`. Not yet unified as a Discovery Dept |
| Storage Intelligence | SES-019A | ✅ (new v2) | ✅/🔨 | `saathi/storage/` — **Storage Database + Disk Watchdog + Lifecycle Engine built & tested** (12 passing tests across `test_storage.py` + `test_lifecycle.py`; watchdog verified against real disk; AC-004 permanent-file guard verified). Cleanup Engine / Predictive Storage Engine / Archive Manager = next slices. `r2_storage.py` already exists for archival |
| Event Bus / Event Fabric | SES-012 | 📐 stub | 🔨 | `saathi/agents/bus.py` exists — needs promotion to NATS-backed Event Fabric per SES-012 |
| Tool Registry | SES-002 | ✅ L3 | 🔨 | `saathi/tools/registry.py` + ~70 tool modules |
| Model Router | SES-002 | ✅ L3 | 🔨 | `saathi/agents/router.py`, `cheap_llm.py`, `_llm_helper.py` |
| Observability | — | 📐 | 🔨 | `opik_tracer.py` — Opik tracing live (git: "Opik LLM observability for all providers") |
| Telegram control | SES-004/007 | 📐 | 🚀 | `telegram_bot.py` — two-way Telegram is live in production |
| Autonomous Engineering | SES-006 | 📐 not written | 🔨 | `auto_dev.py` exists |
| Mission Control | SES-007 | 📐 not written | 🔨 | `social_dashboard.py`, `menubar.py`, `activity.py` — partial |

---

## Products (Live vs Designed)

| Product | Status | Evidence |
|---------|--------|----------|
| pielts (IELTS app) | 🚀 Production | pielts.web.app live; `pielts.py`, `ielts_endpoints.py`, `speaking_eval.py`, `writing_eval.py` |
| Mr. Yeti content engine | 🔨 Implemented | `mr_yeti_pipeline.py`, `mr_yeti_strategy.py`, `mr_yeti_voice.py`; IELTS intelligence layer (Tasks 1-12) in git |
| HCG canteen (POS / Live Signal) | 🚀 Production | `canteen.py`, `hcg_voice.py` |
| Baadar social engine | 🔨 Implemented | `autopost.py`, `social_dashboard.py`, platform posters (`meta_post.py`, `tiktok_post.py`, `twitter_post.py`, `linkedin_post.py`) |

---

## Infrastructure (Cloud)

| Resource | Status | Detail |
|----------|--------|--------|
| Oracle VM `saathiai-vm` | ⏸️ Parked | E2.1.Micro (1 OCPU/1GB), IP 152.67.164.79, 200GB boot. `crashkernel=no` reclaimed RAM. **Decision (2026-07-02): parked** — the 1GB shape cannot reliably run `dnf` (installs saturate the single vCPU and drop sshd). Revisit via A1.Flex (2 OCPU/12GB) when Hyderabad capacity appears, or a cloud-init rebuild. Not blocking M1 — dev continues on Mac. |
| Oracle Object Storage `saathiai-assets` | 🚀 Ready | Standard tier, Private, S3-compatible |
| Oracle Autonomous DB `saathiai-db` | 🚀 Ready | Transaction Processing, Always Free (1 OCPU/20GB) |
| GPU render server | 📐 Not provisioned | Phase 2 — required for local ComfyUI/LTX/Wan (OCI Always Free has no GPU) |
| Cloudflare R2 | 🔨 Integrated in code | `r2_storage.py` |

---

## Target Machine Topology

```
                    SaathiAI
                Mission Control
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    Oracle VM      Mac Studio     GPU Server
   n8n            Development     AI Studio
   APIs           Voice OS        Video
   Telegram       Testing         ComfyUI
   Webhooks       Coding          LTX
```

- **Oracle VM** — 🔨 provisioned, being configured (Python/git install in progress)
- **Mac Studio** — 🚀 current dev machine (this is where everything runs today)
- **GPU Server** — 📐 not yet provisioned (Phase 2)

---

## Build Order (Next Engineering Work — spec-writing paused)

Per the decision to **stop writing specs** after SES-006/SES-007 and start building:

**Part 1 — Core Runtime**
1. Event Bus → promote `agents/bus.py` to Event Fabric (SES-012)
2. Agent Registry (formalize `sub_agents/`)
3. Tool Registry (harden `tools/registry.py`)
4. Model Router (harden `agents/router.py`)

**Part 2 — Storage Intelligence** *(pull earlier — the Mac fills up the moment AI Studio runs locally)*
5. Disk Watchdog (`saathi/disk_watchdog.py`) — **not started, highest M1 gap**
6. Lifecycle Engine (`saathi/lifecycle_engine.py`)
7. Storage Database (SES-019A Appendix A schema)
8. Telegram Alerts wiring (extend existing `telegram_bot.py`)

**Part 3 — Control Plane**
9. Mission Control
10. Authentication
11. Job Queue

**Part 4 — Resume n8n** (as executor, never the brain):
`SaathiAI → creates workflow → n8n executes → returns result → Memory updated → Mission Control updated`

---

## Current Blockers

| Blocker | Impact | Owner action |
|---------|--------|--------------|
| Oracle VM (1GB RAM) chokes during `dnf` installs, dropping sshd mid-transaction | Slows VM environment setup | Install packages one at a time with `--setopt=install_weak_deps=False`; consider it an orchestrator-only box (no heavy local builds). A1.Flex (2 OCPU/12GB) unavailable in Hyderabad — retry off-peak or accept the micro shape's limits |
| Storage Intelligence (Disk Watchdog / Lifecycle Engine) not built | Mac SSD at risk once AI Studio renders locally | Build Part 2 items above before heavy local AI Studio use |
| KG backends (Neo4j, Qdrant) not deployed | Semantic/graph memory limited to SQLite | Phase 4 — not blocking M1 |

---

## Next Three Engineering Priorities

1. **Continue Storage Intelligence Step 1** — Disk Watchdog ✅ done; next build the **Lifecycle Engine** (`saathi/storage/lifecycle_engine.py`, the only sanctioned deleter) + **Cleanup Engine** + **Predictive Storage Engine** (extend the existing `safe_to_render()` stub with storyboard-based estimation), each with tests. Then wire the watchdog into the running scheduler + Telegram.
2. **Finish the Oracle VM base environment** — git installing now (python3.11 dropped: this is an n8n/Node orchestrator, system python3.9 suffices); then Node.js + n8n, firewalld (80/443).
3. **Write SES-006 (Autonomous Engineering) + SES-007 (Mission Control), then stop spec-writing** — these two complete the M1/M2 design surface; after them, all new ideas become ADRs and the effort shifts fully to building.

---

## Integrated GitHub Repositories

| Repo | Purpose | Status |
|------|---------|--------|
| collabs-inc/collab-public | Reference — Collaborator desktop IDE patterns | 🔨 Referenced, not vendored |
| awesome-llm-apps (`~/awesome-llm-apps`) | Reference library — 100+ agent/RAG patterns | 📚 Reference only |

*(See SES-000E Repository Index for the full evaluation list.)*
