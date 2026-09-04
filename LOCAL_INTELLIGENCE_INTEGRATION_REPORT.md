# Local Intelligence Integration Report

## Executive verdict

`LOCAL_AGENT_STACK_BENCHMARKED_NOT_ACTIVATED`

The bounded local/provider/evaluation/provenance architecture is integrated,
but neither MLX-LM, llama.cpp, nor Kimi replaces an active provider. Ollama
remains the default. Kimi is default-off and was contract-tested only because
no authorized credential was available.

## Environment

- Audit time: 2026-07-31, Asia/Kathmandu.
- macOS 26.5.1 (25F80), arm64 Apple M2, 8,589,934,592 bytes unified memory.
- Data volume after installation: 228 GiB total, 110 GiB used, 91 GiB
  available.
- Homebrew 6.0.13; system Python 3.9.6; repository Python 3.12.13; Node
  26.4.0; Git 2.54.0; Ollama 0.32.5; OpenCode 1.18.8.
- Existing Ollama models were preserved: `gemma4:e2b` 7.2 GB, `qwen3:8b`
  5.2 GB, and `qwen2.5:1.5b` 986 MB.
- Existing live processes were preserved: `python -m saathi.server`, two
  pre-existing Ollama serve processes, and browser applications.

Repository evidence selected `/Users/macbookpro/SaathiAI`: its Git remote,
package metadata, roadmap, recent milestone commits, ExecutionGateway,
mission/checkpoint runtime, provider router, approval, permission, event,
audit, memory, Baadar/publication, and IELTSAlert packages all identify it as
the active platform. `/Users/macbookpro/Saathi` was not a Git repository.

## Candidates and installations

The complete candidate/licence/platform audit is
`docs/research/LOCAL_RUNTIME_CANDIDATE_AUDIT.md`.

Installed:

- Homebrew `llama.cpp` 10180 with `ggml` 0.18.0 and `libomp` 22.1.8.
- Isolated MLX environment containing MLX-LM 0.31.3 and MLX 0.32.0.
- Verified MLX Qwen2.5-1.5B-Instruct 4-bit model in an isolated 840 MiB cache.

Rejected/deferred:

- OpenJarvis full stack: duplicates SaathiOS execution, agent, memory,
  scheduling, routing, and audit architecture.
- ColBench/SWEET-RL runtime: large-model/vLLM/NVIDIA-oriented.
- AgencyBench/ALE-Bench/AgentBench/OdysseyBench frameworks: concepts retained,
  heavyweight infrastructure not imported.
- Kimi weights: remote-only for this Mac; none downloaded.
- C2PA signing SDK: deferred until publication key management and a real
  authorized publication pipeline exist.

## Architecture changes

- Kimi provider adapter and descriptor added under the existing inference
  boundary. Credentials remain environment references; the exact official
  HTTPS origin is validated.
- Priority classes translate to existing `ModelRouter` labels/preferences.
  No second router or execution gateway exists.
- Existing provider policy owns default-off state, credential availability,
  kill switch, and retry ceiling. Existing durable governance/circuit-breaker
  facilities remain authoritative.
- Cloud budget policy: $20 monthly, warning $15, hard stop $19, $1 reserve,
  one parallel cloud agent, two retries, 20 tool iterations, approval for
  expensive models.
- Five deterministic workflow fixtures and collaboration review attach to
  mission results.
- Baadar’s gate requires injected existing approval and audit callbacks and
  can only approve a simulation.
- Mission Control integration is a stable read-model contract, not a UI
  redesign. It exposes runtime, model, costs, workflow/collaboration scores,
  provenance, approval, and rollback state.

## Runtime evidence

| Runtime | Model | Memory evidence | Speed | Reliability | Decision |
|---|---|---:|---:|---:|---|
| Ollama | Qwen2.5 1.5B Q4_K_M | service RSS 70→80 MB; unified allocation unavailable | 44.71 tok/s | 5/6 | keep default |
| llama.cpp | same GGUF | 1,940.83 MB peak process | 71.14 tok/s | 5/6 | benchmark only |
| MLX-LM | Qwen2.5 1.5B 4-bit | 939.31 MB MLX peak | 42.43 tok/s | 6/6 | benchmark only |

No candidate run grew swap or triggered a macOS thermal/performance warning.
The Ollama model’s unsafe memory-write answer is a material finding: local
model output cannot bypass deterministic memory/permission policy.

## Security and remaining risks

- No credential was printed, stored, or committed. Changed/new files produced
  zero strong-credential scanner hits.
- No production, payment, trading, staging, or publishing service was
  contacted.
- Kimi live correctness, latency, tool discipline, and real cost remain
  unknown.
- Current machine swap was already about 2.1 GB; simultaneous local runtimes
  or large contexts are not recommended.
- The full suite had two unrelated baseline/live-state failures: the live
  browser driver returned an empty title, and the existing release gate found
  two pre-existing `private_key_block` scanner matches in unchanged trading
  security source. New/focused and security suites passed.

## Recommended defaults

- Local runtime/model: Ollama + `qwen2.5:1.5b`.
- Coding: existing verified provider; Kimi K2.7 Code remains disabled until a
  user-approved live benchmark.
- Multimodal: existing Gemini provider when configured and approved.
- Critical expensive: Kimi K3 disabled; manual approval and budget reservation
  required if later benchmarked.
- Cloud budget: $20/month, $15 warning, $19 hard stop, $1 reserve.

## Rollback

No commit or provider activation exists. Remove only the files listed by Git
as this integration’s new/modified files; preserve the pre-existing dirty
files listed in the Git report. Disable Kimi by leaving `KIMI_API_KEY` unset or
setting `SAATHI_PROVIDER_KILL_KIMI`. Remove the isolated MLX directory to
discard its environment/model. Homebrew uninstall commands are recorded in
`MAC_SETUP_MANIFEST.md`. Do not remove Ollama or its models.
