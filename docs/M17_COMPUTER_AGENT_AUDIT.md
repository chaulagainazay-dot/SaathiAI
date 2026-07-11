# M17 Universal Computer Agent Audit

## Start state
Commit d53a619 (M16). 1325 passed. CONTROL CENTER STAGING READY.

## Approach: connectors, not a new framework
Computer operations are registered as M15 connector tools (vision/desktop/
browser_agent). Every action therefore flows through the existing ExecutionEngine
→ ExecutionGateway → M15.2 ownership → M15.3 scope engine + circuit breaker →
risk/approval → evidence. NO new execution engine; NO app-specific code.

## Components
- perception.py: canonical UIElement + Screen (windows/buttons/inputs/menus/
  tables/errors/loading… + clickable/editable/enabled/visible/focused).
- providers.py: provider abstraction (Playwright/CDP/macOS-Accessibility/Windows-
  UIA/Linux-AT-SPI/OCR-Tesseract/OpenCV/vision-LLM); deterministic default; honest
  availability probes; live control env-blocked (importable != verified).
- operations.py: ComputerAdapter + register() → connectors/tools with EXPLICIT
  risk (read L0, click/type/scroll L2, upload/download/send L3 approval, delete/
  purchase/run_binary L4 manual-only) + require_verification.
- verification (in adapter): post-action re-perceive; unverified → uncertain
  (never assume success).
- replay.py: sanitized replayable timeline (password/otp/token/secret → REDACTED).
- agent.py: runner using the M15 integration funnel (describe-before-act + step).
- cli.py: providers/connectors/describe/perceive (read-only).
- Control Center: computer_agent() cell + /api/v1/control/computer (honest
  live_desktop_control = environment_blocked).

## Security (red-team 34/34)
destructive-needs-approval, password-not-in-replay, agent-cannot-self-approve-
purchase, cross-user desktop isolation, never-assume-success.

## Honest limits (NOT done / environment-blocked)
Live desktop control, real browser actuation, OCR/vision on real screens,
authenticated-app workflows, multi-monitor, replay re-run against live apps.
All deterministic; live is not faked. Voice/CEO/Chat computer surfaces are wired
via the shared funnel + Computer Center read model, not live-driven here.

## M17 hardening (session/consent + security boundary)
Added on top of the M17 core:
- **session.py** ComputerSession: active-session consent boundary (auth user +
  device + os_user + allowed apps/origins/file-roots/displays + risk ceiling +
  expiry + screenshot/clipboard policy). Emergency stop (collision-checked
  shortcut) halts control; stop conditions: expiry/stop/revoke/lock/identity-
  change/secure-desktop. No control without a live session.
- **intent.py** ComputerActionIntent + InteractionLayer (API>DOM/CDP>
  accessibility>OCR/vision>coordinate). Coordinate never default when a
  structured element exists; mutation requires a postcondition; input digest +
  to_dict redact sensitive args.
- **sensitive.py**: sensitive-field detection (AX role/DOM type/label); pause-
  for-user plan (no capture); CAPTCHA/MFA/biometric detection + bypass refusal.
- **policy.py**: browser origin allow-list, download confinement, upload allow-
  list; desktop app allow-list, file-root confinement (traversal + symlink-escape
  rejected); shell + AppleScript injection guards; page/AX text is untrusted data.
- **recovery.py**: obstacle classifier; CAPTCHA/MFA/secure-input/login/permission
  → pause_for_user; crash/expiry → replan_from_checkpoint; irreversible+uncertain
  → stop_uncertain; no budget → stop_no_progress.
- Agent wired: active-session + app/origin allow-list + sensitive pause enforced
  before every action; emergency_stop().
- Control Center: /control/computer page (connectors, tools, honest provider
  availability, live_desktop_control = environment_blocked).

Red-team expanded to **46 attacks (46/46 hold)**: page prompt injection stays
data, download traversal, upload substitution, symlink escape, AppleScript/shell
injection, CAPTCHA bypass refused, MFA capture refused, sensitive-not-recorded,
emergency-stop halts, app-allow-list, coordinate-not-default.

### Honest capability classification (unchanged where live)
implemented + deterministic-tested + red-team-tested: full hardening spine.
live-browser-tested / live-desktop-tested: **none** (permission/dependency-
blocked — no verified Playwright run, no Accessibility permission, no vision
credentials). contract-ready: Windows UIA + Linux AT-SPI. Not claimed as
operational on real applications.
