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
