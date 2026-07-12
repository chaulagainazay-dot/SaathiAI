# SaathiOS Capability Maturity Matrix (as of HEAD 0a77882)

Levels: implemented < deterministic-tested < security/red-team-tested < live-tested < production.

| capability | maturity | evidence |
|-----------|----------|----------|
| ExecutionGateway / approval binding | live+red-team | M15/M15.2 gateway-routed, 78/78 red-team |
| Connector platform (local git/fs) | live-tested | M15.1 real local execution |
| Connector platform (cloud gmail/gcal/telegram) | environment-blocked | no credentials |
| Browser agent (Chrome CDP) | live-browser-tested | M17.1 real workflow |
| Native macOS (enumeration/identity/screenshot) | live-desktop-tested | M17.2 real NSWorkspace/screencapture |
| Native macOS actuation (Finder/TextEdit) | permission-blocked | AXIsProcessTrusted=False |
| Application harness — FFmpeg (media) | live-application-tested | M17.3/M17.4 transcode+verify |
| Application harness — SQLite (database) | live-application-tested | M17.5 schema/query/mutation+integrity |
| Application harness — jq (JSON transform) | live-application-tested | M17.6 transform+json verify |
| Application harness — zip (archive packaging) | live-application-tested | M17.7 pack+ZIP-slip/zip-bomb verify (live hostile archive) |
| Application harness — GUI apps (LibreOffice/Blender/Kdenlive) | dependency-blocked | not installed |
| Harness long-running task control (cancel/timeout-kill/resource-limits/crash-recovery) | live-proven | M17.8 real cancel+SIGXFSZ+reconcile, orphan-free |
| Red-team harness | live | 78/78 deterministic |
| Backup/restore | deterministic+drill | M13.5 real drill |
| Multi-user isolation | single-user tested | cross-user probes only |
| Production monitoring/alerting | not built | gap |
| Workflow intelligence engine | not started | gated on live-execution proof |

## Highest-value NON-blocked evidence gap now
Four live apps (media/database/JSON/archive) now exercise the harness across four
distinct categories, and the archive-security verifier (ZIP-slip/zip-bomb) is
proven live against real hostile archives (M17.7). Remaining safe real-evidence
wins are reliability-oriented (long-running task control, production monitoring)
and are medium/large / less bounded, or are blocked on installs (GUI apps),
permissions (macOS TCC actuation), or credentials (authenticated cloud/browser).
