# M17.6 Validation — Third Live Application (jq)
LIVE-APPLICATION-TESTED: jq (JSON transformation) through the gateway — real
transform (input JSON -> {count,name}) independently verified as valid JSON
(never trusting jq's exit alone). Empty/non-JSON output -> not success.
SECURITY/RED-TEAM: filters leaking env ($ENV/env), reading files (input/include/
import/getpath/input_filename), shelling out (@sh), or debug are rejected;
cross-user blocked; argv-only; input file-root confined; sanitized env.
Tests: test_m17_6_jq.py (17). Red-team 81/81. Platform now has THREE live
application harnesses across THREE distinct categories: FFmpeg (media), SQLite
(database), jq (structured-data transformation).
Verdict: MULTI-APPLICATION PILOT READY (strengthened) — three distinct real
applications execute through one trusted-harness path with independent
verification, trust + source pinning, cross-user isolation. Not PRODUCTION READY
(monitoring/multi-user/rollback-drill/long-session unproven; GUI apps still
dependency-blocked).
