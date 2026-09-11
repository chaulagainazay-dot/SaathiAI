# STT_CANDIDATE_RESEARCH — V-NEXT-2B.1

**Host:** Apple M2, 8 GB unified memory, macOS 26.5  
**Date:** 2026-08-07  
**Source tip:** `468a056` (PR #28 / V-NEXT-2B)  
**Scope:** Local/private multilingual STT for SaathiOS (English + Nepali + mixed). No streaming TTS. No wake word.

## Pre-set Nepali acceptance gate (Phase 17 — locked before measurement)

A primary local STT engine **must not** qualify on English alone.

| Metric (short Nepali + mixed commands) | Gate |
| --- | --- |
| Command **intent preservation** | ≥ 60% of utterances |
| First content word / Devanagari span preservation | ≥ 50% |
| CER (character error, Devanagari-normalized) | ≤ 0.45 on short commands |
| Financial / SaathiOS proper-noun preservation (mixed) | ≥ 40% of target terms |

If no local engine meets these: return `MULTILINGUAL_LOCAL_STT_NOT_YET_QUALIFIED` and retain browser STT honestly.

---

## Classification key

| Label | Meaning |
| --- | --- |
| **KEEP** | Remain in architecture as-is |
| **ADAPT** | Use design ideas / partial integration |
| **INTEGRATE** | Production path for this milestone |
| **COMBINE** | Use with another component |
| **DEFER** | Valuable later; not now |
| **REPLACE** | Supersedes an existing piece |
| **REJECT** | Do not use for SaathiOS primary STT |

---

## Candidate matrix

### 1. whisper.cpp (ggml-org)

| Dimension | Assessment |
| --- | --- |
| Version (research) | Homebrew formula 1.9.1 (2026); upstream ggml-org/whisper.cpp actively maintained |
| Architecture | C/C++ Whisper port; Metal + optional Core ML encoder on Apple Silicon |
| Streaming | Pseudo-streaming / chunked (not native low-latency token stream like transducers) |
| Partials | Achievable via rolling window re-decode |
| Endpointing | External (VAD + silence) — fits SaathiOS TurnCoordinator |
| English | Strong even at tiny/base |
| Nepali | Multilingual models include `ne`; quality scales with size (tiny weak, base/small better) |
| EN/NE code-switch | Partial; often collapses to one script without language hints |
| Apple Silicon | First-class (Metal, Accelerate, optional Core ML) |
| CPU / GPU / ANE | Metal GPU; Core ML → ANE for encoder when built |
| RAM (est.) | tiny ~273 MB, base ~388 MB, small ~852 MB, medium ~2.1 GB |
| Disk | tiny 75 MiB, base 142 MiB, small 466 MiB |
| Cold / warm start | Cold model load hundreds of ms–seconds; warm decode fast on M2 |
| Privacy | **LOCAL_CONFIRMED** when run on-device with no network |
| Licensing | MIT |
| Maintenance | Excellent |
| Integration | CLI or library behind StreamingTranscriptionAdapter; no second mic |
| Cancellation | Process kill / stop decode |
| Pre-roll | Full PCM ingest (critical SaathiOS win vs browser) |
| 8 GB fit | tiny + base safe; small conditional; medium risky with Ollama |

**Classification: INTEGRATE** (if benchmarks pass Nepali gate) else **ADAPT** (benchmark harness retained).

---

### 2. WhisperKit / Core ML Whisper (Argmax)

| Dimension | Assessment |
| --- | --- |
| Architecture | Swift + Core ML / ANE-optimized Whisper |
| Streaming | Chunked / streaming APIs evolving; Apple-native |
| EN / NE | Same Whisper multilingual coverage |
| Apple Silicon | Best-in-class ANE path |
| RAM | Competitive with whisper.cpp; model-dependent |
| Integration | Swift helper/service required; must stay behind adapter |
| Privacy | LOCAL_CONFIRMED when on-device |
| Licensing | Typically MIT/Apache for open components |
| 8 GB | Viable for small models |

**Classification: DEFER / ADAPT** — do not redesign SaathiOS around Swift. Revisit if whisper.cpp latency or power is insufficient after INTEGRATE attempt.

---

### 3. Moonshine (Useful Sensors / sherpa-onnx packaging)

| Dimension | Assessment |
| --- | --- |
| Streaming | True streaming design strength |
| English | Excellent, often beats Whisper tiny/small on EN |
| Nepali | **Not supported** as primary multilingual (v1 EN; v2 limited set without Nepali) |
| RAM | Very small footprint |
| Privacy | LOCAL_CONFIRMED |
| Licensing | Check model-specific (generally research-friendly) |

**Classification: REJECT** as primary SaathiOS STT (Nepali mandatory).  
**ENGLISH_OPTIMIZED_OPTION** only if dual-engine path is later authorized.

---

### 4. sherpa-onnx streaming ASR

| Dimension | Assessment |
| --- | --- |
| Streaming | True streaming transducers + VAD demos |
| Languages | Many zipformer models (EN, ZH, KO, …); Whisper ONNX also packable |
| Nepali | No first-class streaming Nepali zipformer found in current catalog; Whisper-ONNX path re-enters Whisper family |
| RAM | Often lighter than full Whisper for mono-language models |
| Integration | ONNX runtime (already on host); more surface area |
| Privacy | LOCAL_CONFIRMED |

**Classification: DEFER** for primary EN/NE. Useful later for streaming EN-only or specialized models. Not benchmarked as primary unless a verified NE model appears.

---

### 5. faster-whisper (CTranslate2)

| Dimension | Assessment |
| --- | --- |
| Architecture | Python + CTranslate2 int8 Whisper |
| Streaming | Batch / VAD segments; not true low-latency stream |
| EN / NE | Same Whisper multilingual models |
| Apple Silicon | CPU/int8; weaker than whisper.cpp Metal on M-series |
| RAM | Similar to model size + CTranslate2 overhead |
| Host status | **Already installed**; tiny/base/small models **already cached** under HF hub |
| Privacy | LOCAL_CONFIRMED offline |
| Licensing | MIT |

**Classification: INTEGRATE or COMBINE** as primary local engine if whisper.cpp install blocked; strong **benchmark baseline** on this host.

---

### 6. Browser SpeechRecognition

| Dimension | Assessment |
| --- | --- |
| Streaming | True partials (`interimResults`) |
| EN / NE | Platform-dependent; ne-NP not guaranteed |
| Privacy | **PLATFORM_MANAGED_UNKNOWN** (may leave device) |
| RAM | Negligible in-process |
| Pre-roll PCM | **Cannot ingest** — metadata only |
| Offline | Not guaranteed |

**Classification: KEEP** as compatibility fallback. Never label offline/private.

---

### 7. Apple-native speech APIs (SFSpeechRecognizer / Speech framework)

| Dimension | Assessment |
| --- | --- |
| Privacy | Often on-device for some locales; not always; class **LOCAL_WITH_SYSTEM_DEPENDENCY** or PLATFORM_MANAGED_UNKNOWN without verification |
| Web app path | Not available inside Next.js browser shell without native helper |
| Nepali | Limited |

**Classification: DEFER** (native helper only if Whisper path fails).

---

### 8. Other materially stronger local projects (2026 scan)

| Project | Notes | Class |
| --- | --- | --- |
| NVIDIA Parakeet / Canary | Strong accuracy; EN-focused or limited multilingual; heavier | DEFER / REJECT for NE primary |
| Voxtral Transcribe | Strong WER; ~13 languages — not NE-first | DEFER |
| MLX Whisper | Host has `mlx-community/whisper-small-mlx` cached | ADAPT/COMBINE on Apple if measured better than faster-whisper |
| Vosk | Streaming; limited NE | DEFER |

---

## Benchmark shortlist (Phase 2–3) for 8 GB host

| ID | Candidate | Models | Est. disk | Est. RAM | Rationale |
| --- | --- | --- | --- | --- | --- |
| A1 | faster-whisper | tiny multilingual | cached | ~300 MB | Already present; safe |
| A2 | faster-whisper | base multilingual | cached | ~400 MB | Accuracy step-up |
| A3 | faster-whisper | small multilingual | cached | ~900 MB | Strongest safe-ish; admit carefully vs Ollama |
| B | whisper.cpp | tiny + base (if install succeeds) | ~220 MiB | ~300–400 MB | Metal path comparison |
| C | Moonshine / sherpa | — | — | — | Language gate fails → not primary bench |
| D | Browser STT | N/A | 0 | ~0 | Compatibility baseline (live owner path) |

**Rejected for download on this host:** Whisper medium/large (risk swap storm with 8 GB + Ollama).

---

## Architectural fit

```text
VoiceSession
     │
StreamingTranscriptionAdapter
     │
┌────┴─────────────────┬──────────────────┐
▼                      ▼                  ▼
Local Primary     Browser Fallback      Mock
(Whisper family)  (PLATFORM_UNKNOWN)   (tests)
     │
     ▼
TurnCoordinator  (engine-neutral)
```

STT remains an adapter. No ownership of permissions, ToolIntent, approval, ExecutionGateway, or Trading Guardian.

---

## Source CI note (honest)

PR #28 (`468a056`): `critical-regressions` SUCCESS; `full-suite` FAILURE on unrelated `tests/test_m17_1_live.py::test_live_browser_dom_and_click` (empty browser title). Not a voice regression. V-NEXT-2B is **not** claimed fully closed while full-suite is red.

---

## Technology verdict (research prior; refined after bench in STT_SELECTION_DECISION.md)

| Engine | Research class |
| --- | --- |
| whisper.cpp | INTEGRATE candidate |
| WhisperKit | DEFER |
| Moonshine | REJECT primary / ENGLISH_OPTIMIZED_OPTION |
| sherpa-onnx | DEFER |
| faster-whisper | INTEGRATE/COMBINE candidate |
| browser STT | KEEP fallback |
| Pipecat | re-evaluate after STT (not auto-integrate) |
| LiveKit Agents | ADAPT concepts only |
