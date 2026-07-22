# M17.1 Live Computer Validation Audit

## Start state
Commit ed0d253 (M17 hardening). 1374 passed. COMPUTER AGENT STAGING READY.

## Live environment (probed, not assumed)
| dependency | status |
|-----------|--------|
| Google Chrome (/Applications/…) | PRESENT — Chrome/149 |
| Brave, Safari | present |
| Playwright python + browser binary | package traceback + binary ABSENT → dependency-blocked |
| Chrome DevTools Protocol (headless, loopback) | AVAILABLE (no install) |
| Tesseract OCR | absent → dependency-blocked |
| OpenCV | absent → dependency-blocked |
| macOS version | 26.5.1 |
| macOS Accessibility / Screen Recording / Automation (TCC) | not granted; cannot self-grant → user-action-required |
| TextEdit / Finder | present (but need TCC to control) |

## Decision
Real live browser control achieved WITHOUT installing anything and WITHOUT any
macOS permission by launching system Chrome headless with a bounded loopback
`--remote-debugging-port` + isolated `--user-data-dir`, driven over the Chrome
DevTools Protocol via a minimal stdlib websocket (`browser_driver.py`). No large
dependency installed; no system permission modified.

Native desktop (Finder/TextEdit/Accessibility/Screen-Recording) requires macOS
TCC permissions that cannot be granted non-interactively in this environment →
honestly classified **permission-blocked**, not attempted-as-fake.

## Validation plan (executed)
Real browser workflow through the gateway: launch isolated Chrome → load local
test site → read DOM → fill non-sensitive field → click submit → verify
confirmation text → screenshot → sensitive-field pause → clean close. Desktop =
permission-blocked. OCR/vision = dependency-blocked. Authenticated + external
side-effect = environment-blocked.

## Limitations
No live desktop actuation, no OCR/vision, no authenticated-account workflow, no
multi-monitor (single logical display), no real external side effect — all
reported honestly in the live-validation report.
