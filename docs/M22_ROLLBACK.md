# M22 Rollback

## Soft rollback (config)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

Stops all inference paths including migrated facades.

## Git rollback (range)

Identify M22 commit range after push:

```bash
git log --oneline cc7fceb..HEAD
# Revert tip-first if needed:
git revert --no-edit <m22_tip>
# Or reset only on non-shared experimentation (never force-push shared branch without operator):
# git reset --hard cc7fceb
```

Preferred: `git revert` of M22 commits on `milestone/m7-security-engine`.

## What restores

* Pre-M22: HTTP in `llm.py`, SDK in `agent.py`, grounding URL in `research.py`
* Residual exception count returns toward 7
* Release allowlist again includes facades for SDK/URLs
