# OMNILINGUAL_ASR_RESEARCH

**Primary sources:**  
- https://github.com/facebookresearch/omnilingual-asr  
- https://huggingface.co/facebook/omniASR-CTC-300M  
- Meta blog / paper (Omnilingual ASR, 2025)

## Architecture

| Family | Role |
| --- | --- |
| W2V (SSL) | Self-supervised encoder only |
| **CTC** | ASR via CTC head (batch offline; ~40s max clip) |
| LLM-ASR | Encoder + language-conditioned decoder (heavier) |

Languages use tags like `eng_Latn`, `nep_Deva` (verified in `lang_ids.py`: **`nep_Deva`** present; also `hne_Deva`).

## Target candidate

| Field | Value |
| --- | --- |
| Card | `omniASR_CTC_300M` / HF `facebook/omniASR-CTC-300M` |
| Params | ~325M |
| Download | **1.3 GiB** FP32 `.pt` |
| Official inference mem | **~2 GiB** (A100 BF16 ref; host may differ) |
| RTF (official A100) | ~0.001 (very fast on GPU) |
| Audio limit | **&lt; 40 seconds** per clip for CTC suite |
| Runtime | fairseq2 + PyTorch (`omnilingual-asr` package) |
| Mac | Reference pipeline “works across platforms”; audio needs **libsndfile** |
| Streaming | CTC family is primarily **offline batch**; not true product streaming STT |
| Language conditioning | Stronger on LLM-ASR; CTC uses language id where pipeline supports it |

## Host fit (8 GB Apple Silicon) — estimate

| Concern | Assessment |
| --- | --- |
| Peak ~2 GiB vs Whisper CS Small ~1.4 GiB | Heavier than champion |
| Coexist browser+backend+Ollama | **Tight** — one model at a time; no concurrent heavy LLM |
| 1B/3B/7B | **REJECT** for this host |
| LLM-ASR 300M | ~5–6 GiB — **REJECT** default |

## License (models/code)

Apache-2.0 for code and model weights (official).

Corpus `facebook/omnilingual-asr-corpus`: **CC-BY-4.0**.

## Security

Checkpoint format on HF: **`omniASR-CTC-300M.pt`** (PyTorch pickle) — **not safetensors**. Supply-chain limitation recorded.

## Nepali verification

Programmatic language list includes **`nep_Deva`**. Devanagari script support claimed for under-served languages including Devanagari systems.
