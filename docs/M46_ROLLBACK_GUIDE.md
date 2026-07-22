# M46 — Rollback Guide

## Operational

- Kill switch: `SAATHI_M39_KILL_SWITCH=1` aborts live paths.
- Approval expiry invalidates further runs.
- Live canary auto-stops pending revocation; does not expand scope.

## Code removal

M46 is additive. Remove `saathi/credentials/m46.py`, tests, docs/M46_*,
docs/evidence/m46, docs/m46, CLI m46 block, and gitignore m46 lines.

Historical M39–M45 evidence is not modified by M46.
