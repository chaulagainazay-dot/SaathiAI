# M21.3 Final Report

## Verdict

```text
M21.3 COMPLETE WITH LIMITATIONS — RESIDUAL PATHS CLASSIFIED AND RELEASE-CHECK ENFORCED; LIVE CERTIFICATION BLOCKED
```

## Delivered

* Residual path audit + machine registry (`residual_paths` v1 M21.3)
* Exception manifest (`docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json`)
* Release check CLI (`python -m saathi.inference.release_check`)
* Chat compatibility adapter
* `llm.generate` deprecated preflight facade; call sites frozen
* `_llm_helper` direct HTTP chain removed
* Agent / research preflight gates
* Transitional `unknown` caller FORBIDDEN/disabled everywhere
* Caller registry extensions (tools_llm_helper, research_tools, agent_runtime, server_tools)
* M20 console `residual-inference`
* Focused tests `tests/test_m21_3_residual_path_migration.py`
* Docs M21_3_* + Brain/Business/loop updates

## Limitations

* `llm.generate` HTTP DEFAULT_CALLERS remain EXPLICIT_LEGACY_EXCEPTION (M22)
* Agent multi-provider SDKs remain EXPLICIT_LEGACY_EXCEPTION (M22)
* Research Gemini grounding remains EXPLICIT_LEGACY_EXCEPTION (M22)
* Chat not fully governed by default (COMPATIBILITY_WRAPPED; M23)
* Live Ollama ENVIRONMENT_BLOCKED
* Circuit / daily cost still process-local (M21.2 debt)
* Full repository test suite NOT_RUN
* `production_certified=false`

## Next

Operator authorizes **M21.4** only (or program roadmap next slice). Do not auto-start M22.
