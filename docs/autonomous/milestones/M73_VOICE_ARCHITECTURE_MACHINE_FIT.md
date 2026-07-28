# M73 — Voice Architecture and Machine-Fit Audit

Status: complete pending checkpoint commit.

## Scope completed

- Recovered the branch without resetting completed M69–M72 work.
- Inventoried legacy voice/audio/media/Yeti/STT/TTS code and platform authorities.
- Measured target hardware, disk, Python/Torch/package and native speech posture.
- Reviewed upstream VoxCPM models, language/VRAM/size/licensing/MPS/GGUF evidence.
- Selected adapter-first architecture with certified macOS TTS first.
- Kept VoxCPM uninstalled and cloning disabled.

## Evidence

- `docs/autonomous/VOICE_INITIAL_AUDIT.md`
- `docs/autonomous/VOICE_BACKEND_DECISION.md`
- Git and machine observations recorded in those documents.

## Safety gates

- No package or model installation.
- No model download.
- No production, public listener, paid call, push, merge, deploy or PR.
- No `docs/design-spec/` modification or staging.

