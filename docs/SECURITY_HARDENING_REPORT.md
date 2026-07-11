# Security Hardening Report (M13.5)

## Verified (automated tests)
- **AuthN/AuthZ**: every `/api/v1/*` route 401-gated by middleware (session cookie / SAATHI_TOKEN / local); verified across M8–M13 + ops via 401 tests.
- **Cross-user isolation**: chat, memory, voice sessions, studio projects, agent runs, approvals — all prove PermissionError/404 on cross-user access.
- **Cross-project / cross-namespace**: M9 memory scope firewall; M13 project ownership.
- **Approval ownership + expiry**: M10 approve path (reused by voice + studio) rejects cross-user, expired, and unknown approvals.
- **Path traversal**: studio storage `safe_path` and backup restore both reject `..` escapes (tests).
- **Shell injection**: FFmpeg args are list-form only; string args raise (test).
- **SQL injection**: all queries parameterized (no string interpolation of user input).
- **Stored prompt injection**: retrieved memory / transcripts / stored content treated as untrusted data — cannot change policy (M9/M10/M12/M13 tests).
- **Secrets**: remotes credential-free (Repair 0); firebase key untracked + gitignored; `data/` (dbs, media, backups) gitignored; release-gate strong-credential scan clean; `$ENV` placeholders allowlisted.
- **Log/health leakage**: `/api/v1/system/version` exposes only counts + commit; config-check redacts secret values to PRESENT/ABSENT.

## Not verified in this environment (reported, not claimed)
- Browser-level CSRF/cookie-flag/session-fixation behavior (no authenticated browser flow run).
- Dependency CVE scan (see docs — no `pip-audit`/`npm audit` run this milestone; recommended for CI).
- SSRF / file-upload MIME / archive-extraction beyond the tested traversal guard.

## P0/P1
None found. Auth + isolation + injection guards all pass.
