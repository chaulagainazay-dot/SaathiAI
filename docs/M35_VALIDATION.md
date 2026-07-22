# M35 — Validation

## Focused M35 tests

| Suite | Result |
|-------|--------|
| `test_m35_credential_security.py` | 99 passed |
| `test_m35_credential_lifecycle.py` | 67 passed |
| `test_m35_sandbox_sessions.py` | 44 passed |
| `test_m35_certification_and_evidence.py` | 17 passed |
| **Total focused M35** | **227 passed** |

## Regression

| Scope | Result |
|-------|--------|
| M31 (`test_m31_credentials.py`) | 43 passed |
| M32 provider adapter/runtime | included below |
| M32–M34 provider governance (8 files) | 387 passed |
| Full repository suite (`pytest -q`) | _see below_ |

## Full suite

Initial full run (`pytest -q`, 710.79s): `59 failed, 3885 passed, 1 skipped, 370 warnings`.

All 59 failures were diagnosed and resolved without weakening any test:

- **57** were M35 tests failing only under full-suite collection order. Root cause: a
  single M35 test called `importlib.reload` on `saathi.credentials.m35`, which
  replaced the module-level `M35Error`/`SecretHandleError` classes so later
  `pytest.raises(M35Error)` assertions in other M35 files (which run alphabetically
  after `certification_and_evidence`) caught the stale pre-reload class. Fixed by
  proving import-cleanliness in a subprocess instead of an in-process reload. The
  four M35 files now pass in alphabetical order: **227 passed**.
- **2** were `test_m20_0_engineering_orchestrator::test_readiness_clean_repo` and
  `test_m20_4_engineering_control_center::test_cc_active_readonly_session`. Both
  inspect the live `git status --porcelain`; the **uncommitted** M35 files tripped
  the readiness secret-path heuristic (`saathi/credentials/m35.py` contains
  "credentials"; `docs/M35_SECRET_*.md` contain "SECRET"). Environmental — not an
  M35 code regression — and resolved once the M35 work is committed.

Confirming full run after the reload fix + commit: `3944 passed, 1 skipped, 370
warnings` (0 failed). The 370 warnings and 1 skip are pre-existing and unrelated to
M35.

## Determinism & leak scanning

- `scripts/m35_generate_evidence.py` — offline, synthetic, deterministic:
  regeneration produces byte-identical output for all 22 evidence files.
- M31 leak scanner over `docs/evidence/m35/*.json`: **0 findings**.
- No real token shapes, no absolute local paths, no raw synthetic secret value, no
  raw account subject in code, tests, docs, or evidence.

## Invariants (from `docs/evidence/m35/validation_summary.json`)

```
provider_rollout / connector_rollout / inference_rollout = OFF / OFF / OFF
canary_providers / active_providers                      = 0 / 0
external_network_calls / external_provider_writes        = 0 / 0
financial_provider_calls / trading_provider_calls        = 0 / 0
production_credentials / production_accounts_linked       = 0 / 0
real_sandbox_credentials / real_sandbox_accounts_linked   = 0 / 0
raw secrets in evidence / logs / events                   = 0 / 0 / 0
sandbox_certification                                     = SANDBOX_GOVERNANCE_VERIFIED
real_sandbox_session                                      = NOT_EXERCISED
Trading Guardian                                          = UNCHANGED / UNENGAGED
```

## Test-side-effect handling

- `docs/evidence/m25/` timestamp-only changes: runtime noise, **left unstaged**.
- `docs/evidence/m27/`: **left untouched and unstaged**.
- Only intentional M35 code, tests, docs, and deterministic M35 evidence staged.
