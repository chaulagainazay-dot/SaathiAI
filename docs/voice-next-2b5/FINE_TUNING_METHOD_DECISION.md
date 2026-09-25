# FINE_TUNING_METHOD_DECISION

## Contenders

| Method | Trainable params | VRAM (Whisper-small est.) | Adapter size | Forgetting risk | CT2 path |
| --- | --- | --- | --- | --- | --- |
| Full fine-tune | ~244M | high (16–24 GB+ FP16) | full merge | high | merge always |
| **LoRA (PEFT)** | ~0.5–2% | **low–mid (T4 16GB OK)** | MBs | medium–low | merge then convert |
| AdaLoRA | similar to LoRA | similar | MBs | medium | same |
| Prompt/prefix tuning | tiny | low | tiny | can underfit ASR | awkward for Whisper ASR |

## Evidence basis

Community Whisper + PEFT practice typically targets attention projections:

```text
q_proj, v_proj
```

with `r=16–32`, `lora_alpha=32–64`, dropout ~0.05 (e.g. HF PEFT Whisper recipes).

## Decision

```text
SELECTED: LoRA / PEFT
```

### Why

1. Mac is **inference** target only — training must be remote/cheap.
2. Full FT costs more, forgets English more easily.
3. Adapter checkpoint is small, auditable, and versionable.
4. Deployment path: merge → CTranslate2 → faster-whisper (proven family for SaathiOS).

### AdaLoRA

**DEFER** — more moving parts; start with classic LoRA.

### Full FT

**REJECT** as first strategy on cost/forgetting grounds.

