# SaathiOS Private Alpha Product Excellence — Final Report

**Terminal verdict:** `REAL_USER_VALIDATION_PENDING`
**Maximum state reached:** `PRIVATE_ALPHA_READY_FOR_OWNER_OPERATION_OFFLINE_INVITE_ONLY`
**Target state NOT reached:** `PRIVATE_ALPHA_STABLE_FOR_BOUNDED_REAL_USER_VALIDATION`

---

## Why the preferred verdict was not awarded

Two gates were closed before work began, and neither can be opened by automation.

**1. No real invited user exists.** The mission requires a completed owner session, operator
session, viewer session and three full scripted journeys. It also states plainly that Claude must
not impersonate users or invent feedback. Zero sessions have run. The mission's own fallback
verdict for this condition is `REAL_USER_VALIDATION_PENDING`.

**2. Automation cannot authenticate.** All three platform accounts (`owner@e2e.local`,
`operator@e2e.local`, `viewer@e2e.local`) hold password hashes. Entering the owner's password is
prohibited, and "Bootstrap + login" — the only sign-in control on the unauthenticated surface —
would create a new user and organization in the certified database. Every authenticated journey
therefore remains unexercised: workspace, projects, missions, approvals, assistant, authenticated
voice, operations.

Certifying product excellence on a product nobody has used would be exactly the fabrication the
mission forbids.

## What was genuinely established

| Gate | Result |
|---|---|
| Frontend focused tests | **20/20 pass** |
| Frontend full suite | **382 pass, 0 fail**, 71 suites |
| Lint | **pass** |
| Production build | **pass**, 145 routes, 102 kB shared first load |
| Backend full suite | **inconclusive — hang, see below** |
| Network scan | **pass** — all SaathiOS listeners loopback-only |
| Secret scan | **pass** |
| Authority scan | **pass** — all hard authorities false |

Measured performance, all far inside budget: API 2–9 ms average, frontend TTFB 9–13 ms,
2.5 MB static JS across 174 files, 102 kB shared first load.

Accessibility on the reachable surface: zero unlabeled auth fields, zero unnamed buttons, correct
heading order, 4 nav + 1 main landmark, live regions present, no keyboard trap, no positive
tabindex, reduced-motion honoured, and a real 2 px keyboard focus ring.

## Findings

**No open P0. No open P1.** One P1 was found and fixed earlier in this branch (`PA-D-001`,
expired-session dead-end). Six P2 and one P3 remain open — full detail in `DEFECT_LOG.json` and
`PRIVATE_ALPHA_KNOWN_ISSUES.md`.

Two findings deserve the owner's direct attention:

- **`PA-D-002`** — rebuilding `.next` under a running `next start` leaves the server serving chunk
  hashes that no longer exist. The app is completely broken while still returning HTTP 200. This
  bit twice in one session and is the single most likely way to hand a tester a dead build.
- **`PA-D-006`** — every SaathiOS listener is correctly loopback-only, but third-party `ollama`
  binds `*:11434`. On an untrusted network that is real exposure beside a local-first product.
  Fix is outside this repository: `OLLAMA_HOST=127.0.0.1`.

## Two premises in the brief that measurement contradicted

**Database growth is not substantial.** The brief states a prior soak showed substantial growth.
Measured: `platform.db` is 1.17 MB holding **642 rows**; total `data/` is 7.3 MB; there is no logs
directory. `audit_events` (428) and `sessions` (73) are 78% of all rows. Retention governance is
still worth having as prevention — the policy is written — but it is not a capacity problem today,
and no data was deleted and no deletion tooling was built.

**The backend suite does not currently pass or fail cleanly — it stalls.** Two independent runs both
stopped at 32% in the same module, `tests/test_m18_4_insforge_migration.py`. Cause isolated: that
module builds a provider client against `http://127.0.0.1:7130` with a 5-second timeout, and nothing
listens on 7130, so each affected case burns its timeout serially. In the first run the process sat
at 0.0% CPU for over ten minutes.

Two things worth stating plainly. **This is a loopback address, not an external provider** — the
pytest process held no TCP or UDP sockets when inspected, so no forbidden external request occurred.
And **zero tests failed** up to the stall in either run. **No test was skipped, deleted or marked
xfail to make this go away**; the backend gate is recorded as INCONCLUSIVE rather than PASS. Prior
sessions logged the same class of symptom ("Regression Test Output Timeout During M62.9R
Certification"). `pytest-timeout` is declared in `pyproject` dev extras but is absent from the
shared venv.

## Work deliberately not done

Phase 9 optimisation — no evidence-backed bottleneck existed, and the mission forbids speculative
rewrites. Phase 11 tooling — a destructive capability against a 7.3 MB dataset with no measured
pressure. Phase 6 mobile — the viewport could not be varied; Chrome pins a minimum window width and
the viewport stayed at 819 CSS px across 375/390/768/1440 requests, so phone behaviour is
**unverified, not passed**. Phase 17 browser certification and Phase 18 clean clone — 18 of 24
required journeys need authentication, and a certification script that cannot execute its own gate
would emit a misleading PASS. Phase 4 in-app feedback surface — new UI is feature work, forbidden
while workflows remain unvalidated.

## Coverage honesty

2 of 145 routes were browser-verified in this session. 1 of 145 was accessibility-audited. 0 of 54
Trading Guardian pages were individually confirmed non-live, though the shell badge and the runtime
authority values were verified. Absence of evidence is not evidence of absence — unknown P0 and P1
defects may exist in the authenticated journeys nobody has exercised.

## Required statements

**SAATHIOS WAS VALIDATED AS A COMPLETE PRODUCT JOURNEY, NOT ONLY AS A COLLECTION OF COMPONENTS** —
**THIS CANNOT BE ASSERTED.** Only unauthenticated entry, navigation shell, session expiry and
recovery were validated as journeys. The complete journey through workspace, mission, approval,
assistant and voice was not traversed by anyone.

**REAL INVITED USER FEEDBACK WAS RECORDED WITHOUT FABRICATION** — no feedback was recorded, because
no real user session occurred. The log is empty by design. Nothing was invented.

**ALL P0 AND P1 PRIVATE-ALPHA DEFECTS WERE RESOLVED OR THE RELEASE WAS BLOCKED** — true for defects
found. One P1 was found and fixed; no P0 or P1 remains open. The release is blocked anyway, by the
absence of validation.

**AUTHENTICATION, SESSION RECOVERY, RBAC, WORKSPACE, PROJECT, MISSION, APPROVAL, ASSISTANT, VOICE
AND OPERATIONS WORKFLOWS WERE VALIDATED** — **PARTIALLY.** Session recovery was validated end to
end in a real browser. Authentication was validated only to the point of the sign-in form. RBAC,
workspace, project, mission, approval, assistant and authenticated voice/operations were **not**
validated at runtime.

**PERFORMANCE AND RELIABILITY WERE MEASURED BEFORE OPTIMISATION** — true. No budget was asserted
before measurement, and no optimisation was performed at all.

**DATABASE RETENTION WAS TREATED AS A GOVERNANCE DECISION** — true. Classified by authority and
evidentiary value; no tooling built; no row deleted.

**NO SECURITY CONTROL WAS WEAKENED TO IMPROVE CONVENIENCE** — true.
**NO PUBLIC REGISTRATION WAS ENABLED** — true; no such path exists.
**NO PROVIDER OR BROKER CONNECTION WAS CREATED** — true.
**NO REAL FINANCIAL CREDENTIAL WAS ACCEPTED OR STORED** — true.
**NO FINANCIAL ACCOUNT OR ORDER AUTHORITY WAS ENABLED** — true.
**NO PUBLIC DEPLOYMENT OR RELEASE WAS PERFORMED** — true.

## Recommended owner decision

1. **Run the three tester sessions yourself first**, as owner, using `REAL_USER_TEST_SCRIPTS.md`.
   You are the only person who can open the authentication gate. One owner pass through Scripts A,
   C and E would convert most of this report's "unverified" entries into evidence.
2. **Finish the audio review.** Fifteen human checks are still `AWAITING_OWNER_INPUT`, and the
   zero-Nepali-voice finding needs your judgement on whether the fallback is acceptable.
3. **Install `pytest-timeout` and re-run the backend suite with local services stopped**, so the
   backend gate produces a real verdict instead of a hang.
4. **Decide `PA-D-006`** — set `OLLAMA_HOST=127.0.0.1` or accept the exposure knowingly.
5. Only after 1–3 should any release candidate go to a second tester.
