# M17.8 Validation — Governed Long-Running Harness Task Control

Closes the top "Real debt (actionable without approval)" item in TECHNICAL_DEBT
("Long-running harness task control … designed but not built; limits.py caps
resources only") and the recurring verdict gap "long-session/runaway unproven".
No new execution engine: every task still runs through the ONE
`ApplicationHarnessAdapter` boundary — M17.8 only adds control + durability around
it.

## What was built
- `run_journal.py` — append-only, fsync'd JSONL run journal. A "running" record is
  written BEFORE the adapter blocks; a terminal record (success/failed/timeout/
  cancelled) on completion. `reconcile()` finds "running" records whose PID is no
  longer alive and appends a `crash_recovered` terminal record — interrupted runs
  become explicit incident evidence instead of dangling unknown state.
- `task_control.py` — `HarnessTaskController` + `CancelToken`. Launches a run on a
  daemon thread through the adapter, tracks it by id, and supports `cancel(run_id,
  requester=…)`. Ownership is enforced BEFORE spawn and on cancel — no cross-user
  launch or task hijack.
- `adapter.py` — additive, default-off params `cancel_token`, `run_id`, `journal`.
  A watcher thread SIGKILLs the process group the moment the token is set;
  start/terminal records are journaled on every exit path. With none supplied the
  adapter is byte-identical to pre-M17.8 (regression test asserts this).

## LIVE validation (real processes, real signals)
- **Cancellation:** a real `/bin/sleep 30` is launched, confirmed running (journal
  active + PID alive), then cancelled → result `cancelled`, journal `cancelled`,
  and the PID is gone — orphan-free process-group kill.
- **Timeout kill:** a real hung `/bin/sleep 30` with `timeout=0.5` → `timeout`,
  process-group killed, journal `timeout`.
- **Resource-limit enforcement (first live proof):** `dd` writing 20 MB under
  `RLIMIT_FSIZE = 1 MB` is killed by the OS (SIGXFSZ; exit 153) with the output
  file capped at exactly 1 048 576 bytes → `failed`. The setrlimit hook in
  `limits.py` was previously only asserted `callable`; it is now proven to actually
  stop a runaway writer.
- **Crash reconciliation:** a "running" record for a dead PID is reconciled to
  `crash_recovered`; a live-PID run is left untouched.
- **Ownership:** cross-user launch → `blocked` (never spawned); cross-user cancel →
  refused.

## Security / red-team
- New surface = task cancellation. Cross-user launch and cross-user cancel are both
  denied (ownership gate above the adapter). Cancellation reuses the existing
  SIGKILL-to-process-group path (same as timeout). Journal stores only
  pid/pgid/harness_id/owner/state/timestamp — no command output, args, or secrets.
- Adapter trust/argv/root-confinement gates unchanged; default-off params keep the
  hardened path intact (backward-compat test).

## Tests
`tests/test_m17_8_task_control.py` (8): live cancel orphan-free; live timeout;
live FSIZE runaway stopped; crash reconcile (dead vs alive); cross-user launch +
cancel blocked; success journaled; adapter default-off unchanged; cancel-token
semantics.

## Executed evidence (2026-07-12, `.venv` Python, macOS/darwin, POSIX)
Commands run and results:
- `pytest -q tests/test_m17_8_task_control.py tests/test_m17_4_multiapp.py` →
  **20 passed** (M17.8 file = 8 tests, all run, 0 skipped on POSIX).
- `pytest -q tests -k "application_harness or task_control or run_journal or
  resource_limit or trust or artifact or security"` → **140 passed**.
- Red-team: `pytest -q tests/test_m15_2_security.py tests/test_m15_2_harness.py`
  → **108 passed**.
- `python -m json.tool saathi/repair/critical_checks.json` → valid JSON. No
  M17.8-specific critical entry exists yet; applicable critical targets are the
  `application_harness` + `security` subsystems, covered green by the runs above.
- Server import + route count → **308 routes** (CI gate ≥ 290).
- `git diff --check` → clean (no whitespace/conflict markers).
- Secret scan (regex over all M17.8 files) → **no matches**.
- Full suite: `pytest -q tests` → **1509 passed, 1 skipped, 0 failed** (exit 0,
  395s). The single skip is a pre-existing environmental skip, not M17.8 (the
  8 M17.8 tests run with 0 skips on POSIX).

Live evidence (directly reproduced, not carried over):
- **Cooperative cancellation:** `test_live_cancel_kills_process_orphan_free` —
  real `/bin/sleep 30` launched, confirmed alive via journal+PID, cancelled →
  result `cancelled`, journal `cancelled`, PID gone (orphan-free). PASS.
- **Forced termination:** `test_live_timeout_kills_and_journals` — real hung
  `/bin/sleep 30`, `timeout=0.5` → `timeout`, group killed, journal `timeout`.
  PASS. Cancellation path uses the same bounded SIGKILL-to-process-group.
- **Child-process cleanup:** process group started with `start_new_session=True`;
  post-cancel PID confirmed dead in the live test. No leaked `sleep`/`harness`
  processes after the run (`pgrep` clean).
- **Crash recovery / journal recovery:**
  `test_reconcile_marks_dead_running_as_crash_recovered` — dead-PID `running`
  record → `crash_recovered`; live-PID run left `running`. PASS.
- **Resource-limit enforcement (direct live run):** `dd` writing 20 MB under
  `RLIMIT_FSIZE=1 MB` → `status=failed`, **exit_code=153 (SIGXFSZ)**, output file
  capped at **exactly 1 048 576 bytes**. First live proof the setrlimit hook stops
  a runaway writer.

Housekeeping: default journal store `data/application_harness_runs/` never
created (all tests use `tmp_path`); no leftover temp journals; only intended
M17.8 files untracked; `saathi/memory/conventions.md` (unrelated auto-learned
memory) deliberately excluded from the commit.

## Final maturity classification
`live-proven` — real cancel, real SIGXFSZ resource kill, and real crash
reconciliation all pass on live processes through the single adapter boundary.

## Known limitations
- pause/resume/checkpoint not built (deferred, larger scope).
- No production metrics/alerting dashboard for long runs yet.
- Multi-user concurrency proven only by cross-user gate tests, not at scale.
- Journal is single-process append-only (lock-serialized); not a multi-writer DB.

Verdict: HARNESS EXECUTION now has GOVERNED LONG-RUNNING TASK CONTROL — cancel,
orphan-free timeout kill, live-enforced resource limits, and durable run records
with crash reconciliation, all through the single adapter boundary. Advances
long-session stability / crash-recovery from "designed" to "live-proven". Not yet:
pause/resume/checkpoint (deferred), production metrics dashboard, multi-user
concurrency at scale.
