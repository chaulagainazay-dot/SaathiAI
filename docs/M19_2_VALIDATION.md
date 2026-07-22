# M19.2 Validation

## Commands

```bash
# CI collection deps (workflow-level)
# reliability.yml installs: groq pyyaml + editable package

# Inventory / gap analysis
test -f docs/M19_2_CALLSITE_GAP_ANALYSIS.md
test -f docs/M19_2_SHADOW_ADOPTION.md

# M19.2 suite
python -m pytest tests/test_m19_2_shadow_adoption.py -q

# M19.1 regression
python -m pytest tests/test_m19_1_knowledge_adoption.py -q

# M19.0 regression
python -m pytest tests/test_m19_0_unified_knowledge.py -q

# M18.2 regression
python -m pytest tests/test_m18_2_codebase_memory.py -q

# Compile check
python -m compileall saathi/knowledge saathi/control_center/search.py -q

# Diff whitespace
git diff --check
```

## Acceptance checklist

- [x] CI disposition documented (Gate C + minimal install repair)
- [x] Second-wave inventory complete
- [x] Shadow campaign exists with required categories
- [x] Baseline + unified aggregate metrics recorded (via campaign report)
- [x] ≤2 callers adopted (CC repo search, repair context)
- [x] Legacy rollback available (default legacy)
- [x] Provenance / untrusted wrappers preserved
- [x] Context budgets supported
- [x] Security denials never fall back
- [x] Prompt-injection content cannot authorize tools
- [x] Trading Guardian isolated
- [x] InsForge not expanded
- [x] No merge / deploy

## Known limitations

* Campaign fixtures use synthetic search stubs in unit tests; live index quality varies by workspace index state.
* Sample size for p95 may be below threshold — report flags `insufficient_sample_for_p95`.
* Control Center repository facet is opt-in (`types=repository`); not default UX.
* Repair context is a facade — not auto-wired into auto-repair mutation loop.
* Unified ranking need not match legacy; prefer canonical evidence quality.
* Not production-ready.

## Verdict

See final session report after full validation run.
