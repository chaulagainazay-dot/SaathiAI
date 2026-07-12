# M17.2 Native macOS Validation Report

Machine-readable: `python -m saathi.computer_agent.cli native-live-report`.

## LIVE-DESKTOP-TESTED (real macOS APIs, through the gateway)
- application_enumeration — NSWorkspace, real running GUI apps (bundle IDs + PIDs)
- application_identity — real verify; a spoofed/wrong PID is REJECTED
- screen_capture — real screencapture PNG to the confined pilot workspace
  (never committed; probe deleted immediately for privacy)
- screen_recording_readiness — CGPreflightScreenCaptureAccess = True

## PERMISSION-BLOCKED (Accessibility not granted: AXIsProcessTrusted=False)
accessibility_tree, finder_workflow, textedit_workflow, menu_interaction,
application_switching, native_keyboard_input.
User action: System Settings › Privacy & Security › Accessibility → enable the
interpreter/host identity.

## ENVIRONMENT-BLOCKED (no interactive GUI session)
electron_workflow, multi_monitor, GUI app activation (osascript activate → -600).

## DEPENDENCY-BLOCKED
OCR/vision (tesseract/opencv absent).

## Executable identity
venv python, adhoc code-signed, stable path — TCC binds to this identity; grant
Accessibility to it for actuation.

## Verdict
**NATIVE DESKTOP STAGING READY** — real macOS reads (enumeration, identity,
screen capture) verified through the canonical gateway; actuation (Finder/
TextEdit) is permission-blocked pending an Accessibility grant + interactive
session. NOT DIGITAL WORKER PILOT READY for native (no Finder/TextEdit workflow
completed). Browser pilot (M17.1) remains DIGITAL WORKER PILOT READY separately.
