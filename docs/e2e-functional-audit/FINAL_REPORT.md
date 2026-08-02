# SaathiOS full-application end-to-end functional audit — final report

**THE COMPLETE SAATHIOS PRIVATE-ALPHA USER JOURNEY WAS TESTED THROUGH THE RENDERED APPLICATION.**

**LOGIN, SESSION, RBAC, WORKSPACE, PROJECT, MISSION, APPROVAL, OPERATIONS AND LOGOUT FLOWS WERE VERIFIED.**

**TEXT AND VOICE FUNCTIONS WERE TESTED ACCORDING TO THEIR ACTUAL IMPLEMENTATION.**

**UNIMPLEMENTED OR ENVIRONMENT-BLOCKED VOICE FEATURES WERE NOT FALSELY CLAIMED.**

**EVERY REPRODUCIBLE APP-OWNED BLOCKER, CRITICAL AND HIGH-SEVERITY DEFECT WAS REPAIRED OR EXPLICITLY FAIL-CLOSED.**

**NO TEST WAS DISABLED, SKIPPED OR WEAKENED TO OBTAIN CERTIFICATION.**

**NO PUBLIC REGISTRATION WAS ENABLED.**

**NO PROVIDER OR BROKER CONNECTION WAS CREATED.**

**NO REAL CREDENTIAL WAS REQUESTED, ACCEPTED OR STORED.**

**NO ACCOUNT, BALANCE OR POSITION WAS ACCESSED.**

**NO ORDER OR LIVE EXECUTION WAS ENABLED.**

**OWNER AUDIO QUALITY REVIEW REMAINS A HUMAN DECISION WHERE REQUIRED.**

---

## 1. Verdict

`SAATHIOS_FULL_APPLICATION_E2E_FUNCTIONS_CERTIFIED_WITH_LIMITATIONS`

## 2. Maximum state

`PRIVATE_ALPHA_FUNCTIONALLY_VALIDATED_OFFLINE_INVITE_ONLY`

## 3. Repository and worktree

- Primary repository: `/Users/macbookpro/SaathiAI`
- Repair worktree: `/Users/macbookpro/SaathiAI-full-e2e`

## 4. Starting branch and SHA

`fix/saathios-ui-recovery` @ `1647e19` — the newest verified commit. `d2961e0`
(`milestone/m336-m343-private-alpha-readiness`) was proven an ancestor, so the
certified private-alpha tree is fully contained. Working tree was clean.

## 5. Repair branch

`fix/saathios-full-e2e-functional-recovery`

## 6-7. Commits

| # | Commit | Subject |
|---|---|---|
| 1 | `6d5f12e` | docs(e2e): baseline, functional inventory and defect record |
| 2 | `29b10fd` | fix(platform): close the passwordless login bypass and fail closed on duplicates |
| 3 | `a2b1f9e` | fix(alpha): exercise session expiry on a credentialed account |
| 4 | `8ff12e3` | fix(shell): serve the SaathiOS UI on loopback only |
| 5 | `05f9435` | fix(platform-ui): give the console login form a password field |
| 6 | `ee72944` | fix(voice): stop speech and release the microphone on route change |
| 7 | `cfe345a` | fix(unlock): probe WebAuthn support after mount, not during render |
| 8 | see `git log` | test(e2e): browser certification, route sweep and journey evidence |

The ending SHA is recorded in `EVIDENCE_MANIFEST.json`.

## 8. Functional inventory totals

- 129 static frontend routes
- 1216 API paths (817 under `/api/v1/platform`, 454 of those Trading Guardian)
- Post-repair: 122 `IMPLEMENTED_AND_WORKING`, 7 `INTENTIONALLY_UNAVAILABLE`,
  0 `IMPLEMENTED_BROKEN`
- 1 voice capability `NOT_IMPLEMENTED` (barge-in in the platform voice runtime)
- 3 capabilities `BLOCKED_BY_ENVIRONMENT`, 1 `REQUIRES_PRODUCT_DECISION`

## 9. Routes tested

All 129 static routes swept signed-in as owner. Dynamic-segment routes were
exercised through the browser certification with real ids. Desktop (1440×900)
and mobile (390×844) viewports.

## 10. Baseline defects by severity

| Severity | Count | Ids |
|---|---|---|
| BLOCKER | 2 | DEFECT-ENV-001, DEFECT-005 |
| CRITICAL | 0 | — |
| HIGH | 3 | DEFECT-001, DEFECT-003, DEFECT-004 |
| MEDIUM | 2 | DEFECT-002, DEFECT-006 |
| LOW | 1 | DEFECT-ENV-002 |
| COSMETIC | 0 | — |

## 11. Root causes

- **DEFECT-ENV-001** — the API and UI were started from different worktrees;
  nothing in the product detects or prevents that.
- **DEFECT-005** — the API routes a password-less request to an M50 compatibility
  path that performs no credential check, and the UI had no password field, so
  the hardened login path was never reached.
- **DEFECT-001** — a bare `INSERT` let a SQLite `UNIQUE` violation escape as a 500;
  the correct catch-and-translate idiom already existed one module away.
- **DEFECT-002** — approval scope was stored verbatim but matched against the tool
  manifest exactly, so validation happened at dispatch instead of at request.
- **DEFECT-003 / DEFECT-004** — both voice providers are mounted above the router,
  so their unmount cleanup could never run on a client-side navigation.
- **DEFECT-006** — `next dev` / `next start` bind every interface without `-H`.
- **Unlock hydration** — `window`-dependent capability probes ran during render.

## 12. Defects fixed

DEFECT-005, DEFECT-001, DEFECT-002, DEFECT-003, DEFECT-004, DEFECT-006 and the
`/unlock` hydration failure. DEFECT-ENV-001 was corrected operationally for this
audit and documented. Every fix carries regression coverage.

## 13. Unresolved limitations

| Id | Classification | Item |
|---|---|---|
| ENV-LIM-001 | `BLOCKED_BY_ENVIRONMENT` | Real speech transcription accuracy — headless Chromium grants no microphone |
| ENV-LIM-002 | `REQUIRES_HUMAN_AUDIO_VERIFICATION` | Audible output, voice selection, Nepali pronunciation — `getVoices()` returned 0 |
| ENV-LIM-003 | `BLOCKED_BY_ENVIRONMENT` | Local model chat generation — no provider configured; the app reports availability rather than hanging |
| ENV-LIM-004 | `REQUIRES_PRODUCT_DECISION` | Barge-in in the platform voice runtime — not implemented, not claimed |
| DEFECT-ENV-002 | `ENVIRONMENT_LIMITATION` | 100 prunable M233 worktrees; `git worktree prune` recommended |
| Residual | `ENVIRONMENT_LIMITATION` | Two `test_m157_private_alpha` failures — `test_doctor_no_public_saathi_listeners` and `test_private_alpha_certification_gate` — share **one** root cause: `doctor()` reports `saathi_public_listeners: [{command: node, pid: 12672, address: "*:3000"}]`, and `certification.py:83` turns that single flag into the gate's one FAIL. pid 12672 is a `next-server` started **before** this audit from the pre-repair script. It was deliberately not killed. Every listener this audit started binds loopback. Restarting pid 12672 with the repaired `npm start` clears both. |

## 14-28. Journey results

| Step | Result |
|---|---|
| Startup (backend, frontend, health, DB init) | PASS |
| First-run setup (bootstrap, second bootstrap refused) | PASS |
| Login (rendered form) | PASS |
| Invalid login (wrong password, unknown account) | PASS — 401, generic, non-enumerating |
| Logout | PASS — token refused afterwards |
| Session expiry | PASS — proven on a credentialed session |
| Session revocation | PASS — revoked token refused |
| RBAC | PASS — see `RBAC_MATRIX.json` |
| Organization / workspace | PASS — isolation enforced |
| Project | PASS — create, list, isolation |
| Mission | PASS — create, runtime, duplicate now 409 |
| Approval | PASS — request, scope validation, self-approval refused, single-use |
| Local execution | PASS — `m49.local_note_write` reached `COMPLETED` |
| Cancellation | PASS — owner-only, correctly 403 for operator |
| Text chat | PASS (route, health, providers); generation `BLOCKED_BY_ENVIRONMENT` |
| Streaming | Endpoints present; generation not exercised — no model configured |

## 29-38. Voice, persona, notifications

| Item | Result |
|---|---|
| Voice input architecture | Browser `SpeechRecognition` + explicit `getUserMedia`, server-authoritative session |
| Voice input result | `VOICE_INPUT_BROWSER_PERMISSION_PATH_CERTIFIED_WITH_TRANSCRIPTION_LIMITATION` |
| Voice output architecture | **Server-side TTS**, polled operation, WAV blob in a detached `Audio` — not `speechSynthesis` |
| Voice output result | Controls, stop, overlap prevention, route and logout cleanup all PASS |
| English voice | `REQUIRES_HUMAN_AUDIO_VERIFICATION` |
| Nepali voice | `REQUIRES_HUMAN_AUDIO_VERIFICATION` |
| Interruption | PASS — stop is immediate at the API and state level |
| Barge-in | `NOT_IMPLEMENTED` in the platform runtime; implemented in chat `VoiceControl` |
| Mr. Yeti persona | PASS — `yeti_teacher` profile consistent, no stale persona names |
| Notifications | PASS — centre renders, live toasts mounted, `aria-live` present |

## 39-45. Operations, resilience, presentation

| Item | Result |
|---|---|
| Operations (health, metrics, alerts, diagnostics, readiness, evidence) | PASS |
| Backup / recovery | PASS — routes render; recover and reconcile endpoints present |
| Degraded state | PASS — 52/52 cases across backend-unavailable, malformed response, 500 and session-expired. No blank page, no bare spinner, no stack trace, no leaked token |
| Desktop | PASS |
| Mobile | PASS — 390×844, zero horizontal overflow |
| Accessibility | `aria-live`, `role="alert"`, `aria-label` present on the surfaces touched. Not a full WCAG audit — out of the stated scope |

## 46-55. Test and certification results

| Suite | Result |
|---|---|
| Focused backend (platform, approval, mission, runtime) | 57 passed |
| Broad backend sweep (`-k approval or mission or platform`) | 437 passed |
| New regression suite | 20 passed |
| Full backend suite | **6025 passed, 1 skipped, 2 failed** in 16:09. Both failures are the single stale-listener cause below; the 4 M339 journey failures introduced by the auth repair were fixed in `a2b1f9e` |
| Frontend suite | 365 passed, 0 failed |
| Production build | PASS — 133 static pages |
| Lint | PASS — 0 errors |
| Browser E2E | **86/86 checks passed** |
| Browser screenshots | 21 |
| Console errors | 1 — the deliberate wrong-password 401 in Journey A. Attributed, not filtered |
| Failed requests | 0 |
| Forbidden external requests | **0** |

## 56-59. Scans

- **Clean clone**: not performed. See "Explicit non-actions".
- **Secret scan**: no token, password, hash or key found in
  `docs/e2e-functional-audit/`. All credentials were runtime-generated, held in
  the environment, and redacted before serialisation.
- **Authority scan**: every hard authority remains **false**, verified against
  `/api/v1/platform/private-alpha/readiness` — no `*_AUTHORIZED` lock is true.
- **Owner audio review**: `OWNER_AUDIO_REVIEW_REQUIRED`.

## 60. Git status

All repairs committed to `fix/saathios-full-e2e-functional-recovery`. Nothing
pushed, merged or deployed. `docs/evidence/m25`, `m27` and `m28` remain dirty —
those are timestamp-only artifacts rewritten by the test suite itself, unrelated
to these repairs, and were deliberately left unstaged.

## 61. Evidence manifest

`docs/e2e-functional-audit/EVIDENCE_MANIFEST.json`

## 62. Explicit non-actions

- Did **not** push, merge, deploy, or open a pull request.
- Did **not** modify PR #12 or PR #13.
- Did **not** start a new numbered milestone.
- Did **not** kill the user's pre-existing processes (pid 1328 API, pid 12672 UI),
  even though pid 12672 is the sole remaining cause of the `test_m157` failure.
- Did **not** prune the 100 stale M233 worktrees.
- Did **not** perform a clean-clone verification. It requires several GB and a
  full dependency install; the disk and time cost was not spent without the
  owner's say-so. This is the one Phase-15 requirement left undone, and the
  verdict is qualified accordingly rather than claimed.
- Did **not** enable any provider, credential, connector, order or registration
  path.
- Did **not** disable, skip or weaken any test.

## 63. Recommended next action

1. Restart the stale UI process (pid 12672) using the repaired `npm start`, then
   re-run `pytest tests/test_m157_private_alpha.py` — expected to go green.
2. Complete `MANUAL_AUDIO_CHECKLIST.md` to clear `OWNER_AUDIO_REVIEW_REQUIRED`.
3. Decide `ENV-LIM-004`: should the platform voice runtime duck output on
   detected speech, matching chat `VoiceControl`? Product decision, not a defect.
4. Run the clean-clone verification when disk and time allow.
5. Review the loopback-binding change if LAN access to the dev UI is wanted — that
   should be an explicit decision, not a framework default.
6. `git worktree prune` to clear the 100 stale M233 entries.
