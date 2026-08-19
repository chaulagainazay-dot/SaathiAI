# R2.1 — speaker identity authority boundary

**Verdict:** `SPEAKER_IDENTITY_AUTHORITY_BOUNDARY_REPAIRED_WITH_LIMITATIONS`
**Branch:** `validation/r2-1-real-microphone-owner` (unpushed) · **Captured:** 2026-08-19

Machine-readable record: `R21_SECURITY_REPAIR_EVIDENCE.json`.

## What was wrong

An identity *observation* was treated as authority. A voiceprint match — or a
boolean in an anonymous request body — selected `Identity.ADMIN`, satisfied
both `human_approved` and `code_confirmed`, and unlocked privileged tool
execution. Six paths fed that same signal: the chat request body, the Telegram
bridge, the default conversation brain, the voice command endpoint, the
wake-word listener, and push-to-talk.

Removing the privileged bypass was not enough. The legacy dispatcher still
ended in a direct `handler(**args)` call for every tool classified
`LEGACY_BOUNDED` — around 70 named tools, plus, through the default
classification, any handler registered afterwards. Those executed outside the
ExecutionGateway contract: no approval reference, no idempotency key, no
gateway audit record. With every handler replaced by a counting mock, five of
ten probed tool classes executed directly, including read-only, filesystem and
networked tools.

## What changed

- **Identity carries no authority.** The dispatcher runs as `Identity.USER`
  with `human_approved=False` and `code_confirmed=False`. A speaker match is
  bounded metadata that reaches the L7 audit and changes no decision. Approval
  is only ever a server-minted `ToolApprovalReference` validated by
  `ToolExecutionService`.
- **The legacy path executes nothing.** It classifies, governs, audits, and
  routes to the canonical gateway. Malformed arguments and unknown tools fail
  closed. An AST invariant plus an exhaustive runtime sweep keep it that way.
- **Both legacy endpoints are authenticated.** `/agent/chat` lost its trust
  field and is closed to anonymous callers; `/voice/command` returns 401 before
  the upload is read, decoded, transcribed, persisted, sent to an LLM, or
  synthesised, and its conversation session is namespaced by a server-derived
  principal.
- **Audio processing is bounded.** Media type, byte size, and decoded duration
  are capped from the existing voice runtime contract, and temporary files are
  cleared on every path including ffmpeg failure, timeout, decoder failure, and
  cancellation.
- **Enrollment is retired, not re-gated.** The endpoint answers
  `voice_enrollment_unavailable` without reading audio or touching an existing
  profile, and every frontend surface that offered it — including the reachable
  legacy static client — is gone.

## How it was validated

| Gate | Result |
|---|---|
| Full backend suite at the S4 SHA | 7727 passed · 8 skipped · 0 failed · 0 collection errors · 19:33 |
| Bounded regression (auth, RBAC, approvals, guardian, risk, voice, M64) | 699 passed · 1 skipped |
| Adversarial matrix (30 items) | 45 tests, all pass |
| Frontend suite | 694 passed |
| Lint · production build | 0 errors · success |
| Secret / credential / path scan | 0 strong hits |
| R2.1 dock layout certificate | PASS — 10 hard, 56 layout, 28 accessibility |
| M77 voice browser certificate + M64 regression | PASS — 36 hard / 21 gates |
| S6 enrollment retirement browser certificate | PASS — 26 hard gates |

Ports 3000 and 8765 were clear before and after every run, and no service was
started during the backend suite.

## Disclosures

- `test_replay_redacts_credentials` is a **pre-existing timestamp-sensitive
  assertion flake**: the test asserts the literal `"999"` is absent from a blob
  containing `time.time()` floats, so a timestamp like `1787130767.713999`
  fails it. Measured at 0.33% per run over 4000 real-clock samples. The
  redaction property itself passed in every observed run. Not repaired here.
- `test_live_browser_launch_and_close` remains a contention-sensitive browser
  flake. It did not recur in the authoritative run.
- The M77 certificate's external `agent-browser` step timed out once and passed
  on an unchanged-code retry.

## Containment

`com.saathi.local` (`RunAtLoad=true`) launches `~/SaathiAI/scripts/start_local.sh`
— the **unrepaired** main tree. It was unloaded from the per-user domain; the
plist was not edited, renamed, or deleted, and its SHA-256 is unchanged. This
is `TEMPORARY_LOCAL_CONTAINMENT_PENDING_CANONICAL_TRUNK_PROMOTION` and is not
committed. The reversible restoration command is recorded in the JSON record
and must not be run until a repaired canonical checkout is promoted **and** the
plist's target script is reviewed against it.

## Limitations

The full list is in the JSON record. The ones that matter most:

- **On-box callers are trusted.** A genuine loopback request with no forwarding
  header is treated as authenticated, so any local process reaches these
  endpoints. This is pre-existing shared policy, not a change made here.
- **`/voice/command` still exists.** Authenticated, scoped, bounded, advisory —
  but still a legacy surface.
- **Session scoping is single-owner.** The principal namespace prevents
  cross-session access, not cross-tenant access.
- **Frontend route protection is per-page, not global.**
- **The voiceprint code path still runs** on an authenticated turn. It is
  metadata and gates nothing, but it has not been deleted.

This evidence contains no exploit command, no reproduction payload, no raw
audio or voice-profile contents, and no credential material.
