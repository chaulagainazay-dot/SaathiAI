# M17.4 Multi-Application Harness Platform Report

## Start
Commit aee5721 (M17.3). AGENT-NATIVE APPLICATION PILOT READY.

## Added (generalization + hardening; no new execution path)
- discovery.py: real installed-application detection (NSWorkspace + /Applications
  + which + brew); Windows/Linux contract-ready.
- installer.py: staged secure install (inspect→hash-verify→dependency-verify→
  path-hijack-check→smoke→register), rollback; refuses arbitrary URL / embedded
  command / unknown method / unpinned source / unsafe binary path.
- lifecycle.py: update (RESETS trust, backup for rollback), disable/quarantine/
  revoke/uninstall (all block execution, preserve evidence).
- limits.py: RLIMIT CPU/AS/FSIZE preexec + wall-clock + artifact cap; wired into
  the ApplicationHarnessAdapter.
- verify.py expanded: docx/pptx/xlsx (OpenXML + ZIP-slip + zip-bomb), jpeg, mov/
  mkv/mp4, mp3/wav (ffprobe), generic zip (bomb guard), directory tree (confined).
- pilots/apps.py: LibreOffice/Blender/Kdenlive/Inkscape/ImageMagick harness defs
  (contract-ready; present→approved, absent→dependency-blocked, never faked).
- Control Center harness cell + discovery.

## Applications
| app | status |
|-----|--------|
| FFmpeg | LIVE-APPLICATION-TESTED (M17.3 + expanded verifiers on real artifacts) |
| LibreOffice / Blender / Kdenlive / Inkscape / ImageMagick | dependency-blocked (not installed) |

## Live evidence
FFmpeg transcode through the gateway (M17.3) + expanded verifiers run on REAL
ffmpeg-generated png/mp4/wav (verified: dimensions/streams/duration). Secure
install validated the real ffmpeg binary (path-hijack check + smoke + sha256).

## Verdict
**HARNESS PLATFORM STAGING READY** — platform generalized (discovery, secure
install/update/rollback/revocation, resource limits, 15+ format verifiers,
multi-app definitions) + red-team-hardened (75/75). Only ONE application (FFmpeg)
is live; others are honestly dependency-blocked. NOT MULTI-APPLICATION PILOT READY
(requires ≥2 real apps live) and NOT PRODUCTION READY.
