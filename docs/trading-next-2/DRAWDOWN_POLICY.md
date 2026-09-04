# DRAWDOWN_POLICY

From NAV history series (risk history store + ledger NAV):

```text
drawdown = (peak_nav - current_nav) / peak_nav
```

Hard limit vs `max_drawdown`. UI must not compute independently.

