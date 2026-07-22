# M21.2 — Rollback

Restore M21.1 checkpoint without rewriting M21.0/M21.1 history.

Newest-first reverts (replace SHAs with actual M21.2 commits after push):

```bash
git revert <newest-M21.2-commit>
git revert <previous-M21.2-commit>
# … for each M21.2 commit newest → oldest
git push origin milestone/m7-security-engine
```

Do **not** include M21.0 or M21.1 commits in M21.2 rollback.

Disable without revert:

```bash
export SAATHI_INFERENCE_KILL_ALL=1
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
```
