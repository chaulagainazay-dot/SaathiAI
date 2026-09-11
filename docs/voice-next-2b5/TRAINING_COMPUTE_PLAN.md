# TRAINING_COMPUTE_PLAN

## Do not train on 8 GB Mac

Mac = inference/cert host only.

## GPU candidates (LoRA Whisper-small)

| GPU | VRAM | Est. wall time* | Relative cost | Verdict |
| --- | --- | --- | --- | --- |
| **T4 16GB** | 16 | 4–10 h | low | **preferred** |
| L4 24GB | 24 | 3–7 h | low–mid | OK |
| A10G 24GB | 24 | 2–5 h | mid | OK if available |
| A100 40/80 | 40+ | faster | high | **unnecessary** for first LoRA |

\*Depends on hours of audio; assume 5–20 product-clean hours + CV NE subset.

## Local activities allowed

- dataset build / QA
- config dry-run
- tiny smoke (≤1 step) if free GPU/CPU for plumbing
- adapter load tests after remote artifact returns

