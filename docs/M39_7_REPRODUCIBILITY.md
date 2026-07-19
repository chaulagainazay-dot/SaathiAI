# M39.7 — Reproducibility & Clean-Environment Validation

**Status:** REPRODUCIBLE_AND_SELF_CONTAINED (offline).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_7.py`.
**Tests:** `tests/test_m39_7_reproducibility.py` — 28 passed.
**Evidence:** `docs/evidence/m39_7/` (deterministic; leak-clean).

## Purpose

Prove the M39.x offline surface is reproducible and self-contained.

## Checks

- **Byte-for-byte reproducibility** — each of the 5 M39.x evidence builders is
  built twice and compared canonically; a file-level emit/re-emit is compared
  byte-for-byte. All reproducible, all leak-clean.
- **Dependency self-containment** — AST inspection of all M39.x modules confirms
  only allowlisted top-level packages are imported (stdlib + `saathi`); no
  network library (`requests`/`httpx`/`urllib3`/`aiohttp`/`socket`) at import.
- **CLI contract** — 29 documented M39.x commands enumerated; a representative
  read-only subset is executed through `cli.main` and must return a handled exit
  code (0 or 5), never an argparse "invalid choice".

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. Trading Guardian
**UNENGAGED**.

## Reproduce

```bash
python -m pytest tests/test_m39_7_reproducibility.py -q
python -m saathi.credentials.cli m39-7-reproduce
python -m saathi.credentials.cli m39-7-dependencies
python -m saathi.credentials.cli m39-7-emit-evidence   # deterministic
```
