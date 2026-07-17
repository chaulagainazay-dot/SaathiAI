# M21.3 Rollback

Restore **M21.2 checkpoint** content (`32f0d31`) by reverting **only** M21.3 commits (newest first).

M21.3 tip at close: `32b7a1d` (includes this rollback doc). Feature commit: `30eb5bc`.

```bash
cd /Users/macbookpro/SaathiAI
git checkout milestone/m7-security-engine
git pull --ff-only origin milestone/m7-security-engine

# Revert every commit after M21.2 tip (newest first). Adjust tip SHA if more
# M21.3 docs commits land after this file.
git log --oneline 32f0d31..HEAD
git revert --no-edit 32b7a1d
git revert --no-edit 739192e
git revert --no-edit ea7a0e8
git revert --no-edit 692e4e7
git revert --no-edit f27bbf1
git revert --no-edit 30eb5bc

git push origin milestone/m7-security-engine
```

After the revert stack, tree content matches M21.2 tip `32f0d31` (new revert commits on top; do not hard-reset shared history).

## Do not

* Revert M21.0 / M21.1 / M21.2 commits as part of M21.3 rollback
* Force-push or rewrite history
* Merge to main or deploy

## Verify after rollback

```bash
git status -sb
.venv/bin/python -m pytest tests/test_m21_2_provider_governance.py -q
```
