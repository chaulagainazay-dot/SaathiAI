# SPECIALIZED_NEPALI_BENCHMARK

## Locked gate (unchanged)

```text
intent >= 0.60
first-span >= 0.50
CER <= 0.45
```

Gate uses **RAW** metrics only.

## Corpus

Exact V-NEXT-2B.1 locked corpus (31 TTS items). Utterances not modified.

## Results summary

| Candidate | NE+MIX intent | NE+MIX CER | Gate |
| --- | --- | --- | --- |
| Dragneel small CT2 | **0.154** | **0.763** | **FAIL** |
| sparshrestha small CT2 | **0.154** | **0.747** | **FAIL** |
| devrahul small CT2 | error | — | FAIL (runtime) |

### Dragneel by language (RAW)

| Lang | intent | CER | WER |
| --- | --- | --- | --- |
| en | 0.94 | 0.03 | 0.18 |
| ne | 0.29 | 0.57 | 0.64 |
| mixed | **0.00** | 0.98 | 1.00 |

### vs generic small (2B.1 historical)

| | Generic small NE intent | Specialized Dragneel NE intent |
| --- | --- | --- |
| pure NE | 0.00 | 0.29 (better, still << 0.60) |
| mixed | 0.50 | 0.00 (worse under forced `ne`) |

Specialization helps pure NE slightly vs generic base/small but **does not pass gate**. Forced Nepali language mode collapses mixed EN/NE financial code-switch.

## Result files

`tools/voice-stt-bench/results/v-next-2b2/*.json`

