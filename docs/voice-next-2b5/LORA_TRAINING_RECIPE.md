# LORA_TRAINING_RECIPE

## Base model

```text
openai/whisper-small
```

Optionally warm-start from Bijay13 NE–EN checkpoint **only if** license/provenance of that fine-tune is cleared for product use. Default product path: **openai/whisper-small** + product-clean data.

## LoRA config (evidence-based defaults)

| Hyperparameter | Value | Rationale |
| --- | --- | --- |
| target_modules | `q_proj`, `v_proj` | standard Whisper PEFT |
| r | **32** | common Whisper-small optimum band |
| lora_alpha | **64** | alpha ≈ 2r |
| lora_dropout | **0.05** | HF recipes |
| bias | none | PEFT default |
| task_type | SEQ_2_SEQ_LM | Whisper |

## Optimization

| Hyperparameter | Value |
| --- | --- |
| lr | 1e-4 (cosine, warmup 0.03) |
| epochs | 2–5 with early stop |
| batch | 4–8 |
| grad_accum | to effective 32 |
| precision | fp16/bf16 on GPU |
| seed | 42 (recorded) |

## Sampling balance (targets)

```text
NE mono: 30%
EN mono: 25%
code-switch: 30%
numeric-heavy: 15%
```

## Stop rules

See TRAINING_AUTHORIZATION_GATE.md / stop section.

## Output artifacts

```text
adapter_config.json
adapter_model.safetensors
training_log.json
merged_optional/  (only if merge step run)
```

