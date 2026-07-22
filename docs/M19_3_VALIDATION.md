# M19.3 Validation

## Commands

```bash
# Focused M19.3 suite
python -m pytest tests/test_m19_3_real_index_campaign.py -q

# Regressions
python -m pytest tests/test_m19_2_shadow_adoption.py -q
python -m pytest tests/test_m19_1_knowledge_adoption.py -q
python -m pytest tests/test_m19_0_unified_knowledge.py -q
python -m pytest tests/test_m18_2_codebase_memory.py -q

# Compile
python -m compileall saathi/knowledge -q

# Real-index campaign (requires local index; ensure creates if empty)
python - <<'PY'
from pathlib import Path
from saathi.knowledge.real_campaign import (
    ensure_index_current, run_real_index_campaign, write_campaign_report,
    promotion_evidence_summary,
)
root = Path(".").resolve()
print(ensure_index_current(root))
report = run_real_index_campaign(saathi_root=root, ensure_index=False)
print(promotion_evidence_summary(report))
write_campaign_report(report, root / "docs" / "M19_3_REAL_INDEX_METRICS.json")
PY

# Diff whitespace
git diff --check
```

## Results (this session)

| Gate | Result |
|------|--------|
| `tests/test_m19_3_real_index_campaign.py` | pass (15) |
| M19.2 + M19.1 + promotion-adjusted defaults | pass (52) |
| Real index ensure on SaathiAI | HEALTHY · 1387 files · 13981 chunks · commit `f40ee27` |
| Real campaign queries | 12 compared / 12 |
| permission_denial_correctness | **1.0** |
| context_budget_compliance | **1.0** |
| repository_selection_accuracy | **1.0** |
| stale_result_rate | **0.0** |
| canonical_source_hit_rate | **1.0** |
| top1_agreement | 0.5 (ranking may differ; expected) |
| top5_overlap | 0.6167 |
| no_result L/U | 0.0 / 0.0 |
| p50/p95 unified latency ms | ~351 / ~557 |
| promotion ready | **True** |
| promoted caller | `codebase_memory_search` → `unified_with_fallback` |
| secrets in metrics JSON | none |

Metrics artifact: `docs/M19_3_REAL_INDEX_METRICS.json`

## Acceptance checklist

- [x] Registered indexes inspected
- [x] Index current enough for evaluation (HEALTHY)
- [x] Bounded representative query set
- [x] Legacy + unified dual path on real index
- [x] Required metrics recorded (aggregate only)
- [x] Exactly one low-risk caller promoted
- [x] Per-caller + global disable controls
- [x] Regression tests for M19.0–M19.2 + promotion
- [x] Zero permission violations on campaign
- [x] Zero secret leaks in report
- [x] Provenance path preserved via KS adapters
- [x] No security-denial fallback change
- [x] Rollback documented and tested
- [x] Trading Guardian isolated
- [x] InsForge not expanded
- [x] Chat LTM deferred
- [x] No merge / deploy

## Known limitations

* Sample size n=12 → `insufficient_sample_for_p95` warning (min 20).
* Top-1 agreement 0.5 vs legacy — unified ranking prioritizes multi-source
  evidence; not required to match legacy order.
* Only the primary `saathiai` codebase index is evaluated; multi-repo
  registered indexes beyond documentation adapters are not separate clones.
* Promotion is pilot default only; other first/second-wave callers remain legacy.
* Not production-ready; not adopted globally.
* CI critical manifest still has pre-existing env failures (disk, native Linux,
  ffmpeg) unrelated to M19.3.

## Security analysis

* No permission expansion.
* No tenant leakage observed (single-tenant fixture + registry).
* No secret path hits in campaign.
* No arbitrary shell/MCP/SQL from retrieval.
* No TG / InsForge coupling.
* Retrieved injection strings cannot authorize tools (existing safety module).

## Rollback

```bash
export SAATHI_KS_ROLLOUT_CODEBASE_MEMORY_SEARCH=legacy
# or
export SAATHI_KS_DISABLE_PROMOTIONS=1
# or
export SAATHI_KS_ROLLOUT=legacy
```

Git: revert the M19.3 commit(s) if a hard rollback is required.

## Disable procedure

Same as rollback. Confirm with:

```python
from saathi.knowledge.rollout import resolve_mode, rollout_snapshot
print(resolve_mode("codebase_memory_search"))
print(rollout_snapshot()["promoted_defaults"])
```

## Verdict

**M19.3 REAL-INDEX PILOT PROMOTED** — pilot staging ready, not production-ready.
