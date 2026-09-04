# OWNER_DATA_POLICY

## Location

```text
~/.saathi/stt-owner-corpus/
```

Raw audio **never** committed to Git.

## Sub-buckets

| Sub-bucket | Use |
| --- | --- |
| OWNER_EVAL | Locked personal holdout for accent tests |
| OWNER_PERSONALIZATION | Optional future personal LoRA only |
| OWNER_PRODUCT_DEDICATED | Only if owner **explicitly** consents for product training |

## Default

All current owner recordings:

```text
OWNER_PRIVATE
```

Do **not** silently fold into GENERAL_PRODUCT_ADAPTER training.

## Architecture preference

```text
GENERAL_PRODUCT_ADAPTER
  + optional OWNER_PERSONAL_ADAPTER
```

Avoid overfitting a universal product model to one speaker.

