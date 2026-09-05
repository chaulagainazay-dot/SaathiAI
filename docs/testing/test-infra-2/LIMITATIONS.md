# Limitations

## Two mechanisms now exist for one problem — recorded, not hidden

`saathi/runtime_paths.py` already existed and already described this exact
problem: *"ordinary operation — including importing a module during a test run —
permanently modified checked-in evidence… a working tree that goes dirty by
itself."* It offers `SAATHI_RUNTIME_STATE_DIR`, `runtime_state_dir()`, and
`runtime_evidence_dir(milestone)`.

`SAATHI_EVIDENCE_ROOT`, added here, is a **second mechanism for an adjacent
problem**, which the program's core standard warns against.

Why it was still added: the two are not interchangeable. `runtime_paths` moves
runtime logs *out* of the committed tree. The m25/m26 artifacts are **read back**
by the release gate as committed evidence — redirecting them to a runtime
directory breaks the read side, which is exactly the failure observed when the
first attempt did so (`test_release_gate_passes_baseline`, exit 8). Converging
them means changing certification semantics, which is a larger change than test
isolation and does not belong in this milestone.

**This is the top infra debt item.** The correct end state is that m25/m26
runtime observations move to `runtime_evidence_dir()` and only deliberate
certification runs write `docs/evidence/**` — after which `SAATHI_EVIDENCE_ROOT`
can be deleted.

## HOME redirect is broad by design

Setting `HOME` isolates all 44 offending files at once instead of patching 44
call sites. The trade-off: it also redirects home for code that legitimately
wants the real home. One such case surfaced immediately and was fixed
(`config_protection._home()`); others may exist in paths no test exercises.

Escape hatch: `SAATHI_TEST_REAL_HOME=1`.

## The 44 files still have no override of their own

The HOME redirect protects the *test session*. It does not give
`accounts.db`, `missions.db`, `ai_lab.db`, `content_memory.db` and the other ~26
stores an explicit `SAATHI_*_DB` override the way the trading-plane stores have.
A deployment wanting to relocate them still cannot. Not required for test
isolation; worth doing when those subsystems are next touched.

## CI is written but unverified

`.github/workflows/offline-core.yml` has never executed — there is no CI history
on this repository. The YAML parses and the commands match what was run locally,
but "green in CI" is not claimed.

## Suite economics untouched

Runtime is unchanged at ~10-11 minutes. The 15 slowest tests were identified
(18.3 s worst, fifteen over 7 s) but none were optimised — the milestone's
isolation work expanded once the 44-file audit and two production defects
surfaced. `pytest-xdist` remains unevaluated, which is correct: the brief says
not to parallelise until shared state is proven isolated, and while HOME and
evidence are now isolated, the per-store overrides are not.

## Scope note

This milestone changed **production** code in six files. Five are audit/evidence
plumbing. The sixth, `saathi/agentdev/config_protection.py`, is a security fix —
see `SECURITY.md`. None is in the trading plane.
