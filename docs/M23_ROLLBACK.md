# M23 — Rollback

## Preconditions

* On branch `milestone/m7-security-engine`
* Do **not** force-push
* Do **not** rewrite M21/M22 history

## Soft disable (preferred)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

Blocks all chat inference at preflight without code rollback.

## Git rollback of M23 commit range

After identifying M23 commit SHAs from `git log --oneline`:

```bash
cd /Users/macbookpro/SaathiAI
git log --oneline --grep=m23 -20
# Revert in reverse order (newest first), one commit at a time:
git revert --no-edit <m23_tip_sha>
# repeat for each M23 commit if needed
```

If a single squashed implementation commit exists:

```bash
git revert --no-edit <m23_implementation_sha>
```

## Verify after rollback

```bash
.venv/bin/python -m pytest tests/test_m22_provider_migration.py -q
.venv/bin/python -m saathi.inference.release_check
git status -sb
```

## Notes

* Conversation DB schema unchanged by M23 — no data migration reverse required
* Residual manifest will return chat exception only if code is fully reverted
