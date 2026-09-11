# STT_INSTALL_PLAN — V-NEXT-2B.1

## Host budget

| Resource | Value |
| --- | --- |
| Machine | Apple M2, 8 GB |
| Approx reclaimable (at planning) | ~2.3 GiB |
| Ollama process | Running (`ollama serve`) — models not all loaded |
| Disk free | ~63 GiB |
| Existing HF cache | faster-whisper tiny/base/small already present |

## Safety rules

1. Do not lower Ollama / local-LLM memory admission gates.
2. Prefer isolated venv under `tools/voice-stt-bench/.venv`.
3. Models live under `~/.saathi/stt-models` or existing HF hub cache (read-only reuse).
4. Avoid medium/large Whisper on this host.
5. No cloud STT packages or API keys.
6. Record every install action.

## Planned installs

| Item | Method | System-wide? | Status |
| --- | --- | --- | --- |
| faster-whisper + jiwer + edge-tts + soundfile | venv `tools/voice-stt-bench/.venv` | No | Planned |
| Reuse HF models tiny/base/small | HF hub cache | No (already present) | Reuse |
| whisper-cpp (optional Metal compare) | `brew install whisper-cpp` | Yes (Homebrew) | Optional; document if used |
| ggml tiny/base models | curl to `~/.saathi/stt-models` | No | If whisper-cpp installed |
| Moonshine / sherpa models | — | — | **Skipped** (language gate) |
| WhisperKit CLI | brew | Yes | **Skipped** this mission (Swift isolation) |

## Model size estimates (selected)

| Model | Disk | Runtime RAM (approx) | Decision |
| --- | --- | --- | --- |
| Whisper tiny multi | ~75 MB | ~273–350 MB | **Benchmark** |
| Whisper base multi | ~142 MB | ~388–450 MB | **Benchmark** |
| Whisper small multi | ~466 MB | ~850–1000 MB | **Benchmark if reclaimable ≥ 1.5 GiB** |
| Whisper medium+ | ≥1.5 GB | ≥2 GB | **Do not download** |

## Runtime dependency cost

| Dep | Cost |
| --- | --- |
| CTranslate2 (faster-whisper) | Already on user site-packages; venv may reinstall |
| edge-tts | Network only at corpus generation; not runtime STT |
| ffmpeg | Already installed (`/opt/homebrew/bin/ffmpeg`) |
| macOS `say` | Built-in English TTS for corpus |

## Uninstall notes

```bash
# bench venv
rm -rf tools/voice-stt-bench/.venv

# optional brew
brew uninstall whisper-cpp

# models (only if we downloaded copies)
rm -rf ~/.saathi/stt-models
# do NOT delete shared HF cache without owner consent
```

## Install log

| Timestamp | Action | Result |
| --- | --- | --- |
| 2026-08-07 | Create `tools/voice-stt-bench` + venv | OK |
| 2026-08-07 | pip faster-whisper jiwer edge-tts soundfile numpy in venv | OK |
| 2026-08-07 | Generate 31-item TTS corpus | OK |
| 2026-08-07 | Benchmark tiny/base/small via faster-whisper | OK — NE gate fail |
| 2026-08-07 | brew whisper-cpp | **Skipped** (Whisper family measured via faster-whisper; avoid extra system churn) |
| 2026-08-07 | Moonshine/sherpa install | **Skipped** language gate |
| 2026-08-07 | Research: Moonshine/sherpa skip | Language profile fail |
| 2026-08-07 | Reuse faster-whisper tiny/base/small cache | Planned primary bench path |
