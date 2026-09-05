# WHISPER_VS_OMNI_BENCHMARK

## Contenders

| A | B |
| --- | --- |
| Bijay13 Whisper Small NE–EN v3.1 (2B.3 historical) | Meta omniASR-CTC-300M |

## Head-to-head (intent rates)

| Axis | Whisper CS Small | Omni CTC 300M |
| --- | --- | --- |
| English | **0.8** | 0.03333333333333333 |
| Nepali | **0.5714285714285714** | 0.0 |
| Mixed | **0.5217391304347826** | 0.06666666666666667 |
| Numeric fidelity | **0.3976190476190476** | 0.0 |
| Peak RSS MiB | 1433.46875 | 1623.75 |

## Winner

**Whisper CS Small** remains the best local candidate. Omnilingual does **not** beat it on SaathiOS workload.

## Omni failure modes observed

- English → wrong script / empty / Arabic-script collapse
- Nepali → wrong script mixtures, low intent
- Mixed → transliteration garbage
- Numbers → nearly total loss

