# M39 — Interruption and Recovery

## Offline validation

**PASSED** (safe offline paths)

| Case | Result |
|------|--------|
| Interrupt after provider, before cleanup | CLEANED + recovery |
| Cancel before second provider call | handle closed |
| Kill switch blocks new calls | fail closed |
| Recovery no secret reopen from evidence | enforced |
| Duplicate recovery | idempotent |

## Live interruption

**NOT_EXERCISED** (requires operator live session)

## Kill switch

- `SAATHI_M39_KILL_SWITCH=1`
- `m39-interrupt-session`
- Does not grant authority; preserves evidence; closes handles / revokes leases
