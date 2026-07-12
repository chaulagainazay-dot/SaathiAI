# SaathiOS Autonomous Roadmap

Detected state: branch milestone/m7-security-engine, HEAD 67500d6 (M17.4).
Verdict chain: browser DIGITAL WORKER PILOT READY (M17.1); native NATIVE DESKTOP
STAGING READY (M17.2); harness AGENT-NATIVE APPLICATION PILOT READY (M17.3);
multi-app HARNESS PLATFORM STAGING READY (M17.4, ONE live app: FFmpeg).

## Candidate scoring (0–5: value/strategic/necessity/security/dep-ready/env/complexity-inv/regr-inv/evidence/cost-inv/reversible/ready-now)
| candidate | notes | ready-now |
|-----------|-------|-----------|
| **M17.5 second live app harness (SQLite)** | closes M17.4's own gap (needs >=2 live apps); sqlite3 installed; safe/verifiable; no install/permission | **5** |
| workflow intelligence | prompt says NOT until execution layers sufficiently live-tested; only 1 live harness app | 1 |
| release-candidate stabilization | valuable but no acute blocker; gates already green | 3 |
| native Finder/TextEdit live | permission-blocked (macOS TCC) — user action required | 0 |
| authenticated browser workflow | needs a safe staging account (credential) | 1 |
| cloud/multi-user hardening | large; premature | 2 |

## Decision
Priority rule: "missing real-world evidence for an already-built system" +
"validate a second application before building a workflow marketplace." →
**M17.5 SQLite live application harness**. Bounded, no install, no permission, no
external side effect. Reversible. Highest ready-now leverage.
