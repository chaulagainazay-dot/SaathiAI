# Mac Setup Manifest

All installation was user-space or Homebrew-managed. No `sudo`, kernel
extension, macOS security change, or background service was created.

| Package/change | Version/source | Install command | Disk usage | Disable / uninstall |
|---|---|---|---:|---|
| llama.cpp | Homebrew 10180, official ggml-org project | `brew install llama.cpp` | 19 MB | do not call it; `brew uninstall llama.cpp` |
| ggml | Homebrew 0.18.0 dependency | installed by formula | 3.3 MB | removed when no formula depends on it; `brew autoremove` only after review |
| libomp | Homebrew 22.1.8 dependency | installed by formula | 1.7 MB | same dependency caution |
| ca-certificates | Homebrew 2026-07-16 active alongside old keg | formula update dependency | 208 KB active keg | do not remove if other formulae use it |
| openssl@3 | Homebrew 3.6.3 active alongside old keg | formula update dependency | 39 MB active keg | do not remove if other formulae use it |
| MLX benchmark venv | MLX-LM 0.31.3, MLX/MLX-Metal 0.32.0 | `/opt/homebrew/bin/python3.12 -m venv ~/.local/share/saathi-eval/mlx-venv`; then venv `pip install mlx-lm==0.31.3` | 397 MB | remove only `~/.local/share/saathi-eval/mlx-venv` |
| MLX Qwen model | `mlx-community/Qwen2.5-1.5B-Instruct-4bit`, Apache-2.0 | downloaded automatically by benchmark with isolated `HF_HOME` | 840 MB | remove only `~/.local/share/saathi-eval/hf-cache` |

Total isolated MLX evaluation footprint: approximately 1.2 GB. Homebrew
formula footprint above: approximately 63 MB for the named active kegs, not
counting shared/global Homebrew metadata. Data-volume availability changed
from roughly 93 GiB at audit to 91 GiB after tools/model/build caches.

Configuration changed:

- Repository `.env.example` gained blank `KIMI_API_KEY` and documented
  `KIMI_BASE_URL`/`KIMI_DEFAULT_MODEL` references.
- No real `.env` value was written.
- No launch agent, daemon, login item, or background service was added.
- Existing Ollama models/services and OpenCode were untouched.
