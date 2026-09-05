# RESOURCE_REPORT

| Model | cold_s | peak_RSS_MiB | p50 decode_s |
| --- | --- | --- | --- |
| tiny | 0.07320154100000309 | 1433.46875 | 0.3184035829999914 |
| base | 0.10618845899999974 | 859.40625 | 0.6394696249999967 |
| small | 0.19496891600000055 | 1433.46875 | 2.1400577919999932 |

RSS budget 1500 MiB: all under (tiny peak after sequential runs elevated). LLM gates not lowered.

