# M13.5 Production Hardening Audit (Phase 1)

**Date:** 2026-07-11 · **Branch:** `milestone/m7-security-engine` @ `4e198d7`

Classification: P0 (release-blocking) · P1 (staging-blocking) · P2 (important) · P3 (polish).
Status: verified · partially-verified · unverified · unavailable-in-env.

## Findings

| # | Area | Finding | Sev | Status |
|---|------|---------|-----|--------|
| 1 | Runtime identity | `/api/v1/system/version` exists (M12) but lacks schema versions / frontend-build compare | P1 | partially-verified → **fix this milestone** |
| 2 | Stale backend | M11 live smoke hit a days-old process serving pre-M8 code; no duplicate/stale-process detection | P1 | unverified → **fix (ops status/identity)** |
| 3 | Backup/restore | `data/backups/` has 2 ad-hoc old copies; no repeatable backup cmd, no proven restore | P1 | unverified → **build + real drill** |
| 4 | Release gates | No `release-check`; readiness is implicit | P1 | unverified → **build with exit codes** |
| 5 | Config validation | No `config-check`; env loaded ad-hoc | P2 | unverified → **build** |
| 6 | Disk safety | M13 has per-render preflight; no global ops-level storage/cleanup command | P2 | partially → **build ops storage/cleanup** |
| 7 | DB integrity | 6 app dbs, no `PRAGMA integrity_check` tooling | P2 | unverified → **build** |
| 8 | Studio frontend | M13 backend/API only; no workspace UI | P1 (product gap) | unverified → **build (Phase 7)** |
| 9 | Auth | session cookie + SAATHI_TOKEN + local; `/api/v1/*` middleware-gated (verified across M8–M13 via 401 tests) | — | **verified (automated)** |
| 10 | Security invariants | cross-user/project isolation, approval ownership/expiry, path-traversal, shell-injection all have passing tests across M9–M13 | — | **verified (automated)** |
| 11 | Cloud providers / publishing | unconfigured (no keys/accounts) | — | **unavailable-in-env** |
| 12 | Browser workflows | Chat/agent/voice/studio full auth browser flows | P1 | **unverified** (sandbox can't grant getUserMedia; login cookie flow not run) |
| 13 | Deployment/rollback | `deploy/hf-deploy.md` exists; no validated staging path/rollback drill | P2 | unverified → **document + dry-run** |
| 14 | Streaming | chat SSE is post-completion word-chunking (documented M8); `llm.generate` non-streaming | P2 | **verified: NOT true streaming** — documented, not faked |
| 15 | Secrets | remotes credential-free, firebase key gitignored (Repair 0); data/ gitignored | — | **verified** |

## Plan (this milestone, honest scope)

Build `saathi/ops/`: runtime identity (schema versions), config-check, storage+cleanup (dry-run/apply), **real backup + real isolated restore drill**, db integrity, process/status, **release-check** (exit codes 0–12). Build the Studio frontend workspace on the existing `/api/v1/studio-os/*`. Strengthen `/api/v1/system/version` + frontend mismatch warning. Produce release-readiness matrix, security report, performance baseline, deployment/DR/runbook docs, incident template. Tests + manifest + full validation ladder.

**Explicitly out of reach in this environment (reported, never faked):** live authenticated browser workflow verification (no login-cookie automation / no getUserMedia), cloud image/video provider validation (no keys), real social publishing (no accounts), real staging deployment + live rollback drill (no infra). These stay `unverified` / `unavailable-in-env`.
