# M19.5 Validation

## Commands

```bash
python -m pytest tests/test_m19_5_incremental_refresh.py -q
python -m pytest tests/test_m18_2_codebase_memory.py -q
python -m pytest tests/test_m19_0_unified_knowledge.py tests/test_m19_3_real_index_campaign.py tests/test_m19_4_context_composer.py -q
python -m compileall saathi/knowledge saathi/codebase_memory/service.py -q
git diff --check
```

## Results (this session)

| Gate | Result |
|------|--------|
| `tests/test_m19_5_incremental_refresh.py` | 17 passed |
| M18.2 regression | (run with commit suite) |
| TG isolation in refresh module | clean |
| Source mutation | none |

## Acceptance checklist

- [x] Identify current vs indexed commit
- [x] Detect changed / deleted / renamed files (git when available)
- [x] Refresh via incremental indexer (unchanged files skipped)
- [x] Remove stale chunks for deleted paths (M18.2 mark_deleted)
- [x] Repository fingerprint updated
- [x] Cache epoch invalidated on successful refresh
- [x] Multi-repo isolation
- [x] Interrupted refresh / stale lease recovery
- [x] Duplicate refresh → skipped_fresh when clean
- [x] Concurrent lease protection
- [x] Permission / secret path exclusion
- [x] Deterministic audit evidence
- [x] No source mutation
- [x] No large embedding downloads
- [x] TG / InsForge untouched
- [x] No merge / deploy

## Known limitations

* Full-walk mode does not pre-list changed paths (indexer still hash-skips).
* Rename detection quality depends on git similarity thresholds.
* No OS filesystem watcher; refresh is on-demand.
* Query result caches beyond `cache_epoch` meta are not process-global (KS has no durable query cache today).
* Not production auto-scheduled.

## Security analysis

* No permission expansion.
* Secret path exclusions preserved.
* No arbitrary network or clone.
* Lease meta is local sqlite only.
* No TG coupling.

## Rollback

* `CodebaseMemoryRuntime.refresh()` falls back to M18.2 index path if import fails.
* Revert M19.5 commit to remove knowledge refresh module; CLI `refresh` remains hash-incremental via indexer.

## Disable

Use M18.2 path only:

```python
from saathi.codebase_memory.indexer import index_repository
index_repository(project_root)  # direct
```

## Verdict

**M19.5 INCREMENTAL REFRESH READY** — pilot staging ready, not production-ready.
