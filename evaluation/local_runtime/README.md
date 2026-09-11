# Local runtime evaluation

This package is deliberately a harness, not a provider switch.

Run the already-installed Ollama model:

```bash
.venv/bin/python scripts/benchmark_local_runtime.py --model qwen2.5:1.5b
```

Run llama.cpp against the read-only Ollama GGUF path reported by
`ollama show qwen2.5:1.5b --modelfile`:

```bash
.venv/bin/python scripts/benchmark_runtime_candidate.py \
  --runtime llama.cpp --model /absolute/path/to/model-blob
```

Run the isolated MLX-LM candidate:

```bash
HF_HOME="$HOME/.local/share/saathi-eval/hf-cache" \
"$HOME/.local/share/saathi-eval/mlx-venv/bin/python" \
scripts/benchmark_runtime_candidate.py --runtime mlx-lm \
--model mlx-community/Qwen2.5-1.5B-Instruct-4bit
```

The harness checks memory pressure and swap between cases, uses at most 128
output tokens, and does not change the model router.
