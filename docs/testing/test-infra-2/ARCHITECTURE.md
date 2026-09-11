# TEST-INFRA-2 — Test State Isolation and CI

## Problem

TEST-INFRA-1 fixed one unprotected home-directory store (`SecurityStore`) that
both deadlocked the suite and wrote into the operator's live security database.
The obvious follow-up question — *how many more are there?* — turned out to have
an uncomfortable answer.

## Audit findings

| Finding | Measurement |
|---|---|
| Source files persisting state under `Path.home()` | **44** |
| Distinct `~/.saathi` databases / JSON stores / logs | **~30** — accounts, missions (7 stores), evidence, events, knowledge library, production automation, ai_lab, client_projects, content_memory, studio_runs, reading_queue, recommendations, provider_credits, security, … |
| Of those 44, how many had an environment override | **0** |
| Trading-plane stores | already protected (`SAATHI_PLATFORM_DB`, `SAATHI_PAPER_DB`, `SAATHI_MARKETDATA_DB`, `SAATHI_STRATEGY_DB`, `SAATHI_RESEARCH_DB`, `SAATHI_PAPER_GOV_DB`) |
| Non-trading plane | unprotected |

Separately: a test run left the working tree dirty with no source change, because
evidence writers persist under the committed `docs/evidence/**` tree.

## Approach — one lever, not 44 patches

`Path.home()` and `os.path.expanduser("~")` both resolve `$HOME` on POSIX. The
root `conftest.py` is imported before any `saathi` module, and therefore before
any module-level `Path.home()` constant is evaluated.

Setting `HOME` (and `USERPROFILE`) to a session temp directory in the root
conftest isolates **all 44 files at once**, without editing any of them.

Patching 44 call sites would have been 44 chances to introduce a defect, and
would still have missed the 45th.

Opt-out: `SAATHI_TEST_REAL_HOME=1`.

## Evidence writers

Five modules wrote into the committed evidence tree:

| Module | Path |
|---|---|
| `saathi/inference/cert_evidence.py` | `docs/evidence/m25/cert/` |
| `saathi/inference/live_cert_m25.py` | `docs/evidence/m25/` |
| `saathi/inference/runtime_gate.py` | `docs/evidence/m25/LIVE_CERT_EVIDENCE.json` |
| `saathi/inference/ops/service.py` | `docs/evidence/m25/` pointers |
| `saathi/inference/ops/state.py` | `docs/evidence/m26/` — **found by fresh-context review, not by me** |

All now honour `SAATHI_EVIDENCE_ROOT`, redirecting the evidence **output root
only**.

### A mistake worth recording

The first attempt redirected each module's `ROOT` constant. That broke
`test_ops::test_release_gate_passes_baseline` (exit 8), because `ROOT` in those
modules is the *repository* root — used for subprocess `cwd`, source scanning,
manifest lookup, and `relative_to()`, not only for evidence.

The fix was to keep `ROOT` as the repository root and introduce a separate
`EVIDENCE_ROOT`. The conftest additionally **seeds** the isolated evidence root
by copying the committed tree (6.9 MB, 398 files), because gates *read* those
artifacts — isolation had to copy, not start blank.

## Known overlap — recorded, not hidden

`saathi/runtime_paths.py` already exists and already describes this exact
problem, in almost these words: *"ordinary operation — including importing a
module during a test run — permanently modified checked-in evidence… a working
tree that goes dirty by itself."* It provides `SAATHI_RUNTIME_STATE_DIR`,
`runtime_state_dir()`, and `runtime_evidence_dir(milestone)`.

`SAATHI_EVIDENCE_ROOT` is therefore a **second mechanism for an adjacent
problem**, which the program's core standard warns against.

It was kept for this milestone because the two are not interchangeable:
`runtime_paths` moves runtime logs *out* of the committed tree, whereas the m25
artifacts are read back by the release gate as committed evidence — redirecting
them to a runtime directory breaks the read side, which is exactly the failure
observed above. Converging them means changing certification semantics, which is
a larger change than test isolation and does not belong in this milestone.

Recorded as the top item in `LIMITATIONS.md` and as infra debt on the roadmap.

## CI

`.github/workflows/offline-core.yml` — two jobs:

- **offline-suite**: compileall syntax gate → offline regression by marker → a
  step that **fails the build if the test run mutated tracked files**. That last
  step is what stops this class of defect from returning.
- **trading-regression**: the execution-integrity, reconciliation-gate, ledger,
  construction, risk, guardian, and gateway suites.

Neither job has, or needs, a browser, an API key, a broker, or a provider
credential.
