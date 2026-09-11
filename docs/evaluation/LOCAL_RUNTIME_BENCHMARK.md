# Local Runtime Benchmark

Recorded 2026-07-31 on an Apple M2 MacBook Pro with 8 GB unified memory while
the SaathiOS service and browsers remained open. The common model family was
Qwen2.5-1.5B-Instruct, 4-bit. Context and output were deliberately short.

| Runtime | Model | Peak RAM evidence | Mean speed | Contract reliability | Decision |
|---|---|---:|---:|---:|---|
| Ollama 0.32.5 | Qwen2.5 1.5B Q4_K_M | service RSS 70→80 MB; unified model allocation is not represented by RSS | 44.71 tok/s | 5/6 | keep default |
| llama.cpp b10180 | same existing GGUF | 1,940.83 MB process | 71.14 tok/s | 5/6 | benchmark only |
| MLX-LM 0.31.3 / MLX 0.32.0 | MLX Qwen2.5 1.5B 4-bit | 939.31 MB MLX peak | 42.43 tok/s | 6/6 | benchmark only |

## Findings

- Ollama failed the safety-critical memory-write prompt by recommending that
  an API key be stored. This confirms the model must never authorize memory or
  permission actions without deterministic policy.
- llama.cpp was fastest, but raw CLI usage has no SaathiOS provider,
  permission, retry, audit, or lifecycle boundary. Its speed gain does not
  justify a second serving architecture.
- MLX-LM had the best six-prompt result and lowest measured model peak, but its
  first run included a 42.8-second model download/load path. Steady generation
  was not materially faster than Ollama.
- No run added swap; macOS reported no thermal or performance warning. The
  measured machine already had about 2.1 GB swap in use, so concurrency remains
  inappropriate.
- Time-to-first-token is unavailable for the non-streaming candidate APIs.
  The Ollama adapter’s current `stream()` is a single-shot compatibility path,
  so its “first-token” metric is effectively full-response latency. This is a
  known measurement limitation, not fabricated streaming evidence.
- Installation size: llama.cpp formula 19 MB plus Homebrew dependencies;
  isolated MLX environment and model cache total 1.2 GB.

## Reproduction and guardrails

Commands are documented in `evaluation/local_runtime/README.md`. Harnesses
stop between cases below 5% macOS free-memory indication or above 1 GiB swap
growth. Output is limited to 128 tokens. Existing models are not deleted,
unloaded, or replaced.

Evidence:

- `artifacts/evaluation/local-runtime-results.json`
- `artifacts/evaluation/llama-cpp-results.json`
- `artifacts/evaluation/mlx-lm-results.json`

## Verdict

Ollama remains the active default. MLX-LM is the strongest future candidate
for a narrow provider adapter if repeated tests under sustained load preserve
its reliability and memory advantage. Both MLX-LM and llama.cpp remain
`CANDIDATE`/benchmark-only.
