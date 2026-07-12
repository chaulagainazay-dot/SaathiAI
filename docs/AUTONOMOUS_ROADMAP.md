# SaathiOS Autonomous Roadmap

Detected state: branch milestone/m7-security-engine, HEAD c2b23a1 (M17.6, three
live apps: FFmpeg/SQLite/jq). Verdict chain: browser DIGITAL WORKER PILOT READY
(M17.1); native NATIVE DESKTOP STAGING READY (M17.2); harness AGENT-NATIVE
APPLICATION PILOT READY (M17.3); multi-app HARNESS PLATFORM (M17.4–M17.6, three
live apps across three distinct categories).

## Candidate scoring (0–5: value/strategic/necessity/security/dep-ready/env/complexity-inv/regr-inv/evidence/cost-inv/reversible/ready-now)
| candidate | notes | ready-now |
|-----------|-------|-----------|
| **M17.7 archive live app (zip/unzip)** | fourth DISTINCT category (packaging); first LIVE exercise of the ZIP-slip/zip-bomb security verifier (`verify_zip_safe`) — prior 3 live apps never emitted an archive; zip+unzip installed; bounded/reversible; no install/permission/credential | **5** |
| workflow intelligence | prompt says NOT until execution layers sufficiently live-tested; large | 1 |
| release-candidate stabilization | valuable but no acute blocker; gates already green | 3 |
| native Finder/TextEdit live | permission-blocked (macOS TCC) — user action required | 0 |
| authenticated browser/cloud workflow | needs a safe staging credential | 1 |
| production monitoring/alerting | valuable but medium/large; unbounded for one iteration | 2 |
| cloud/multi-user hardening | large; premature | 2 |

## Decision (this invocation)
Priority rule: "missing real-world evidence for an already-built system." The
archive-security verifier (ZIP-slip + zip-bomb) was security-critical since M17.4
but had only synthetic unit coverage — no live application had ever produced or
routed a real archive through it. → **M17.7 zip archive live application harness**.
Distinct fourth category, exercises untested-live security code against a REAL
hostile archive, bounded, no install/permission/credential, reversible. Highest
ready-now leverage.

## Blocked / deferred (unchanged; need user action or larger scope)
- native Finder/TextEdit actuation — macOS Accessibility not granted.
- LibreOffice / Blender / Kdenlive / Inkscape / ImageMagick — not installed.
- authenticated browser/cloud workflow — needs a safe staging account.
- workflow intelligence + production monitoring — larger, gated / less bounded.
