# M21.3 Residual Path Audit

**Milestone:** Platform M21.3 — Residual Inference Path Migration and Release-Check Enforcement  
**Baseline HEAD:** `32f0d31`  
**Schema:** `m21.3.residual_paths.v1`  
**Authority modules:** `saathi/inference/residual_paths.py`, `docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json`

## Completion gates

| Metric | Target | Result |
|--------|--------|--------|
| UNKNOWN count | 0 | **0** |
| DIRECT_PROVIDER_BYPASS count | 0 | **0** |
| UNCLASSIFIED count | 0 | **0** |
| production_certified | false | **false** |

## Inventory summary

| Classification | Count (approx) | Notes |
|----------------|----------------|-------|
| CANONICAL | 8 | ModelRouter, gateway, governance, preflight, release_check, console, ollama, runtime |
| COMPATIBILITY_ADAPTER / WRAPPED | 8 | cheap_ask, prose, compat, chat, llm_helper, server, cloud/openai engines |
| EXPLICIT_LEGACY_EXCEPTION | 4 | llm.generate HTTP, agent SDK, research grounding, OJ stub |
| FAKE_PROVIDER | 1 | FakeEngine tests |
| BLOCK | 2 | cheap proxy invoke, transitional unknown |

## Paths (abridged)

| Path ID | File | Symbol | Classification | Caller | Prod | M21.3 action |
|---------|------|--------|----------------|--------|------|--------------|
| model_router | saathi.model_router | ModelRouter | CANONICAL | — | Y | unchanged |
| governed_local_gateway | gateway_path | execute_governed_local_inference | CANONICAL | execution_gateway | Y | unchanged |
| legacy_llm_generate | saathi.llm | generate | EXPLICIT_LEGACY_EXCEPTION | legacy_llm_generate | Y | preflight + deprecate; freeze call sites |
| chat_engine | saathi.chat.engine | _default_llm | COMPATIBILITY_WRAPPED | chat_engine | Y | chat_adapter wrap |
| chat_adapter | chat_adapter | chat_generate | COMPATIBILITY_WRAPPED | chat_engine | Y | new |
| tools_llm_helper | tools/_llm_helper | ask_llm | COMPATIBILITY_WRAPPED | tools_llm_helper | Y | remove direct HTTP |
| agent_sdk_clients | saathi.agent | complete/respond | EXPLICIT_LEGACY_EXCEPTION | agent_runtime | Y | preflight gate |
| tools_research | tools/research | _grounded | EXPLICIT_LEGACY_EXCEPTION | research_tools | Y | preflight gate |
| cheap_ask | tools/cheap_llm | cheap_ask | COMPATIBILITY_ADAPTER | cheap_ask | Y | keep M21.2 |
| prose_clean | tools/prose | clean_prose | COMPATIBILITY_ADAPTER | prose_clean | Y | keep M21.2 |
| cheap_ask_legacy_proxy | cheap_llm | proxy invoke | BLOCK | — | N | remain blocked |
| transitional_unknown_caller | caller_policy | unknown | BLOCK | unknown | N | FORBIDDEN/disabled |
| release_check | release_check | run_release_check | CANONICAL | — | N | new enforcement |

## Runtime reachability notes

* **Chat:** public API → `chat_adapter.chat_generate` → preflight → optional governed → single legacy sink `llm.generate`.
* **Tools:** `ask_llm` → preflight → `llm.generate` only (no direct OpenAI/Groq/Gemini URLs).
* **Research:** Gemini google_search grounding retained (unique capability) behind preflight; expiry M22.
* **Agent:** SDK clients retained behind preflight on `complete`/`respond`; expiry M22.
* **Server:** inference via `ask_llm`; groq URL used only as non-generate health probe (allowlisted).

## Evidence tier

| Claim | Tier |
|-------|------|
| Static inventory complete for scanned residuals | A (repo AST + residual_paths registry) |
| Unknown production acceptance removed | A (caller_policy + contract + tests) |
| Direct HTTP removed from `_llm_helper` | A (source + release_check) |
| Live provider certification | NOT_TESTED (env-blocked) |
| Full repository suite | NOT_TESTED this session (bounded suite only) |

## Expiry map

| Exception | Expiry |
|-----------|--------|
| llm.generate HTTP callers | M22 |
| agent SDK clients | M22 |
| research grounding | M22 |
| openjarvis stub | M22 |
| chat full migration | M23 |
| cloud/openai_compat engines | M24 |
