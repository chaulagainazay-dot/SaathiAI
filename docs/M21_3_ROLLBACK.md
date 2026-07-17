# M21.3 Rollback

Restore **M21.2 checkpoint** `32f0d31` by reverting **only** M21.3 commits (newest first).

```bash
cd /Users/macbookpro/SaathiAI
git checkout milestone/m7-security-engine
git pull --ff-only origin milestone/m7-security-engine

# Replace with actual M21.3 SHAs after push (newest first):
git revert --no-edit <newest-M21.3-commit>
git revert --no-edit <previous-M21.3-commit>
# …repeat for each M21.3 commit…

git push origin milestone/m7-security-engine
```

## Do not

* Revert M21.0 / M21.1 / M21.2 commits as part of M21.3 rollback
* Force-push or rewrite history
* Merge to main or deploy

## Verify after rollback

```bash
git rev-parse HEAD   # should match 32f0d31 after full M21.3 revert stack
git status -sb
.venv/bin/python -m pytest tests/test_m21_2_provider_governance.py -q
```
