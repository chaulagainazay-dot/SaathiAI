# ACCURACY_REPORT

## Method

- WER via jiwer on normalized text (lowercasing, punctuation strip)
- CER on space-stripped NFC Devanagari/Latin
- Intent preservation: ≥50% of content tokens (len>2) appear in hypothesis
- Term preservation: SaathiOS/finance terms listed in corpus doc
- Mixed language: report WER/CER + intent separately (do not trust WER alone)

## English

| Model | n | mean WER | mean CER | intent | first-span | terms |
| --- | --- | --- | --- | --- | --- | --- |
| tiny | 18 | 0.37 | 0.10 | 0.72 | 0.61 | 0.64 |
| base | 18 | **0.19** | **0.03** | **0.94** | 0.78 | 0.68 |
| small | 18 | 0.17 | 0.03 | 0.94 | 0.83 | 0.77 |

English is **strong** on base/small for SaathiOS command English.

## Nepali

| Model | n | mean WER | mean CER | intent | first-span | terms |
| --- | --- | --- | --- | --- | --- | --- |
| tiny | 7 | 0.96 | 0.77 | **0.14** | 0.14 | 0.43 |
| base | 7 | 1.08 | 0.85 | **0.00** | 0.14 | 0.00 |
| small | 7 | 0.92 | 0.73 | **0.00** | 0.14 | 0.00 |

Nepali fails gate on all sizes. Hypotheses often romanize, wrong script, or unrelated Devanagari.

## Mixed EN/NE

| Model | n | mean WER | mean CER | intent | first-span | terms |
| --- | --- | --- | --- | --- | --- | --- |
| tiny | 6 | 0.61 | 0.26 | 0.33 | 0.33 | 0.46 |
| base | 6 | 0.55 | 0.27 | 0.50 | 0.50 | 0.62 |
| small | 6 | 0.53 | 0.25 | 0.50 | 0.50 | 0.62 |

English tokens often preserved; Devanagari spans largely lost.

## Short / long / noise

- Short EN commands (Stop/Wait): near-perfect on base/small
- Long EN conversational: near-perfect on base/small
- Noise variants: degraded but often intent-ok on base for mission phrasing

## Caveats

1. Corpus is **TTS-generated**, not owner accent. Owner live qualification required.
2. edge-tts Nepali voice path may not match owner dialect — still, none of the models produced usable NE intent rates near the 0.60 gate.
3. Gate was **not** lowered post-hoc.

## Gate result

```text
MULTILINGUAL_LOCAL_STT_NOT_YET_QUALIFIED
```

