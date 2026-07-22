# M32 — Shadow Operations & Mode Distinctions

Modules: `runtime.py`, `models.py`

## Modes (`ExecutionMode`) — kept strictly distinct

| Mode | Meaning | M32 |
|------|---------|-----|
| `DRY_RUN` | Validate; **no** provider execution. | Exercised |
| `SIMULATION` | Deterministic local provider behaviour. | Exercised |
| `SHADOW` | Safe sandbox / read-only path; **non-authoritative**. | Exercised (over the local simulator) |
| `CANARY` | Production canary. | **PROHIBITED** — rejected |
| `ACTIVE` | Production active. | **PROHIBITED** — rejected |

`M32_ALLOWED_MODES = {DRY_RUN, SIMULATION, SHADOW}`;
`M32_PROHIBITED_MODES = {CANARY, ACTIVE}`. The runtime denies prohibited modes
(`mode_prohibited:*`) before any provider call, and eligibility denies them too.

## SHADOW guarantees

- Runs through full governance (validation, idempotency, bounded execution, health).
- Uses the local simulator only — never mutates production external state.
- Output is marked `authoritative = False` — never returned as authoritative
  production data.
- Cannot activate rollout, create an account link, or store a real credential.

## Important qualification

In M32, SHADOW runs over the **deterministic local simulator**, so it does not
prove live-provider compatibility. The highest verification state claimed is
`SIMULATION_VERIFIED` (see `M32_PROVIDER_VERIFICATION.md`). Local simulation is
never labelled live shadow verification, and shadow verification is never labelled
production readiness.
