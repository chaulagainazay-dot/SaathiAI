# M17.1 Live Validation Report

Machine-readable form: `python -m saathi.computer_agent.cli live-report`.

## LIVE-BROWSER-TESTED (real headless Chrome via CDP, through the gateway)
Verified by `run_browser_smoke()` + tests/test_m17_1_live.py (4 live tests):
- browser_launch — isolated profile, loopback-only CDP, real PID
- dom_inspection — real document.title / innerText read
- navigation — real click → page change to confirm.html
- form_fill — real input value set + input event
- postcondition_verification — confirmation text "Submission received" observed (confirmed=True)
- screenshot_capture — real PNG bytes to the confined workspace (never committed)
- sensitive_field_pause — password field → paused_for_user, value never typed/recorded
- replay_redaction — sanitized replay contains no secret value
- clean_browser_exit — process terminated + isolated profile removed

## PERMISSION-BLOCKED (macOS TCC not granted here)
macos_accessibility, finder_workflow, textedit_workflow, electron_workflow,
real_screen_capture (desktop), multi_monitor.

## DEPENDENCY-BLOCKED
playwright browser binary, tesseract OCR, OpenCV → ocr_vision_fallback.

## ENVIRONMENT-BLOCKED
authenticated_browser_workflow (no safe staging account),
approval_gated_live_side_effect (no authorized external target).

## Verdict
DIGITAL WORKER PILOT READY (browser). Real controlled browser workflow succeeds
through the canonical gateway with verification, sensitive-input protection,
redacted replay, and clean teardown. Native-desktop pilot remains permission-
blocked pending macOS TCC grants; production remains gated on authenticated
workflows + monitoring + multi-user isolation + long-session stability.
