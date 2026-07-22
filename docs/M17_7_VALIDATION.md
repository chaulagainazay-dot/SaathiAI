# M17.7 Validation — Fourth Live Application (zip archive / packaging)

LIVE-APPLICATION-TESTED: `zip` / `unzip` (archive packaging) through the gateway.
A real archive is packed from a root-confined file (`zip -q -X -j`) and the
produced container is INDEPENDENTLY verified by `verify.verify_zip_safe` — the
container is inspected directly (namelist + compression ratio), never trusting the
packaging tool's exit code.

WHY THIS CLOSES A REAL EVIDENCE GAP: FFmpeg (media), SQLite (database) and jq
(JSON) all emit media or structured text — none is an archive, so the harness's
ZIP-slip / zip-bomb verifier (`verify_zip_safe`, security-critical since M17.4) had
only synthetic unit coverage and had never run end-to-end against a real archive
file through the service path. M17.7 is its first LIVE exercise: a genuinely
hostile `.zip` carrying a `../escape.txt` traversal entry, and a high-ratio
zip-bomb, are each routed through the SAME service → adapter → gateway → verify
path and verify as NOT success even though `unzip` exits 0.

SECURITY / ISOLATION:
- Untrusted member names validated (`validate_member`): leading `/`, any `..`
  component, and NUL are rejected before argv is built.
- `-j` junk-paths guarantees our own output stores only flat basenames (no
  traversal entry can be produced); `-X` drops uid/gid/extra attributes.
- argv-only through the sole adapter boundary (never a shell string); input paths
  file-root confined; sanitized minimal environment.
- Independent verifier rejects ZIP-slip (leading `/` or `..`) and zip-bomb
  (uncompressed bound + ratio > 200); ambiguous/failed verification is never
  reported as success.
- Cross-user ownership mismatch blocked at the service gate.

TESTS: `tests/test_m17_7_zip.py` (14, live zip/unzip) — four-live-applications
present; traversal members rejected; live pack verified; ZIP-slip archive → not
success; zip-bomb archive → not success; clean-archive list verified; cross-user
blocked; verifier helper direct.

LIVE REPORT: `zip_pack` and `zip_slip_rejected` both `live-application-tested`;
executable harnesses now `{ffmpeg, sqlite, jq, zip}`.

Verdict: MULTI-APPLICATION PILOT READY (strengthened) — FOUR distinct real
application categories (media / database / JSON transform / archive packaging)
execute through one trusted-harness path with independent verification, trust +
source pinning, and cross-user isolation, and the archive security verifier is now
proven live against real hostile archives. Not PRODUCTION READY
(monitoring/multi-user/rollback-drill/long-session unproven; GUI apps still
dependency-blocked pending install).
