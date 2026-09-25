# DAILY_WEEKLY_LOSS_POLICY

- Day: UTC midnight → now
- Week: Monday 00:00 UTC → now
- Loss = max(0, −pnl_pct vs period baseline NAV)
- Fail closed / informational when baseline missing (first observation)
- No silent manual reset

