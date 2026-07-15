# M19.1 Validation

## Commands

```bash
# Inventory presence
test -f docs/M19_1_RETRIEVAL_CALLSITE_INVENTORY.md

# M19.1 suite
python -m pytest tests/test_m19_1_knowledge_adoption.py -q

# M19.0 regression
python -m pytest tests/test_m19_0_unified_knowledge.py -q

# M18.2 regression
python -m pytest tests/test_m18_2_codebase_memory.py -q

# Formatting check on touched sources
python -m compileall saathi/knowledge saathi/codebase_memory/service.py -q

# Diff whitespace
git diff --check
```

## Acceptance checklist

- [x] Call-site inventory complete with classifications
- [x] First-wave callers use KnowledgeService via adoption gateway
- [x] No direct adapter calls from first-wave facades
- [x] Legacy default preserves M18.2 behaviour
- [x] Shadow does not change authoritative results
- [x] Fallback never on security denial
- [x] Provenance survives compat mapping
- [x] Prompt-injection boundaries present
- [x] TG isolation tests
- [x] No push / merge / deploy

## Known limitations

* Mission/audit facades have empty legacy no-ops (opt-in unified/shadow).
* Chat LTM and voice paths remain legacy (deferred).
* Shadow doubles retrieval cost when enabled — sample carefully.
* No production rollout recommended.
