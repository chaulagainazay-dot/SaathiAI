# M19.4 — Context Composer and Mission Context Quality

**Status:** Pilot (not production-ready)  
**Base:** M19.0 Knowledge Service + M19.1 adoption + M19.3 real-index pilot  
**Verdict target:** `M19.4 CONTEXT COMPOSER READY`

---

## Purpose

Provide one canonical **context composer** that turns Knowledge Service results
into structured, budgeted, provenance-preserving, mission-ready context packages
for coding, repair, audit, architecture, and incident work.

Does **not** create a second Knowledge Service. Consumes M19.0
`KnowledgeResult` / `KnowledgeResponse` only.

---

## Module

`saathi/knowledge/composer.py`

| API | Role |
|-----|------|
| `ComposerProfile` | coding / repair / audit / architecture / incident |
| `compose_context(results, …)` | pure composition from result list |
| `compose_from_response(resp, …)` | composition from KS response |
| `compose_for_mission(ks, objective, …)` | retrieve + compose |
| `ComposedContext` | structured package + prompt text |

Adoption integration (optional enrichment when unified results exist):

* `mission_context_prepare` → `composed` + `prompt_block_composed` (coding profile)
* `repair_context_prepare` → `composed` (repair profile)

---

## Structured sections

1. Governing policies (authority shell — operator supplied / default KS policy)
2. Mission objective (authority shell)
3. Implementation (primary code)
4. Related tests
5. Architecture documentation
6. Milestone decisions
7. Known limitations
8. Operational runbooks
9. Relevant memory
10. Lower-trust generated / external evidence

Section order and soft quota fractions vary by `ComposerProfile`.

---

## Required controls

| Control | Implementation |
|---------|----------------|
| Character budget | Hard/soft section quotas + global trim |
| Per-source quota | via `assemble_context` + section item caps |
| Per-repository quota | via `assemble_context(max_per_repo=…)` |
| Min source diversity | warning when below threshold |
| Primary-source preference | sort primary evidence before generated |
| Duplicate suppression | `dedupe_results` before fill |
| Provenance | path/source/evidence/trust/fp + safe provenance keys |
| Truncation reporting | `truncated` flags + excluded reasons |
| Excluded reasons | section_budget, repo_quota, global_budget_drop_section, … |
| Context fingerprint | hash of profile + objective + included ids |
| Trust labels | high / medium / low / untrusted per block |
| Prompt-injection boundaries | `wrap_retrieved_context` on evidence body |
| Tool authorization | always `authorizes_tools=False` |

Authority vs data partition in `prompt_text`:

```
=== GOVERNING_SAATHIOS_POLICY (authority) ===
=== MISSION_OBJECTIVE (authority) ===
<<<RETRIEVED_EVIDENCE untrusted=true …>>>
…sections…
<<<END_RETRIEVED_EVIDENCE>>>
```

---

## Profile → retrieval profile map

| Composer | KS RetrievalProfile |
|----------|---------------------|
| coding_mission | CODE_EXPLAIN |
| repair_mission | CODE_EXPLAIN |
| audit_mission | AUDIT_EVIDENCE |
| architecture_review | CODE_EXPLAIN |
| incident_diagnosis | MISSION_CONTEXT |

---

## Security

* Retrieved text cannot authorize tools, trades, deploys, or policy overrides.
* Trading Guardian not imported or engaged.
* InsForge not expanded.
* Composer failures never raise into adoption hot paths (warnings only).

---

## Out of scope

* Auto-promotion of mission/repair callers (remain legacy default)
* Chat LTM promotion
* Production deployment
* M19.5 incremental refresh
