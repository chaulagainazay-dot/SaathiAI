# ADR — Password KDF strategy

**Status:** Accepted (decision), implementation partially deferred.
**Date:** 2026-09-11
**Context milestone:** Session lifecycle & auth recovery.

## Context
Two password-hash paths exist (`saathi/authsec.py`, `saathi/server.py`):
1. **Managed passwords** (change-password, reset, security-store owner) → `authsec.hash_password` = salted **PBKDF2-HMAC-SHA256, 600k iterations**. `verify_password` also accepts `scrypt$` and, for backward compat, **legacy bare-sha256** (transparently upgraded on next change).
2. **Env-configured owner password** (`BAADAR_PASSWORD`) → `_PASSWORD_HASH` derived at boot as a **bare sha256 hex** (server.py:1849). Login verifies via the legacy-sha256 branch of `verify_password`.

## Decision
- **KEEP** the PBKDF2 path for all managed passwords — it is modern, salted, dependency-free (stdlib), and already the default for change/reset.
- **KEEP** the legacy bare-sha256 acceptance strictly as a compatibility path for the env-derived owner password and any un-upgraded stored hash. Do **not** remove it in this milestone — removing it would lock the owner out of an env-configured install.
- **DEFER** two hardening steps to their own change (they broaden this milestone and touch the live login path):
  1. Hash `BAADAR_PASSWORD` at boot with PBKDF2 (random salt) instead of bare sha256, so no bare-sha256 verification path is exercised for the primary credential.
  2. **MIGRATE to Argon2id** as the preferred KDF. Blocked on a dependency (`argon2-cffi`) — the VM install is intentionally stdlib-only, so this needs a deployment decision. Until then PBKDF2-600k is an acceptable, OWASP-aligned KDF.

## Consequences
- No behavior change in this milestone; login continues to work for the env-configured owner and for managed passwords.
- Follow-up ticket: PBKDF2-at-rest for `BAADAR_PASSWORD` + evaluate Argon2id (adds a dependency; needs VM sign-off).
- Never log `BAADAR_PASSWORD` or any hash containing sensitive material (unchanged rule).
