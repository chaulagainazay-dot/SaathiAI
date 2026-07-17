# M25 Rollback

```bash
git log --oneline -15
git revert <m25-commit-range>   # preferred; no force-push
```

Evidence under `docs/evidence/m25/` may be deleted safely; it does not affect runtime without the module.

Does not touch Trading Guardian, chat.db, or provider installs.
