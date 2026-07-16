# M20.3 — Opt-In LLM Caller Migration

**Date:** 2026-07-16  
**Starting HEAD:** `f38ca66` (M20.2)  
**Branch:** `milestone/m7-security-engine`  
**Status:** Adoption pilot (not global migration)

---

## 1. Call-site inventory (pre-implementation)

| Caller | File / symbol | Subsystem | Task | Path today | Latency | Risk | Classification |
|--------|---------------|-----------|------|------------|---------|------|----------------|
| Chat turn | `saathi/chat/engine.py` ChatLLMAdapter | chat | dialogue | `llm.generate` STANDARD | user-facing | high | `KEEP_LEGACY` / `DEFER_LATENCY_CRITICAL` |
| ask_llm hub | `saathi/tools/_llm_helper.ask_llm` | studio tools | multi-purpose | `llm.generate` + inline chain | medium | high (fan-out) | `DEFER_SAFETY_CRITICAL` (too many consumers) |
| cheap_ask | `saathi/tools/cheap_llm.cheap_ask` | ops tools | screening summary/rewrite | `llm.generate` SCREENING COST | medium | low | **`MIGRATE_IN_M20_3`** |
| clean_prose | `saathi/tools/prose.clean_prose` | content polish | rewrite | `infrastructure.llm.generate` | medium | low | **`MIGRATE_IN_M20_3`** (+ shadow) |
| score_prose | `saathi/tools/prose.score_prose` | content polish | classify scores | same | medium | low | `SHADOW_IN_M20_3` deferred (sibling) |
| content studio / script / SEO / quotes / … | many `._llm_helper` consumers | production content | creative | ask_llm | high | high | `KEEP_LEGACY` |
| ielts_endpoints | direct Groq SDK | education | explain/grade | Groq stream | high | high | `DEFER_LATENCY_CRITICAL` |
| directors / ai_studio / client_intake / workspace | `infrastructure.llm.generate` | product | planning/JSON | STANDARD | medium | medium–high | `KEEP_LEGACY` |
| creative_director / script_director / studio_directors | generate JSON plans | studio | planning | STANDARD | medium | medium | `KEEP_LEGACY` |
| writing_eval / speaking_eval | OpenAI SDK | eval | scoring | direct provider | medium | medium | `KEEP_LEGACY` |
| gateway_path / ModelGateway | inference package | platform | governed local | M20.2 | n/a | n/a | `NOT_REAL_CALLER` (path itself) |
| tests | various | test | fixtures | injected callers | n/a | n/a | `NOT_REAL_CALLER` |
| Trading Guardian / trade execution | no `llm.generate` | finance | n/a | none | n/a | n/a | not migrated |
| voice turn / kill switch / auth / payment | various | safety | critical | not via this pilot | n/a | critical | `DEFER_SAFETY_CRITICAL` |

### Selected (≤2)

1. **`cheap_ask`** — operator/routine screening text; dict `{reply, model, cost}`; SCREENING/COST; no streaming; good fallback story.  
2. **`prose_clean`** — non-user-chat prose cleanup; dict `{cleaned, lengths}`; STANDARD rewrite; excellent shadow candidate.

### Deferred (explicit)

- Global chat, voice, all `_llm_helper` fan-out, IELTS streaming, directors, client intake, creative pipelines, Trading Guardian (none present as LLM callers).

---

## 2. Rollout modes (per caller)

| Mode | Behaviour |
|------|-----------|
| `legacy` | Existing `llm.generate` only (**default**) |
| `shadow` | Legacy authoritative; governed local runs for metrics only |
| `governed_local_with_fallback` | Governed local first; soft failures → legacy |
| `governed_local_only` | Governed local only; no legacy |

Env:

* `SAATHI_INF_ROLLOUT` — global default (`legacy`)
* `SAATHI_INF_ROLLOUT_CHEAP_ASK`
* `SAATHI_INF_ROLLOUT_PROSE_CLEAN`
* Requires `SAATHI_INFERENCE_ENABLED=1` and `SAATHI_INFERENCE_GATEWAY_ENABLED=1` for non-legacy modes to actually hit local engines

---

## 3. Compatibility adapter

`saathi/inference/compat.py` — builds `InferenceRequest`, invokes `execute_governed_local_inference`, maps to caller shapes, records metrics. Does **not** re-route models or open Ollama directly.

## 4. Fallback policy

**Allowed:** engine/model unavailable, timeout, provider unavailable, malformed response, concurrency saturation.  
**Denied (never fallback):** capability/security/sensitivity denial, prompt too large, inference/gateway disabled when mode is `governed_local_only`, tool-use/streaming/cloud policy denials.

## 5. Disable / rollback

```bash
unset SAATHI_INF_ROLLOUT SAATHI_INF_ROLLOUT_CHEAP_ASK SAATHI_INF_ROLLOUT_PROSE_CLEAN
# or set =legacy
# inference path remains off without:
# SAATHI_INFERENCE_ENABLED / SAATHI_INFERENCE_GATEWAY_ENABLED
```

```bash
git revert <m20.3-sha>
```

## 6. Not claimed

Global chat migration · all `llm.generate` · streaming · model download · 8B models · automatic cloud fallback · Trading Guardian changes · production enablement.
