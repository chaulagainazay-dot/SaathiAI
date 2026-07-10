# M9 Memory Engine — Existing System Audit (Phase 1)

**Date:** 2026-07-10 · **Branch:** `milestone/m7-security-engine` @ `f8ef49c`

## What exists in `saathi/memory/`

| Module | Role | M9 disposition |
|--------|------|----------------|
| `platform.py` (343L) | `Episode`, `Knowledge`, `MemoryScope`, `RetentionPolicy`, `PromotionState`, `retention_expiry`, promotion state machine, cross-product firewall | **REUSE** — import the enums + `retention_expiry` verbatim; the M9 engine builds on these scopes/retention/promotion semantics |
| `promotion.py` (236L) | deterministic extractor + promotion engine (episodes → knowledge) | **REUSE pattern** — M9 extraction mirrors the deterministic-first approach |
| `evidence.py` (142L) | `find_contradictions`, `_tokens`, `_topic_overlap`, evidence scoring | **REUSE** — M9 conflict detection delegates to `find_contradictions` semantics |
| `review_queue.py` (299L) | human review queue + auto-approval policy | REUSE-compatible — M9 conflicts route here in future; not required for core |
| `semantic.py` (87L) | Chroma-optional **keyword pattern** store (IELTS error patterns) | KEEP — domain-specific (student weaknesses), not general memory; not replaced |
| `episodic.py`, `working.py`, `hierarchical.py`, `_legacy.py` | small stores + IELTS legacy | KEEP — used elsewhere; M9 does not touch |

## Infrastructure reality

- **Chroma: NOT installed.** `sentence-transformers: NOT installed.** `numpy: 2.4.6 present.**
- Implication: real vector similarity is achievable **in-process with numpy** using a
  deterministic local embedder — no external service required. Cloud/ST/Ollama
  adapters are provided behind one interface but are **adapter-ready, not tested**
  (no libs/keys in this environment). Reported honestly, never faked.

## Current ChatEngine retrieval

`saathi/chat/engine.py::_retrieve_memory` (M8) = keyword search over conversation
content + mission knowledge nodes, writing `memory_link` rows. This is the exact
seam M9 replaces: same method, upgraded internals, stable interface.

## Conflicts / duplication

None blocking. Two "semantic" concepts coexist (`memory/semantic.py` = IELTS
patterns; M9 = general semantic memory) — disambiguated by living in
`saathi/memory/engine/`. No table-name collisions (M9 uses a fresh `data/memory.db`).

## Integration path (chosen)

New subpackage `saathi/memory/engine/` with the canonical M9 schema in
`data/memory.db`, reusing `platform.py` enums + `evidence.find_contradictions`.
`ChatEngine._retrieve_memory` rewired to call `MemoryEngine.retrieve_for_chat`
behind the unchanged `SendResult.memory_links` contract. No existing memory
module is modified; no existing data destroyed.

## Migration risks

- Low: additive package + new db file. Existing tables untouched.
- Embedding-dimension drift handled by `embedding_version` tracking + controlled
  re-index. Keyword fallback guarantees chat never blocks on vector failure.
