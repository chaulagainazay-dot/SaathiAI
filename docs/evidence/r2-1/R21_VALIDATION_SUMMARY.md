# R2.1 — real microphone owner validation

Final repair SHA: `d4485a6cb0395d2bc2e5ae010e2d34924c432262`
Branch: `validation/r2-1-real-microphone-owner` (not pushed, no PR)

## What was repaired

| Defect | Commit |
|---|---|
| D3 — session end left the streaming input pipeline running | `2d3d5f5` |
| D2 — two SpeechRecognition owners for one microphone | `320c843` |
| D4 — production capture discarded the mic constraints contract | `7d7457f` |
| `/command` React #31 and two phantom infrastructure reads | `83788c1` |
| Backend voice sessions stranded in LISTENING until the budget refused new ones | `e7d8edc` |
| Shell pipeline kept running when another surface preempted its input claim | `d4485a6` |

## Browser automation disclosure

All browser journeys are labelled

    REAL_BROWSER_AUTOMATION_WITHOUT_PHYSICAL_MICROPHONE

They ran headless Chromium with a fake media device. No physical microphone
and no human speech was involved. They prove plumbing, ownership, teardown and
route behaviour. They prove nothing about recognition accuracy, Nepali or
code-switched transcription, echo behaviour, or how the dock feels to a person
speaking into it. That is what Test A is for.

## Certificates at the final SHA

| Certificate | Verdict |
|---|---|
| R2.1 dock layout — 7 viewports | PASS · 10 hard, 56 layout, 28 accessibility |
| M77 voice browser | PASS · 36 hard, 6 responsive, 2 accessibility, 4 security |
| M64 shell regression | PASS |

All three record `mode: production-build-loopback` with matching
`frontendSha` and `backendSha` at `d4485a6`.

`repoDirty` reads `true` in these certificates. The reason is self-referential
and worth stating rather than hiding: the dock certificate writes its own
evidence into the working tree, and the M77 run that follows observes those
files. The repository was clean at the start of the run and no source file
differed from `d4485a6`.

## Automated gates at the final SHA

| Gate | Result |
|---|---|
| Focused D2/D3/D4 + lifecycle + exclusion + command tests | 117 pass |
| Full frontend suite | 671 pass |
| Frontend lint | 0 errors, 3 pre-existing warnings |
| Frontend production build | compiled, 138 static pages |
| Backend voice runtime + R2.1 lifecycle | 51 pass |
| Auth / CORS | 195 pass |
| Approval / ExecutionGateway | 67 pass |
| Trading Guardian | 69 pass |
| Secret / credential / path scans | 0 findings |

## Open items recorded, not repaired

**Chat VoiceControl** — `LEGACY_SEPARATE_VOICE_SURFACE_DEFERRED_FOR_CENTRAL_COMMAND_CONVERGENCE`.
It still builds its own `SpeechRecognition`. Mutual exclusion with the shell
dock is proven deterministically in
`saathi-os/lib/voice-session/surface-exclusion.test.js`: at most one claim, at
most one live recognizer, switching surfaces tears the previous owner down,
and one spoken final can be submitted by exactly one surface. SaathiOS has one
active recognizer per ownership domain. It does not yet have one unified
system-wide recognition implementation, and this document does not claim
architectural convergence. Convergence belongs to the Central Command /
Mr. Yeti milestone.

**`GET /api/v1/infrastructure/health` is reachable signed out** —
`PUBLIC_HEALTH_CONTRACT_OVEREXPOSED_R3_SECURITY_FINDING`. It is listed in the
auth-exempt path set in `saathi/server.py` and returns 200 without a token.
Categories exposed: model/provider inventory identifiers, browser tier
identifiers, connector identifiers with display names, categories,
capabilities, per-connector authentication state, error and quota fields, and
conversation driver names. No credentials, tokens or secrets are exposed, and
no direct authority is reachable, so this was recorded rather than escalated.
No test or document authorises the public exposure. Referred to R3 Centralized
Authentication Policy Hardening. Authentication policy was deliberately not
changed in the command-rendering commit.

**A hard navigation while listening can still strand one session** — closing a
tab or a full page load cannot complete the terminal request, because the
cross-origin loopback split makes it a preflighted request that the unload
kills. Client-side navigation finalizes correctly (observed: 2 active → 1).
The backend reconciliation added in `e7d8edc` clears the stranded session once
it passes the idle bound, so it cannot accumulate toward the budget.
