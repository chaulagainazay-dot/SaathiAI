# M12 Voice OS — Audit (Phase 1)

**Date:** 2026-07-11 · **Branch:** `milestone/m7-security-engine` @ `1dbc99c`

## Existing voice-related code

| Location | Role | Disposition |
|---|---|---|
| `saathi/voice.py` | Ajay's personal Mac push-to-talk assistant: local Whisper (mlx/cpu) transcription, speaker verification via embeddings, `say`/kokoro/openai/elevenlabs TTS chain, macOS-only (Right Option hotkey) | **KEEP, do not touch.** Personal desktop assistant, not the browser Chat voice interface. Different product surface. |
| `saathi/tools/voice.py` | TTS provider chain: kokoro → openai → elevenlabs → macOS `say` fallback, returns wav bytes | **REUSE the `_say` adapter** as a real, locally-testable TTS path (no keys needed). Cloud adapters (kokoro/openai/elevenlabs) require keys/binaries not present — contract-ready, untested. |
| `saathi/infrastructure/conversation/adapters/voice.py` | Adapter for the pre-M8 `ConversationEngine`/`SessionStore` | Unrelated to M8 Chat; not reused (M8 Chat already superseded that engine's role for the web UI). |
| `saathi/tools/hcg_voice.py`, `saathi/tools/mr_yeti_voice.py`, `missions/voice_director.py` | Domain-specific (cafeteria/Mr Yeti character/mission director voice content generation) | Out of scope, untouched. |

## Dependency reality (checked, not assumed)

| Library | Status |
|---|---|
| `faster_whisper` | **installed** — real local STT usable server-side |
| `mlx_whisper`, `whisper`, `piper`, `TTS`, `pyaudio` | **not installed** |
| `sounddevice`, `soundfile` | installed (Mac device I/O, not browser mic) |
| Browser `SpeechRecognition` (webkit) / `SpeechSynthesis` | native to Chrome, zero install, genuinely available client-side |

## Findings

- No prior web-based (browser mic → Chat) voice pipeline exists. M12 is new, not a rebuild.
- **Real, locally-testable paths available today:** energy-based VAD (pure math, no deps), faster_whisper local STT (installed), macOS `say` TTS (installed), browser-native SpeechRecognition/SpeechSynthesis (zero-install, client-side).
- **Not verifiable in this environment:** cloud STT/TTS (no provider keys), live microphone hardware capture in a sandboxed browser-automation session (no real getUserMedia grant available to the agent), true token-level provider streaming (chat's `llm.generate` is non-streaming — M8's SSE already chunks post-completion text, documented in M8's own report as not true streaming).
- ChatEngine (`saathi/chat/engine.py`) and Orchestrator (`saathi/agent_runtime/orchestrator.py`) already provide the only sanctioned entry points for inference/execution — voice must call `ChatEngine.send()` / `ChatEngine.start_orchestration()` and `Orchestrator.approve()`, never the gateway or providers directly.

## Proposed architecture

New package `saathi/voice_os/` (`data/voice_os.db`), separate from the legacy personal-assistant `saathi/voice.py`:
`models.py` (session/turn state machines) · `store.py` (schema) · `vad.py` (energy-based, real) ·
`stt.py` (provider abstraction: faster_whisper local adapter + deterministic test adapter + browser-passthrough) ·
`tts.py` (provider abstraction: macOS `say` adapter + deterministic test adapter + browser marker) ·
`transcript.py` (normalization/dedup/command pipeline) · `bridge.py` (ChatEngine + Orchestrator calls, approval binding) ·
`segmentation.py` (voice-friendly text rendering) · `api.py` · `cli.py`.

## Security/privacy risks identified

Raw audio must never default-persist (policy field, opt-in only); approval-by-voice must re-validate ownership + expiry through the *existing* `agent_runtime` approval store, never a shortcut; transcripts are untrusted input (same prompt-injection posture as M9/M10).

## Honesty commitment for this report

Live browser microphone capture and live cloud STT/TTS cannot be demonstrated in this sandboxed session. Every claim in the final report will state explicitly: deterministic-adapter-tested vs. real-local-adapter-tested (faster_whisper/`say`) vs. unverified (no browser mic grant, no cloud keys).
