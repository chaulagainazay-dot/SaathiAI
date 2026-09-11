# RESOURCE_REPORT

| Engine | cold load | peak RSS | decode p50 |
| --- | --- | --- | --- |
| Whisper CS Small | ~0.19 s | ~1433 MiB | ~2.14 s |
| Omni CTC 300M | 1.2820656659969245 | 1623.75 | 3.7083439999987604 |

Omni disk download ~1.21 GiB + tokenizer. Fits on host but **heavier** and **less accurate** than Whisper CS.

