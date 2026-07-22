# M19.4 Validation

## Commands

```bash
python -m pytest tests/test_m19_4_context_composer.py -q
python -m pytest tests/test_m19_3_real_index_campaign.py tests/test_m19_2_shadow_adoption.py tests/test_m19_1_knowledge_adoption.py tests/test_m19_0_unified_knowledge.py -q
python -m compileall saathi/knowledge -q
git diff --check
```

## Results (this session)

| Gate | Result |
|------|--------|
| `tests/test_m19_4_context_composer.py` | 15 passed |
| M19.1–M19.3 regressions with M19.4 | 82 passed (combined run) |
| compileall `saathi/knowledge` | ok |
| Trading Guardian imports in composer | none |
| `authorizes_tools` always false | tested |
| Injection boundary in prompt | tested |

## Acceptance checklist

- [x] One canonical composer module
- [x] Consumes M19.0 Knowledge results only
- [x] All 10 structured section kinds represented
- [x] Profiles: coding, repair, audit, architecture, incident
- [x] Budget / per-source / per-repo quotas
- [x] Primary preference + dedupe
- [x] Provenance + trust labels
- [x] Truncation + excluded reasons + fingerprint
- [x] Prompt-injection boundaries
- [x] No tool authorization from composition
- [x] Adoption facades attach `composed` when unified results exist
- [x] No second Knowledge Service
- [x] TG / InsForge untouched
- [x] No merge / deploy

## Known limitations

* Section classification is heuristic (path/evidence class); not LLM-based.
* Soft section quotas can sum above global budget; global trim drops low-priority sections.
* Memory LTM section only fills when memory adapter returns results (still deferred for promotion).
* Mission/repair callers remain default legacy; composition attaches only on unified path.
* Not production-ready.

## Security analysis

* No permission expansion.
* No secret leakage pathways added.
* Retrieved injection phrases remain data.
* No arbitrary shell/MCP/SQL.
* No Trading Guardian coupling.

## Rollback

* Composer is additive. Disable by not consuming `composed` / `prompt_block_composed`.
* Mission/repair remain legacy by default.
* Revert M19.4 commit if hard rollback required.

## Disable procedure

No global flag required. Consumers may ignore `payload["composed"]`.
To avoid composer attachment entirely, use legacy mode for those callers
(default) or pin an older revision.

## Verdict

**M19.4 CONTEXT COMPOSER READY** — pilot staging ready, not production-ready.
