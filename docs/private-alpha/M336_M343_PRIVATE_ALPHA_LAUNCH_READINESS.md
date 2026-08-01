# M336–M343 — Baseline Regression Debt Closure and Private-Alpha Launch Readiness

**Branch** `milestone/m336-m343-private-alpha-readiness`
**Predecessor** `milestone/m328-m335-production-readiness` @
`6cdf72661834242eb4901f7eaf44a4425957db37`
**Verdict** `PRIVATE_ALPHA_LAUNCH_READINESS_CERTIFIED_WITH_LIMITATIONS`
**Maximum state** `PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY`

This milestone closes the eight inherited backend failures SaathiOS had been
carrying, and establishes that the system is ready for a bounded, local,
invite-only private alpha. It does **not** authorize public production
deployment.

---

## 1. What the inherited failures actually were

M328–M335 recorded eight full-suite failures and proved they predated that
milestone. That is where the previous milestone correctly stopped. M336 started
by refusing to accept "pre-existing" as an explanation, and root-caused all
eight before changing a line of code.

They reduced to **two** causes.

### RC-A — installation outputs treated as installation prerequisites (7 failures)

Both `bin/saathi-local` and `private_alpha.prepare()` classified the
repository-root build artifacts `.venv` and `saathi-os/node_modules` as required
prerequisites whose absence was a hard FAIL. Those are *outputs* of installation,
not preconditions of it.

The consequence was not cosmetic. On any checkout where installation had not
already been performed in place — a fresh clone, a git worktree, a clean-clone
certification, or **a newly invited private-alpha tester's machine** —
`prepare()` could never return `ok`, so `init_first_run()` returned
`PREPARE_FAILED`, `apply_local_upgrade()` returned `PREFLIGHT_FAILED`, and the
M165 certification gate reported a permanent FAIL. The first command a new tester
runs could not succeed.

In the launcher the same mistake had a second effect: because `_check_env` ran
before the readiness decision layer, an operator whose real problem was an
unhealthy or unrelated listener on port 8765 was told the venv was missing. The
PID-safety refusal — the launcher's strongest guarantee, that it never kills a
process it does not own — was unreachable and unprintable.

Proof of the cause: symlinking the two artifacts into the worktree turned
`8 failed / 47 passed` into `1 failed / 54 passed`.

### RC-B — the release gate blocking on its own safety machinery (1 failure)

`saathi/ops/release_gate.py` counted any `private_key_block` scanner hit as a
strong credential leak. That rule matches the PEM *header* alone, with no key
body. Two security-control modules embed that header deliberately: a rejection
sample proving the payload sanitiser refuses private keys, and a detector's own
pattern definition. The gate's only exclusion was a `tests/` and `docs/` path
prefix, which does not cover security-control source.

`git log -S'BEGIN RSA PRIVATE KEY' -- saathi/` pins the first failing ancestor to
`79d3c29` (M224–M231). The gate had been red since 2026-07-30 — long enough that
a red security gate had become background noise, which is the worst state a
security gate can be in.

Full analysis: [`M336_REGRESSION_INTENT_RECONSTRUCTION.json`](m336_m343_evidence/M336_REGRESSION_INTENT_RECONSTRUCTION.json).

## 2. How they were closed

All three repairs are implementation-side. **The three test files containing the
eight failures are byte-identical to the predecessor commit**, verified by
`git hash-object`. No test was modified, skipped, xfailed, deleted or weakened.

| Fix | Change |
| --- | --- |
| FIX-1 `bin/saathi-local` | `_check_env` split into scoped predicates. The venv is required only on the branch that spawns uvicorn; `node_modules` only on the branch that spawns `npm run dev`. Both spawn paths still abort non-zero with identical remediation text. The unrelated-occupant refusal is now reported as itself. |
| FIX-2 `private_alpha/prepare.py` (+ upgrade, certification) | `INSTALLABLE_CHECKS` routes the two artifact checks into a new `install_complete` field instead of clearing `ok`. Both still run, still report FAIL, still emit full remediation. The M165 gate gained an explicit `installation_complete` check so an incomplete install stays visible. |
| FIX-3 `saathi/ops/release_gate.py` | `pem_carries_key_material()` requires a base64 body of ≥100 characters after the header — the same materiality standard `integration_assurance/security.py` already used. Non-material markers are reported under `non_material_markers`, not silently dropped. No file was allowlisted and the path exclusions were **not** widened. |

18 focused regression tests guard the repairs, including one that injects a
genuine PEM key body and asserts the gate still returns `EXIT_SECURITY`, and one
that asserts the original path-exclusion expression is still present.

Detail: [`M337_REGRESSION_DEBT_CLOSURE.json`](m336_m343_evidence/M337_REGRESSION_DEBT_CLOSURE.json).

## 3. Two further defects found along the way

Neither was in the original eight. Both were found by building the certification
rather than by reading the code.

**The release SHA was recorded twice.** `_git_sha(full=True)` expanded to
`["git", "rev-parse", "HEAD", "HEAD"]`, so every release manifest, certification
report and evidence file recorded `<sha>\n<sha>`. The release and rollback
runbooks both key off the approved SHA, so this had to be exact.

**Concurrent approval decisions could all win.** The M341 soak ran four
`decide_approval` calls against one approval and all four succeeded.
`decide_approval` read the record, checked `status == pending`, then wrote — a
textbook read-check-write race. One approval could record several decisions, and
a later approve could overwrite an earlier reject. Fixed with a conditional
`UPDATE ... WHERE status='pending'` under the runtime lock, matching the
guarantee `consume_approval_if_approved()` already provided for dispatch.
Verified across five trials of six concurrent deciders: one decided, five
refused, every time.

This is the clearest argument for running the soak rather than asserting it: the
sequential test passed, and had always passed. Only contention exposed it.

## 4. The private-alpha contract

[`PRIVATE_ALPHA_SCOPE.md`](PRIVATE_ALPHA_SCOPE.md) and
[`M338_PRIVATE_ALPHA_CONTRACT.json`](m336_m343_evidence/M338_PRIVATE_ALPHA_CONTRACT.json)
define exactly who may use the alpha (owner, approved internal operators,
specifically invited testers — nobody else), what environment it runs in
(single host, localhost only), the eighteen-step supported journey, and what is
explicitly unsupported.

Fifteen authority locks are `false` and are asserted by the backend suite, the
browser certification and the readiness checklist.

## 5. The certified journey

`saathi/platform/private_alpha/journey.py` runs the whole contract in one
deterministic pass — 70 steps across seven stages — composing `PlatformService`,
`PlatformAgentRuntime` and the M328–M335 `OperationsService` rather than
reimplementing any of them.

31 positive steps, 18 refusals, 21 assertions and observations.

The refusals are the point. A journey that only walks the happy path proves
nothing about a fail-closed system, so each refusal is asserted to return its own
specific code:

```
ANONYMOUS_PROHIBITED   SESSION_INVALID         AUTH_FAILED
INVITE_NOT_PENDING     PERMISSION_DENIED       PROJECT_ISOLATION
WORKSPACE_ISOLATION    MEMBERSHIP_REVOKED      APPROVAL_REVOKED
APPROVAL_EXPIRED       APPROVAL_TOOL_MISMATCH  APPROVAL_REQUIRED
```

A test asserts no refusal is a `TypeError` or `AttributeError` — a call that
fails on its own signature proves nothing about the boundary it claims to test.
That check caught two isolation probes doing exactly that, and both were
rewritten to use the real `select_workspace` API against a genuine second
organization.

Evidence: [`M339_PRIVATE_ALPHA_E2E_JOURNEY.json`](m336_m343_evidence/M339_PRIVATE_ALPHA_E2E_JOURNEY.json).

## 6. Language that was not true

The global status bar read **"Live connected"** on every authenticated screen. It
reflected only the local Server-Sent-Events stream from the local backend. On a
product that deliberately has no broker connectivity, no market access and no
execution authority, that wording claimed something untrue. It now reads
**"Local platform online"**, with a "Private alpha · local only" badge beside it.

The remaining `LIVE` strings in the UI were audited and left alone: every one is
an explicit negation (`NO LIVE ORDERS`, `LIVE TRADING NOT AUTHORIZED`). Changing
them would weaken the disclosure.

Detail: [`M340_PRIVATE_ALPHA_UX_READINESS.json`](m336_m343_evidence/M340_PRIVATE_ALPHA_UX_READINESS.json).

## 7. Reliability

`scripts/m341_private_alpha_soak.py` sustains a bounded local workload with
concurrent sessions, tenants and missions, sampling memory, CPU, file
descriptors, database and log growth, latency and error rate throughout, then
runs four concurrency scenarios and eight recovery scenarios.

It reports the duration it actually sustained and never claims one it did not.

Evidence: [`M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json`](m336_m343_evidence/M341_SOAK_CONCURRENCY_RECOVERY_REPORT.json).

## 8. Operational readiness

Four runbooks, written to be usable under pressure rather than to be complete:

- [Release](PRIVATE_ALPHA_RELEASE_RUNBOOK.md) — prerequisites through
  post-release monitoring, with the owner-review gate at step 11 and tester
  invitations only after it.
- [Rollback](PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md) — non-negotiable triggers, both
  SHAs recorded before anything is touched, a verified backup before the rollback
  itself, and an explicit rollback-versus-forward-fix decision.
- [Incident](PRIVATE_ALPHA_INCIDENT_RUNBOOK.md) — fourteen scenarios, each with
  what *not* to do under pressure: no widening CORS to fix a UI outage, no
  backfilling invented audit entries, no restarting with approvals bypassed
  "temporarily".
- [Tester guide](PRIVATE_ALPHA_TESTER_GUIDE.md) — what the alpha will not do,
  stated bluntly because some of it looks like a bug; the
  never-enter-a-real-credential rule; and redaction the support bundle cannot do
  for them.

## 9. Launch readiness surface

`/operations/private-alpha-readiness` renders the readiness overview, regression
debt, user journey, reliability, security, release package, the launch checklist
and the known limitations.

It is read-only. It has no input, form, textarea, or launch/deploy/publish/invite
/approve control, and the API behind it exposes only GET routes — both asserted
by test.

`OWNER_REVIEW_REQUIRED`, `PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC` and
`PUBLIC_PRODUCTION_NOT_AUTHORIZED` are always visible. Owner approval is
hard-coded to `OWNER_REVIEW_REQUIRED`; there is no code path that sets it to
anything else.

## 10. Limitations

- Private-alpha readiness does **not** authorize public production deployment.
- Certified on macOS arm64 only, on a single 8 GB reference machine.
- The accessibility result is a structural audit of the surfaces this milestone
  changed, not a WCAG conformance claim. No automated scanner or screen-reader
  session was run; the repository has no such harness.
- The soak is bounded by what the reference machine can sustain, not by a
  production traffic model.
- Mission, approval and execution steps in the browser certification are driven
  through the local platform API and then verified in the rendered UI, because
  the private-alpha UI has no separate mutation surface for them.
- Forbidden-control checks assert absence across the certified routes; they
  cannot prove absence on routes outside the private-alpha journey.
- Owner review has **not** been performed. No automation may perform it.

## 11. What was not done

No public deployment. No DNS change. No push. No merge. No provider or broker
connection. No credential requested, accepted or stored. No account, balance or
position accessed. No order submitted, modified or cancelled. No paper or live
execution enabled. Public registration was not enabled. M344 was not started.
