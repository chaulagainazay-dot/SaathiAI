# M2 Step 0 — Memory System Audit

**Question:** *What does SaathiAI already know how to remember?*
**Method:** two parallel read-only auditors — one on `saathi/memory/` code, one on SES-003 requirements.
**Date:** 2026-07-03 · Branch: `milestone/m2-learning-runtime`

---

## The headline finding

There are **two unrelated memory systems** in the tree:
- **(A)** the tiered `saathi/memory/` package — the real one, wired into `MasterAgentLoop` (`observe → get_context`, `update_memory → store_interaction`).
- **(B)** `saathi/memory.py` (top-level) — a flat `Memory` class, **byte-identical to `_legacy.py`, and dead**: Python resolves the *package*, so the top-level module is shadowed. → **Cleanup candidate.**

And the current system is **IELTS-shaped, not platform-shaped**: episodic records are `(student_id, skill, band_est)`, not the SES-003 generic `(agent, department, product, intent, outcome, quality_score)`. The memory works well for pielts tutoring but is not yet a platform capability.

---

## Audit table

| SES-003 Capability | Exists | Quality | Gap | Action |
|--------------------|:------:|---------|-----|--------|
| **L0 Working Memory** | ✅ | Good | Keyed by `student_id` not session; not persistent; missing entry metadata (`role`, `tool_name`, `tool_result`, `token_estimate`) | **Patch** |
| **Episodic Memory (L1)** | ✅ | Good (persistence) | Schema is IELTS-specific; missing SES-003 fields: `agent/department/product/intent/outcome/quality_score/promoted/expires_at/retention_policy`; no FTS5 | **Extend** (schema) |
| **Semantic Memory (L2)** | ⚠️ | Partial | It's a SQLite pattern-*counter*, not semantic; **ChromaDB init is dead code**; missing `pattern_key/category/scope/confidence/evidence_count/source_episodic_ids/embedding_id` | **Extend** (schema + confidence) |
| **Hierarchical / Tiered (L0–L5)** | ⚠️ | Partial | Only 3 tiers exist; SES-003 defines 6 (L0–L5) with L3 KG, L4 Organizational, L5 Archive; no promotion path between tiers | **Extend** |
| **Memory Retrieval** | ⚠️ | Partial | Only recency + count ordering + naive keyword; no FTS5, no vector (Qdrant), no RRF hybrid, no compound re-ranking (`0.4 rel + 0.3 recency + 0.2 conf + 0.1 product`) | **Build** (reranker) |
| **Memory Compression** | ❌ | Missing | No summarizer in the tiered stores; `memory_reflector` writes markdown from an unrelated `feedback` table | **Build** |
| **Promotion Engine** | ❌ | Missing | Tiers are written **in parallel** at interaction time — no consolidation job, no episode→pattern promotion (`≥2 similar, confidence ≥ 0.5`, 3-day age) | **Build ⭐ Core M2** |
| **Knowledge Graph Sync** | ❌ | Missing | No `kg_nodes`/`kg_edges`, no node/edge types, no versioning/SUPERSEDES | **Build** (M2 Phase 4) |
| **Context Assembly** | ✅ | Good (wired) | Only 2 sources (recent + weaknesses); no token budget (~1,800), no 10-layer priority pipeline, no reverse-priority compression | **Improve** |
| **Learning Engine** | ❌ | Missing | Only stamps `metadata["learned_patterns"]` + cross-skill bus notes; no outcome/success analysis, no QA rubric (weighted ≥0.72), no capability proposals | **Build ⭐ Core M2** |
| **Memory Governance** | ❌ | Missing | No retention matrix, no cross-product firewall (`FIREWALL_PRODUCT_SCOPES`), no `memory_audit_log` | **Build** (governance phase) |

---

## What this tells us we're actually building in M2

**Keep / clean up (small):**
- Delete the dead shadowed `saathi/memory.py` duplicate.
- Remove the dead ChromaDB stub in `semantic.py` (misleading docstring).

**Extend existing foundations (medium):**
- Episodic + Semantic schemas → SES-003 generic platform schema (add promotion-tracking + retention + confidence fields). This is the load-bearing prerequisite for everything else — you can't promote episodes that don't carry `promoted`/`quality_score`/`intent`.

**Build net-new (the M2 flagships):**
- **Promotion Engine** — the daily consolidation job (episodes → clusters → patterns → L2), gated by the **Review Queue**.
- **Learning Engine** — outcome analysis + QA rubric + capability proposals.
- **Memory Quality Scorer** — specificity/evidence/reusability/cross-product/contradiction, feeding the Review Queue.
- **Context Assembly upgrade** — the 10-layer, token-budgeted pipeline.
- **Knowledge Graph** (SQLite adjacency, Phase 1) + **Brain Synchronizer** (routes promoted knowledge to Brain.md / Business.md / Writing Style / ADR candidate).

**Governance (your enhancement, correctly first-class):**
- **Knowledge Promotion Review Queue** — auto-approve (high-confidence, low-risk) / human-review (strategic) / reject — before anything reaches L2, the KG, or the living docs. This is AP-14 applied to knowledge.
- **L6 — Platform Wisdom** (already recorded in Brain.md §6b): the constitution; human-approved promotion only.

---

## Recommended M2 build order (revised by the audit)

The audit changes the order slightly: **schema-extend before engine-build**, because the Promotion Engine needs promotion-tracking fields to exist first.

| Phase | Work | Why now |
|-------|------|---------|
| **1a** | Extend episodic + semantic schemas to SES-003 generic (promotion + retention + confidence fields); delete dead duplicates/stub | Prerequisite for every engine |
| **1b** | **Memory Promotion Engine** (episode clustering → pattern extraction → L2) | M2 flagship |
| **2** | **Memory Quality Scorer** + **Knowledge Promotion Review Queue** | Governance gate before knowledge is trusted |
| **3** | **Learning Engine** (outcome analysis → QA rubric → capability proposals) | Turns execution into improvement |
| **4** | **Knowledge Graph** (SQLite `kg_nodes`/`kg_edges`) + sync | Structured knowledge |
| **5** | **Brain Synchronizer** (Brain.md / Business.md / Writing Style / ADR) | Living docs |
| **6** | **Mission Control Learning Dashboard** (promoted today / rejected / avg confidence / KG nodes) | Visibility |

**M2 success criterion:** *SaathiAI learns from completed work and measurably improves future decisions without manual prompt edits.*
