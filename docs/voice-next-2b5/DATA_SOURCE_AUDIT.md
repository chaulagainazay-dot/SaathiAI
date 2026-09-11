# DATA_SOURCE_AUDIT

## Buckets (exactly one per item)

| Bucket | Meaning |
| --- | --- |
| PRODUCT_CLEAN | Commercial product training allowed |
| OWNER_PRIVATE | Owner-controlled; not automatic product training |
| RESEARCH_ONLY | Non-commercial / research use only |
| REJECTED | Unusable (bad quality, unclear rights, contaminated) |

## Source classification

| Source | License (verified/expected) | Bucket | Notes |
| --- | --- | --- | --- |
| Mozilla Common Voice Nepali | **CC0** (MDC / Common Voice terms) | **PRODUCT_CLEAN** | Scripted read speech; limited code-switch |
| Owner corpus `~/.saathi/stt-owner-corpus/` | Owner rights | **OWNER_PRIVATE** | Not universal product training unless dedicated |
| Public ~58h NE–EN CS v2 | **CC BY-NC 4.0** | **RESEARCH_ONLY** | Forbidden for commercial product FT |
| CS corpus earlier CC BY rev | provenance unclear / platform ToS | **LICENSE_UNCLEAR → exclude** | YouTube-extracted risk |
| Locked V-NEXT eval corpora | product internal holdout | **REJECTED for train** | Contamination policy |
| Omnilingual ASR corpus | CC-BY-4.0 | PRODUCT_CLEAN_WITH_OBLIGATIONS | Multilingual; not SaathiOS-domain CS |
| Synthetic TTS (edge-tts / say) | platform ToS | **REJECTED for product FT** | Eval-only historically |

## Product-clean mixed speech today

```text
AVAILABLE HOURS OF PRODUCT-CLEAN NATURAL CODE-SWITCH: ~0
```

Common Voice NE is monlingual/scripted-dominant. Owner is private. NC CS is research-only.

**Gap:** product-clean multi-speaker Nepali–English code-switch collection is **required** before training authorization.

