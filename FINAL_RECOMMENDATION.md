# Final Recommendation

| Priority | Classification | Recommendation |
|---|---|---|
| Apple-Silicon local inference runtime | **BENCHMARKED_ONLY** | Keep Ollama/Qwen2.5 1.5B default; retain MLX-LM as candidate, llama.cpp as diagnostic candidate. |
| Long-horizon SaathiOS workflows | **INTEGRATED** | Use the five deterministic offline fixtures inside the existing mission-evaluation boundary. |
| Kimi K3 / coding provider | **BENCHMARKED_ONLY** | Keep default-off; live benchmark K2.7 Code first under approval and budget, then K3 only for critical work. |
| Human-agent collaboration metrics | **INTEGRATED** | Attach the bounded evidence-backed review to mission results; require human review for qualitative scores. |
| Baadar provenance gate | **INTEGRATED** | Require manifest, existing approval, existing audit, and simulation gate before any future publisher integration. |
| OpenJarvis full stack | **ADAPTED_AS_PATTERN** | Retain useful local-runtime concepts; do not install a duplicate control plane. |
| Heavy external benchmark frameworks / GPU training | **REJECTED** | Incompatible with local constraints or unnecessary architecture. |
| C2PA SDK signing | **DEFERRED** | Revisit only with authorized publishing and secure signing-key management. |

Safest active configuration:

- local runtime/model: Ollama + `qwen2.5:1.5b`;
- coding: existing verified coding provider; Kimi K2.7 Code disabled;
- multimodal: existing Gemini when configured and approved;
- expensive critical: Kimi K3 disabled and approval-required;
- budget: $20 monthly, $15 warning, $19 hard stop, $1 reserve;
- concurrency/retries/tools: one cloud agent, two retries, 20 tool iterations;
- all external, expensive, publishing, and state-changing actions remain under
  existing SaathiOS permission, approval, audit, checkpoint, and recovery
  controls.
