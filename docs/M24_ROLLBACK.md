# M24 Rollback

## Code

```bash
git log --oneline -20
git revert <m24-commit-range>   # preferred; do not force-push
# or checkout prior tag/commit on a branch
```

## Database

```python
from saathi.inference.governance_store import DurableGovernanceStore
DurableGovernanceStore("data/provider_governance.db").downgrade()
```

Downgrade drops only M24 governance tables. Does not touch chat.db or trading state.

## Residual manifest

Restore prior manifest from git history if rolling back residual-exception count expectations.

## Notes

* Process-local circuit behavior returns only if code is reverted.
* Do not set `production_certified=true` during rollback.
