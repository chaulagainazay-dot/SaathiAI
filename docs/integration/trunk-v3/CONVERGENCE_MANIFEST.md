# R2 — SaathiOS Trunk Convergence Manifest

`integration/saathios-trunk-v3`

One authoritative trunk assembled from the UI/Trading, Voice, M64 and R1
recovery lines. This is a convergence record, not a feature milestone: no
AgentHarness, no new voice or trading capability, no provider activation.

---

## 1. Input heads

Every input was re-verified against `origin` before any branch was created.
All three source worktrees were clean and at their expected SHAs, and no source
branch had moved.

| Line | Branch | SHA | Role |
| --- | --- | --- | --- |
| UI-NEXT 3.1 + T-NEXT 4 | `feature/ui-next-3-1-production-motion` | `1a51ae955cb6c13394c19bb2dd9f6e3ef109854f` | convergence base |
| V-NEXT through 2B.6 | `data/v-next-2b6-product-clean-speech` | `f4dd4fbee54daa1cdbd7d28bc445592209265148` | merged |
| M64 route repair | `fix/m64-module-discovery-regression` | `8e59e2c68ce8b86533f349eb62567f827fe53762` | cherry-picked (source only) |
| R1 CORS preservation | `recovery/r1-cors-auth-preservation` | `2a2b3bbeebeff08e17c173698e6c7f921f5e1c19` | cherry-picked |
| R1 import determinism | `recovery/r1-cors-auth-preservation` | `c84912646de85328183fc23794a5beb7b83b8e6a` | cherry-picked |

**Result:** `604257e796612a3efe6a158b73fe4b9b0156146d`

### Why R1 was cherry-picked rather than merged

`recovery/r1-cors-auth-preservation` is not only the two R1 commits. It sits on
`integration/saathios-canonical-baseline-v2-voice`, which carries five commits of
the **condensed** voice implementation. Merging the branch would have imported
that condensed line alongside V-NEXT and let it contest ownership of the voice
runtime — the one substitution this convergence was explicitly not to make. The
two R1 commits were taken directly instead. Same content, no condensed voice.

---

## 2. Conflict resolutions

The V-NEXT merge produced exactly two textual conflicts. Both are recorded here
with the competing behaviours, not just the outcome. Two further decisions were
made outside the conflict markers and are recorded for the same reason.

### `saathi-os/package.json` — **COMBINE**

| Side | Behaviour |
| --- | --- |
| UI | `npm test` list including design-lab, command-read-model, command-motion suites |
| Voice | `npm test` list including the three `lib/voice-session/*` suites |

Neither list is a superset of the other; the conflict is purely that both edited
the same line. Resolved as the union — 57 suites, later 60. Choosing either side
would have silently stopped running the other line's tests, which is the failure
mode a merge conflict in a test manifest exists to prevent.

### `saathi-os/app/command/page.jsx` — **ADAPT** (keep UI structure, wire the V-NEXT contract into it)

| Side | Behaviour |
| --- | --- |
| UI | UI-NEXT-3.1 rewrote the page into the 1067-line hybrid command centre with modes, motion tokens and read models. Voice state was local: `useState("READY")`, seeded from `model.saathi.voice_session_state`. |
| Voice | V-NEXT-1 made a three-line change to the *pre-rewrite* 129-line page: subscribe to `VoiceSessionProvider` and pass `commandLabel` to `CommandComposer`. |

Not a real contest of implementations — the voice change is a small edit to a
file the other side replaced. Resolved by keeping the UI structure entirely and
carrying the V-NEXT *contract* into it:

- the page subscribes to `useVoiceSession()`;
- when the manager actually owns the mic or speaker (state is not `IDLE`/`CLOSED`)
  its state is what renders;
- the former `voice` state becomes `voiceOverride`, a presentation-only label
  used for the read-model value, demo intents and the `cycle-voice` certification
  affordance that UI-NEXT-3/3.1 browser certification depends on;
- the Listen control asks the canonical manager for input instead of only
  relabelling itself.

The conflict-policy criteria that decided it: preserve the broader certified
capability (the UI rewrite is far larger and separately certified), maintain
central command coherence, minimise duplicate state owners, and preserve one
voice session owner. Taking the voice side would have discarded UI-NEXT-3 and
3.1 wholesale. Taking the UI side unmodified would have left two voice state
owners with no connection between them.

### `saathi-os/lib/design-lab/contracts.js` + `lib/command-motion.js` — **COMBINE**

| Side | Behaviour |
| --- | --- |
| UI | 10-state presentation vocabulary, no `SPEECH_DETECTED` |
| Voice | 11-state canonical contract including `SPEECH_DETECTED` (V-NEXT-2A acoustic barge-in) |

Not a textual conflict — git merged both files cleanly — but a semantic one: a
state the session manager can enter would have rendered as `READY`, silently
hiding a certified capability. `SPEECH_DETECTED` added to the presentation
vocabulary with its own motion entry.

### M64 browser evidence in `8e59e2c` — **REJECT** (source only)

The M64 commit carried five certificate artifacts alongside its six source
files. Those were produced by a run whose frontend and backend provenance is
unrecorded, and they predate the provenance schema this convergence adds. Source
cherry-picked; evidence regenerated against the proven trunk runtime in phase 13.

### `mainSessionToken()` from the canonical-baseline harness — **REJECT**

Read `BAADAR_PASSWORD` / `BAADAR_PASSWORD_HASH` / `SAATHI_TOKEN` from `.env` and
recomputed the server's session derivation, so certification skipped the
authentication flow it claimed to exercise. Not carried forward. M64
authenticates through the real platform login endpoint.

### `verifyRuntime()` from the canonical-baseline harness — **KEEP / ADAPT**

Kept and extended. See section 5.

---

## 3. What survived

### Voice — full V-NEXT through 2B.6

326 files, ~27k lines. Every milestone's implementation, qualification assets and
documentation:

| Milestone | Present |
| --- | --- |
| V-NEXT-1 | canonical VoiceSession, single audio ownership, `lib/voice-session/*`, `VoiceSessionProvider` |
| V-NEXT-2A | energy/ZCR VAD adapter, acoustic barge-in, `SPEECH_DETECTED` |
| V-NEXT-2B | streaming STT adapter, turn coordinator, partial vs final transcripts |
| V-NEXT-2B.1 | local STT qualification matrix, qualified local adapter, resource admission |
| V-NEXT-2B.2 | Nepali-specialised ASR benchmark, deterministic domain vocabulary repair |
| V-NEXT-2B.3 | Nepali–English code-switch benchmark and gates |
| V-NEXT-2B.4 | Omnilingual ASR challenger evaluation, no-cloud fallback gates |
| V-NEXT-2B.5 | PEFT/LoRA readiness, clean data source selection |
| V-NEXT-2B.6 | consented multi-speaker recorder, speech QA and contamination validation, frozen corpus metadata, 2B.6A campaign plan |

Supporting trees intact: `tools/voice-stt-bench/` (corpus + results),
`tools/voice-stt-data/`, `tools/voice-stt-train/`, `docs/voice-next-*`.

The condensed voice implementation from the canonical-baseline line was **not**
used and does not appear in this trunk.

### UI and Trading

`integration/saathios-canonical-baseline` (`2030257`) is an ancestor of the
UI-NEXT-3.1 head, and the trunk is built on that head, so the whole UI-NEXT and
T-NEXT ladder is present by ancestry rather than by re-merge:

UI-NEXT 1 → 2 → 2.1 → 2.2 → 3 → 3.1, and T-NEXT 1 → 1.1 → 2 → 3 → 4.

---

## 4. Defects found and fixed during convergence

Three were found by convergence itself. Recording them here because a manifest
that lists only merges hides the part that mattered.

### CORS middleware ordering (phase 6, `2b0442f`)

Starlette builds its stack from the reverse of registration order, so
registering `CORSMiddleware` at import time — above the `_auth` gate defined 1700
lines later — made authentication outermost. Two consequences: preflight reached
the auth gate before CORS could answer it (hence R1's temporary `OPTIONS`
bypass), and an authentication rejection short-circuited before CORS could label
it, so a genuine 401 reached the browser with no ACAO and was reported as a CORS
failure with the real cause invisible.

CORS is now registered last and is outermost. The `OPTIONS` bypass is deleted.
The contract is pinned by tests, not by comment:

| Origin | Request | Result |
| --- | --- | --- |
| allowed | `OPTIONS` preflight | 200 + correct ACAO |
| allowed | unauthenticated GET | **401 + correct ACAO** |
| disallowed | preflight | refused, no ACAO, authentication not consulted |
| any | GET / POST / non-preflight `OPTIONS` on a protected route | 401 |

The ~70-path `_auth` allowlist is untouched. Centralising that policy is R3.

### Client navigation frozen by a voice teardown loop (phase 13, `257f0ba`)

The first M64 run failed on the converged trunk, and the failure was real: every
link and sidebar button in the shell was inert. Clicks were received, synchronous
updates still committed, direct URL loads worked, nothing was logged. Bisected by
rebuild — the pre-convergence UI-NEXT-3.1 build navigates, the trunk did not, and
removing `VoiceSessionProvider` restored it.

`publish()` allocates a new snapshot with a fresh `lastActivityAt` on every call,
so any publish is a changed value to a React subscriber. `endInput()` published
unconditionally, including with nothing held. `VoiceRuntimeProvider`'s cleanup
calls `endInput()`, and that cleanup belonged to an effect keyed on callbacks
that closed over the session context value. Cleanup published → session value
changed → callback identity changed → effect re-ran → cleanup published again. A
synchronous update loop that never let React commit a navigation transition.

Fixed twice over, either sufficient: teardown is idempotent and silent when
nothing is owned, and teardown callbacks read the session through a ref.

### Guaranteed-401 request on every signed-out page load (phase 13, `257f0ba`)

The shell TopBar called `/api/v1/connectors/approvals/pending` on mount without
checking for a session. Previously invisible: with CORS innermost the 401 arrived
unlabelled, the browser called it a CORS failure, and the M64 harness had a
bucket classifying exactly that text as expected noise. With CORS outermost the
same 401 is correctly labelled and failed `no_unexpected_console_errors`.

Fixed at the source rather than by re-tuning the harness classifier: the request
is not sent without a session. Callers already treated a rejection as
"unavailable" rather than inventing a zero, so displayed behaviour is unchanged.
The gate was not weakened.

### Runtime dirtying committed evidence (phase 10, `686e78d`)

Reproduced before the change: a governed-connector test selection left
`docs/evidence/m27/connector_events.jsonl` and
`docs/evidence/m28/deprecation_events.jsonl` modified, with no test having asked
for it. `storage/storage.db` was tracked despite `storage/*.db` being ignored —
ignore rules do not apply to already-tracked files.

`saathi/runtime_paths.py` splits the two: `docs/evidence/**` is the immutable
record written only by a deliberate certification run; live logs go to
`<repo>/.runtime/`, git-ignored and relocatable via `SAATHI_RUNTIME_STATE_DIR`.
`storage/storage.db` is untracked — the file stays on disk and in history.

No historical evidence was deleted or rewritten. M25 was deliberately left alone:
its files are written by the M25 live certification run itself, which is evidence
generation working as designed.

---

## 5. Certification harness

### `verifyRuntime()` — kept and extended

The original verified ports and the observed browser API origin. It now also
requires that both halves identify themselves, report the same commit, resolve to
the harness worktree, and match the SHA the run is meant to certify
(`SAATHI_EXPECTED_SHA`, defaulting to harness HEAD). 15 runtime gates run before
any product gate.

Origin verification changed from string comparison to identity proof. The product
default API base is `http://localhost:8765` while the harness addresses
`http://127.0.0.1:8765`; those are the same process reached through two loopback
names, and a string comparison fails a correct run. Each observed backend origin
is now asked who it is and its answer compared against the commit under test —
strictly stronger, since it also catches a second backend on the expected origin.

### Runtime provenance

| Surface | Exposes |
| --- | --- |
| `GET /api/v1/platform/provenance` | backend SHA, branch, dirty flag, repository |
| `GET /api/v1/platform/health` | the same, embedded as `provenance` |
| `GET /api/provenance` (frontend) | frontend SHA, branch, dirty flag, repository |

Worktree and package paths are exposed only outside production-class
environments; build identity is always present. Both halves resolve the
environment from `SAATHI_ENV` / `SAATHI_ENVIRONMENT` / `ENVIRONMENT`, defaulting
to development. `NODE_ENV` is deliberately not consulted — it is the build mode,
and `next start` sets it to `production` for any production build, which made the
frontend claim production while the backend beside it said development.

### Certificate provenance schema

Every newly generated certificate carries `capturedAt`, `repoSha`,
`worktreePath`, `frontendSha`, `backendSha`, plus frontend and backend origins,
observed API origins, the certification command and the harness commit. M64 moved
to `m64.browser_cert.v2`, M77 to `m77.voice_browser_cert.v2`. No historical
certificate was rewritten.

---

## 6. Results

### Tests

| Suite | Command | Result |
| --- | --- | --- |
| Bounded backend | `./.venv/bin/python -m pytest $(cat docs/integration/trunk-v3/BOUNDED_SUITE.txt) -p no:randomly` | **976 passed, 0 failed** |
| Frontend | `npm --prefix saathi-os test` | **527 passed, 0 failed** |
| Frontend lint | `npm --prefix saathi-os run lint` | 0 errors, 3 pre-existing warnings (threshold 5) |

Pre-convergence baseline for comparison: 839 backend / 432 frontend. The
backend gain is 38 R1 guard tests, 22 new CORS assertions, 27 provenance, 14
evidence hygiene and 36 architecture invariants. The frontend gain is 22
voice-session suites plus 73 added here.

### Browser certification

| Certificate | Verdict | Gates | Frontend SHA | Backend SHA |
| --- | --- | --- | --- | --- |
| M64 | **PASS** | 21 hard / 12 state / 6 responsive / 3 accessibility, + 15 runtime | `257f0ba` | `257f0ba` |
| M77 | **PASS** | 36 hard / 6 responsive / 2 accessibility / 4 security | `8b645e3` | `8b645e3` |

Both ran against a clean tree with both halves proven to be serving the same
commit from `/Users/macbookpro/SaathiAI-trunk-v3`. M64 recorded 0 page errors, 0
console errors, 0 framework overlays. No gate was reduced to obtain either pass.
M77 includes an embedded M64 shell regression run.

### Route ownership (M64 contract)

| Route | Owner |
| --- | --- |
| `/apps` | M64 Applications Dashboard, driven by `GET /api/v1/platform/modules` |
| `/app-launcher` | M121–M129 AppLauncher |
| `/applications` | redirect to `/apps` |

---

## 7. Authority invariant attestation

Machine-checked by `tests/test_r2_architecture_invariants.py` — 36 assertions,
all passing. The table is generated by running code, not by reading it.

| Invariant | Status |
| --- | --- |
| Exactly one `ExecutionGateway` | PASS |
| Execution path runs through ApprovalCenter → ExecutionGateway | PASS |
| Trading Guardian posture preserved | PASS |
| Approval required | PASS |
| Deterministic risk / default policy prohibitions intact | PASS |
| Broker connectivity authority false | PASS |
| Live trading authority false | PASS |
| Order submission capability false | PASS |
| Withdrawal authority false (simulation-only ledger event) | PASS |
| Leverage / margin / shorting / martingale false | PASS |
| Kill switch present | PASS |
| Circuit breakers present | PASS |
| Reconciliation present | PASS |
| No model, provider or plugin gains hard authority | PASS |
| Identity cannot independently grant high authority | PASS |
| Authentication not optional for protected routes | PASS |
| CORS outermost, no method bypass | PASS |
| No credentials committed, `.env` ignored | PASS |
| `saathi` resolves to this checkout | PASS |

---

## 8. Deterministic environment

`/Users/macbookpro/SaathiAI-trunk-v3/.venv`, created with
`python3.12 -m venv --system-site-packages` and `pip install --no-deps -e .`
inside it.

```
$ ./.venv/bin/python -c "import saathi, pathlib; print(pathlib.Path(saathi.__file__).resolve())"
/Users/macbookpro/SaathiAI-trunk-v3/saathi/__init__.py
```

The R1 root `conftest.py` guard refuses collection if `saathi` ever resolves
outside this checkout, so every pytest invocation in this convergence proved its
own resolution before running.

---

## 9. Remaining divergence

Nothing was deleted. Branches and worktrees carrying work not in this trunk:

| Branch | Contains | Status |
| --- | --- | --- |
| `integration/saathios-canonical-baseline-v2-voice` (`b5e8fda`) | condensed voice implementation | superseded by V-NEXT; deliberately not merged |
| `milestone/m312-m319-connectivity-governance` and the M2–M343 milestone ladder | the historical 40-PR ladder | out of scope by instruction |
| `implementation/fm-i1…fm-i6`, `hardening/fm-i6.2-*` | AgentHarness / local model harness line | future milestone |
| `evaluation/twenty-readonly-sandbox`, `audit/saathios-canonical-integration-readiness` | evaluation and audit lines | not product code |
| `/Users/macbookpro/SaathiAI` (main worktree) | dirty: uncommitted provider/inference edits, `artifacts/`, `docs/baadar/`, `docs/design-spec/` | unowned; not load-bearing to this convergence |

The main worktree's uncommitted `saathi/baadar/`-adjacent work was inspected and
is not required by anything in this trunk.

---

## 10. Resource profile

No Docker, Kubernetes, additional database, background service, build daemon or
new model runtime was introduced. The convergence ran on the existing
architecture on an 8 GB Apple Silicon host: one venv, one Next build, two
loopback processes during certification.

---

## 11. Publication and CI

| Field | Value |
| --- | --- |
| Branch | `integration/saathios-trunk-v3` |
| Final published SHA | `9e369bda036fdfc81a246c8583c263f14cfee1f7` |
| Upstream | `origin/integration/saathios-trunk-v3`, same SHA, no force push |
| Pull request | [#45](https://github.com/chaulagainazay-dot/SaathiAI/pull/45), open, not draft |
| Base | `integration/saathios-canonical-baseline` — deliberately not `master` |
| Merged | no; merge was never authorized |
| Workflow | `reliability`, run [32010707455](https://github.com/chaulagainazay-dot/SaathiAI/actions/runs/32010707455) |
| SHA tested | `9e369bd` — the same SHA as the published HEAD |
| Runner | `ubuntu-latest`, Python 3.12.13 |
| Started / completed | 2026-08-17T08:30:39Z / 2026-08-17T09:15:18Z |

| Required job | ID | Conclusion | Result |
| --- | --- | --- | --- |
| `critical-regressions` | 95329446484 | **success** | 262 blocking manifest checks passed, 0 failed; 7547 tests collected with no collection errors; 309 server routes against a floor of 290 |
| `full-suite` | 95334038526 | **success** | 7530 passed, 17 skipped, 0 failed, 23m56s |

### The first run failed, and what it found

Run `32006446275` on `4bab721` passed `critical-regressions` and failed
`full-suite` with 12 failed, 7509 passed, 17 skipped. Publication was the first
time any of this code had been executed on Linux, and it earned its keep.

**Eleven failures — `package_hash_mismatch` in `tests/test_m121_app_runtime.py`.**
`AppRuntime.validate_package` hashed a package's files in raw `os.walk` order,
which is readdir order and therefore a property of the filesystem rather than of
the package. Every built-in package has exactly two hashed files, so there were
exactly two possible hashes; the values pinned in each `app.json` matched one
order and not the other. This is recorded as **R2-D5**.

It is not a convergence regression. The canonical baseline passed the same job
on Linux, but it passed because readdir order happened to agree that day — the
gate was a coin flip on every runner, not a platform-specific failure. The walk
is now ordered by name. The pinned hashes were already the sorted-order hashes,
so no package manifest and no evidence was regenerated to make this pass.
`tests/test_package_hash_determinism.py` asserts the hash and the pinned-hash
validation both survive a reversed read order, and its final test fails rather
than passing vacuously if the built-in packages ever drop below two hashed files.

**One failure — `tests/test_m87_knowledge_grounding.py::test_no_absolute_paths_in_public`.**
The Phase 11 documentation commit put absolute host paths into
`docs/autonomous/LOOP_STATE.json`, which the public knowledge corpus serves and
that test forbids. Self-inflicted by the preceding commit, repaired in the same
program, recorded as **R2-D6**. The paths were removed from the state file. The
worktree path remains recorded in the browser certificates under
`provenance.worktreePath`, because those are evidence and were not weakened to
satisfy a test.

**The bounded local suite had never run either file.** That is the real finding:
a macOS-only gate that does not run the suites covering the surfaces you touched
cannot see this class of defect. Both files are now in
`docs/integration/trunk-v3/BOUNDED_SUITE.txt`, which with the nine new
determinism guards takes it from 976 to **1024 passed, 0 failed**.

### Linux / clean-clone differences found

- Package hash ordering (R2-D5 above) — the only genuine platform-sensitive
  defect, and it was latent rather than introduced.
- `tests/test_m17_1_live.py::test_live_browser_launch_and_close` and
  `::test_live_browser_dom_and_click` failed on the canonical baseline's Linux
  run and passed on both trunk-v3 runs. Pre-existing contention-sensitive flake,
  untouched by R2. Recorded, not claimed as a fix.

### What remains untrue

The pull request is open and must stay open. Merge to
`integration/saathios-canonical-baseline` was never authorized and was not
performed. Nothing here authorizes production, live trading, broker
connectivity, or any deployment.

### CI on the record commit

`68d5713`, the commit carrying section 11, received its own required CI as
run [32014601693](https://github.com/chaulagainazay-dot/SaathiAI/actions/runs/32014601693):
`critical-regressions` success (job 95352662425) and `full-suite` success
(job 95352661515). Both green at the final HEAD.

`full-suite` failed on its first attempt at that SHA with one failure —
`tests/test_m17_computer_agent.py::test_replay_redacts_credentials` — on a
docs-only commit, and passed on re-run. It is a pre-existing time-dependent
flake, and the diagnosis is worth stating precisely because the test name
implies a security failure and there was none.

The test asserts that the replay blob contains neither the password `hunter2`
nor the OTP `999`. Both are redacted, and always were: holding `time.time()`
fixed shows `hunter2` absent under every timestamp. But the blob also carries
two raw `time.time()` floats, and `"999" not in blob` fails whenever a
timestamp's decimal expansion happens to contain `999` — about 0.37% per
timestamp, so roughly 0.7% per run. The redaction control held; the test's
oracle is unsound.

It is not a convergence regression, R2 never touched that suite, and R2 does not
fix it — the same treatment this manifest gives the `test_m17_1_live` contention
flake. It is a real defect and belongs to whichever program owns that suite.
