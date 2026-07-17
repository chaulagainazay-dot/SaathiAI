# M21.4 — Rollback

## Scope

Rollback only M21.4 commits on `milestone/m7-security-engine`.  
Do **not** rewrite M21.0–M21.3 history.

## Soft disable (no code rollback)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
```

## Git rollback (operator)

```bash
cd /Users/macbookpro/SaathiAI
git fetch origin
# Identify M21.4 tip vs parent (see FINAL_REPORT commits)
git log --oneline -15
# Revert M21.4 commit range (preferred) or reset only if not shared:
# git revert --no-edit <m21.4_first>^..<m21.4_last>
```

## Files introduced / primarily owned by M21.4

* `saathi/inference/runtime_gate.py`  
* `tests/test_m21_4_runtime_consolidation.py`  
* `docs/M21_4_*`  
* Edits: `ops/release_gate.py`, `m20_console/cli.py`, `prod_config.py`, `critical_checks.json`  

## Verify after rollback

```bash
.venv/bin/python -m saathi.inference.release_check --explain
.venv/bin/python -m pytest tests/test_m21_3_residual_path_migration.py -q
```
