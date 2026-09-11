# STT_BENCHMARK_RESULTS

**Host:** Apple M2, 8 GB, macOS 26.5  
**Engine family:** faster-whisper 1.2.1 (CTranslate2 int8, CPU)  
**Corpus:** 31 locally generated TTS utterances (`tools/voice-stt-bench/corpus`)  
**Nepali gate (locked pre-measurement):** intent≥0.60, first-span≥0.50, CER≤0.45, terms≥0.40

## Candidates benchmarked

| Candidate | Cold load | Peak RSS | Decode p50 | Decode p95 | Worst | NE gate |
| --- | --- | --- | --- | --- | --- | --- |
| faster-whisper-tiny | 1.01 s | 470 MiB | 0.17 s | 0.89 s | 5.56 s | **FAIL** |
| faster-whisper-base | 0.59 s | 830 MiB | 0.33 s | 1.56 s | 6.36 s | **FAIL** |
| faster-whisper-small | 1.10 s | 1430 MiB | 1.13 s | 2.10 s | 18.5 s | **FAIL** |

whisper.cpp: not installed this run (Homebrew optional deferred to avoid system-wide churn after faster-whisper already provided Whisper family measurements).  
WhisperKit: not integrated (Swift isolation).  
Moonshine / sherpa-onnx: **not primary-benchmarked** (language profile fails SaathiOS NE requirement).  
Browser SpeechRecognition: compatibility baseline (live owner path; privacy PLATFORM_MANAGED_UNKNOWN).

## Raw result files

- `tools/voice-stt-bench/results/faster-whisper-tiny.json`
- `tools/voice-stt-bench/results/faster-whisper-base.json`
- `tools/voice-stt-bench/results/faster-whisper-small.json`
- `tools/voice-stt-bench/results/summary_all.json`

## Verdict input

All local models fail locked Nepali acceptance gate on this corpus.

