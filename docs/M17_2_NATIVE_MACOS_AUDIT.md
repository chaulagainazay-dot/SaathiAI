# M17.2 Native macOS Audit

## Start state
Commit 2f66902 (M17.1). 1389 passed. DIGITAL WORKER PILOT READY (browser);
native-desktop permission-blocked.

## Live environment (probed)
| item | state |
|------|-------|
| macOS | 26.5.1, arm64 |
| PyObjC / Quartz / AppKit | PRESENT (12.2.1) |
| NSWorkspace app enumeration | WORKS (real 19–87 GUI apps, bundle IDs + PIDs) |
| AXIsProcessTrusted (Accessibility) | **False** → actuation permission-blocked |
| Screen Recording (CGPreflightScreenCaptureAccess) | **True** → granted |
| Automation (System Events count) | works; per-app GUI activate fails -600 (no interactive session) |
| screencapture | WORKS (real 1.7MB PNG) |
| executable identity | venv python, adhoc-signed, stable path |
| Finder / TextEdit | present; control needs Accessibility + GUI session |
| Tesseract / OpenCV | absent |

## Canonical driver path (no bypass)
Agent → ComputerSession → ComputerActionIntent → ExecutionGateway → MacAdapter →
MacDriver (the ONLY place AX/Quartz/NSWorkspace/AppleScript is called) →
verification → sanitized replay.

## Honest classification
- **live-desktop-tested**: application enumeration, application/process identity
  verification (spoofed-PID rejected), screen capture, screen-recording readiness.
- **permission-blocked**: Accessibility tree, Finder/TextEdit/menu/app-switch/
  keyboard actuation (AXIsProcessTrusted=False — user must grant Accessibility to
  the interpreter identity).
- **environment-blocked**: GUI app activation + Electron + multi-monitor (no
  interactive session; osascript activate returns -600).
- **dependency-blocked**: OCR/vision (tesseract/opencv absent).

## Validation plan (executed)
Live reads through the gateway (enumeration, identity, screenshot). Actuation
attempted and honestly reported blocked. Nothing faked — no shell file op is
presented as Finder automation; no direct file write as TextEdit automation.

## Expected blockers
Accessibility grant + an interactive login GUI session are required for real
Finder/TextEdit actuation — both outside this non-interactive environment.
