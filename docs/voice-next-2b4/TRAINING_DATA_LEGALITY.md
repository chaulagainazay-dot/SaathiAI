# TRAINING_DATA_LEGALITY

| Bucket | Examples | Use |
| --- | --- | --- |
| OWNER_OWNED_AUDIO | `~/.saathi/stt-owner-corpus/` | Eval + personal adaptation seed |
| COMMERCIAL_LICENSE_DATA | CC-BY Omnilingual corpus (with attribution); Common Voice CC0 | Product training OK with obligations |
| NON_COMMERCIAL_RESEARCH_DATA | CC BY-NC code-switch sets | Research only — **not** product training |

Do not use NC data for commercial SaathiOS weights.

Separate:

```text
OWNER_PERSONAL_MODEL
GENERAL_PRODUCT_MODEL
```

