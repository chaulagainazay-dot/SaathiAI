# M17.5 Plan — SQLite live harness
Objective: prove a SECOND real application through the harness platform → move to
MULTI-APPLICATION PILOT READY. Files: pilots/sqlite.py, registry bootstrap, tests,
red-team probes, verify (db verifier), Control Center (auto). Ops: inspect_schema
(risk0, -readonly), query_readonly (risk0, -readonly), safe_mutation (risk2, into
pilot-workspace DB, reversible). Verification: open DB + PRAGMA integrity_check +
row/table count. Security: argv-only, DB path file-root confined, reject ATTACH/
dot-commands/multi-statement in untrusted args, reads use -readonly. Test plan:
unit + live sqlite (schema/query/mutation/integrity) + red-team (injection/attach/
readonly/confinement). Rollback: HEAD 67500d6. Completion: 2 live apps verified.
Stop: none expected (no install/permission/side-effect).
