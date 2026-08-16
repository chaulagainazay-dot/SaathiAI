# PRODUCT_CLEAN_CORPUS_SPEC

## Goal

Build a commercially usable Nepali–English mixed corpus for Whisper CS Small LoRA.

## Pilot targets (minimum before training authorization)

| Requirement | Minimum |
| --- | --- |
| Speakers | **5–15** (pseudonymous) |
| Product-clean mixed utterances | **≥ 500** clips |
| Numeric curriculum clips | **≥ 200** |
| Pure Nepali (product-clean) | **≥ 300** (Common Voice + new) |
| Pure English replay | **≥ 300** (license-clean) |
| Consent complete | 100% of new speakers |
| Speaker-disjoint val/test | yes |

## Categories

```text
general conversation
SaathiOS commands
English / Nepali / code-switch
finance / portfolio / risk / approvals
system control
numbers
```

## Collection methods allowed

1. Recorded with explicit commercial consent
2. Common Voice CC0 (as PRODUCT_CLEAN mono NE/EN support)
3. Studio/scripted reads under work-for-hire or product license

## Forbidden for PRODUCT_CLEAN train

- CC BY-NC datasets
- Locked V-NEXT eval audio
- Unlicensed YouTube rips
- TTS-only synthetic as primary train (eval OK)

## Status as of V-NEXT-2B.5

```text
PRODUCT_CLEAN_MIXED_SPEECH: NOT YET COLLECTED
```

