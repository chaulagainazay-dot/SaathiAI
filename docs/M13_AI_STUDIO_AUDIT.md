# M13 AI Studio — Audit (Phase 1)

**Date:** 2026-07-11 · **Branch:** `milestone/m7-security-engine` @ `1228397`

## Existing studio/media code

| Location | Role | Disposition |
|---|---|---|
| `saathi/ai_studio.py` (`AIStudio`, `StudioRun`, `StageReport`) | Run-tracking layer with pluggable stage callbacks (research/script/voice/images/render/publish); the defaults are placeholders and the real media gen happens on Ajay's Mac worker | **KEEP for the existing dashboard.** Not gateway-routed, not versioned-artifact based. M13 does not extend it — it would fork the model. Left untouched. |
| `saathi/studio_store.py` | Records `studio_runs` rows (topic/mode/status/cost/video_url) for the dashboard | KEEP (dashboard reporting), not reused as the M13 artifact store. |
| `saathi/content_pipeline.py` (`ContentFactoryPipeline`, `Stage`, `Scene`) | Content-factory pipeline w/ scenes | Reference for scene shape; not the orchestrator (M13 uses M10). |
| `saathi/studio_directors.py`, `studio_control_room.py`, `studio_visual.py`, `tools/content_studio.py`, `tools/mr_yeti_pipeline.py` | Domain directors + Mr Yeti pipeline + control room | Out of scope, untouched. |
| FFmpeg users: `render_director.py`, `quality.py`, `tools/clip_extractor.py`, `tools/backup_video.py` … | Scattered direct `ffmpeg` subprocess calls | M13 adds ONE argument-safe gateway-routed FFmpeg engine; does not refactor the existing scattered callers. |

## Dependency reality (checked, not assumed)

| Tool | Status |
|---|---|
| `ffmpeg` + `ffprobe` binaries | **present** (`/opt/homebrew/bin`) — real local render/probe achievable |
| `Pillow` (PIL) | **installed** — real local thumbnail/image generation achievable |
| `numpy` | installed |
| macOS `say` (via M12 `SayTTS`) | available — real narration audio |
| Free disk | 87 GB (real `shutil.disk_usage` preflight will use this) |
| Cloud image/video (Flux/Veo/HeyGen/ComfyUI) | **not configured** — no keys/servers. Deterministic adapters only; never claimed tested. |
| Publishing accounts (YouTube/TikTok/…) | **not configured** — publish is approval-gated dry-run only; a real receipt is never fabricated. |

## Chosen architecture (consolidation, not a new framework)

New package `saathi/studio_os/` reusing existing systems:
- **Orchestration:** the M10 `Orchestrator` (Studio workflows = M10 strategies; Studio agent roles registered into the existing M10 `registry`). No second orchestrator.
- **Memory:** M9 `MemoryEngine` for the learning loop + research provenance.
- **Approvals:** M10 `Orchestrator.approve` / approval store — the same ownership/expiry-checked path M11/M12 use. No parallel approvals.
- **Gateway:** every provider/FFmpeg call is a `ToolIntent` through `ExecutionGateway`.
- **Events:** the repaired fabric bus (`studio.*`).

New in `studio_os/`: `models.py` (Project state machine, Artifact model), `store.py` (projects/artifacts/stages/costs/publish schema), `storage.py` (REAL disk preflight + quotas + checksum dedup + cleanup), `ffmpeg_engine.py` (REAL argument-safe gateway-routed render/probe/thumbnail), `providers.py` (image/video/tts abstraction: deterministic + real-local Pillow/say adapters), `workflows.py` (Studio strategies), `agents.py` (Studio roles → M10 registry), `budget.py`, `publishing.py` (approval-gated, dry-run), `bridge.py` (Chat→Studio), `api.py`, `cli.py`.

## Risks identified

- **Disk exhaustion** (user has hit this before) → disk preflight is a HARD gate before any generation; quotas + checksum dedup + abandoned-job cleanup are core, not optional.
- **Shell injection via FFmpeg** → arguments built as a list, never a shell string; a security test proves injection attempts fail.
- **Path traversal** in asset upload / storage URIs → every path is resolved and confined under the project workspace; a security test proves `../` escapes are rejected.
- **Fabricated media/receipts** → a provider job is incomplete until its output file exists + checksums; publishing without a verified receipt is impossible.

## Honesty commitment

Final report will label every path: implemented · tested-locally · tested-with-real-provider (ffmpeg/PIL/say only) · not-configured (cloud gen/publishing) · not-verified (live browser render/publish) · blocked-by-environment. Cloud media generation and real publishing are NOT production-verifiable here and will be reported as such.
