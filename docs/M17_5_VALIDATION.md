# M17.5 Validation — Second Live Application (SQLite)
LIVE-APPLICATION-TESTED: SQLite through the gateway — inspect_schema (integrity
ok), query_readonly (-readonly blocks writes: DB unchanged), safe_mutation
(reversible, verified, row present). Independent verification opens the DB
directly (PRAGMA integrity_check + table count), never trusting the CLI's word.
SECURITY/RED-TEAM: dot-commands (.shell/.import), ATTACH, multi-statement,
load_extension, PRAGMA, VACUUM, identifier injection all rejected; cross-user
blocked; argv-only; DB path file-root confined. Tests: test_m17_5_sqlite.py (14).
Red-team 78/78. Platform now has TWO live application harnesses (FFmpeg + SQLite).
Verdict: MULTI-APPLICATION PILOT READY — two real applications execute through the
same trusted-harness path with independent verification, trust + source pinning,
and cross-user isolation. Not PRODUCTION READY (monitoring/multi-user/rollback-
drill/long-session unproven; GUI apps still dependency-blocked).
