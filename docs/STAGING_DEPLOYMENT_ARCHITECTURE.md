# Staging Deployment Architecture (M13.5)

## Recommended staging path (documented, NOT yet live-verified)
- **Backend**: `uvicorn saathi.server:app` (Procfile already defines this) behind a reverse proxy (Caddy/nginx) with TLS.
- **Frontend**: Next.js build (`saathi-os`) served statically or via Node; `NEXT_PUBLIC_SAATHI_API` points at the backend origin (empty string = same-origin behind the proxy).
- **Databases**: SQLite files under `data/` on persistent disk; backed up via `ops backup` on a schedule.
- **Artifacts/media**: `data/studio_workspaces/` on persistent disk with the M13 disk-safety preflight; large media should move to external object storage in production.
- **Secrets**: environment variables only; never in the repo. `ops config-check` validates presence.
- **Health**: `/api/v1/system/version` for identity + stale-backend detection; `ops status` for listener/stale detection; `ops health` for storage+db.

## CRITICAL platform constraint
`macOS say` (Studio narration + Voice OS TTS) is **macOS-only**. A cloud Linux host has NO `say`. Production on Linux MUST either:
1. run on macOS infrastructure, or
2. configure a tested cross-platform TTS provider (the provider contracts exist; a Piper/Coqui/cloud adapter must be wired + verified before relying on narration in Linux staging).
The provider capability matrix already reports `say` as local/unavailable off-macOS — it will not silently fail; it degrades to the deterministic adapter, which produces no real audio.

## Deploy dry-run / rollback
- `python -m saathi.ops release-check` gates a release locally (storage/config/db/backup+restore/secret).
- Real staging deploy + live rollback drill are **NOT run in this environment** (no staging infra). The rollback foundation (pre-rollback backup + verified restore) is proven; a live staging rollback drill is required before PRODUCTION READY.
