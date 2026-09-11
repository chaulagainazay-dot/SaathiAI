# PRODUCT_SCORING_MATRIX

Weights: accuracy + privacy > convenience.

| Dimension | Whisper CS Small | Omni CTC 300M | Browser |
| --- | --- | --- | --- |
| English | **strong** | fail | unknown/live |
| Nepali | near-miss | fail | unknown |
| Mixed | near-miss | fail | unknown |
| Numeric | weak | fail | unknown |
| Owner accent | pending quality | fail | n/a |
| Latency | medium | medium | low |
| RAM | ~1.4 GiB | ~1.6 GiB | negligible |
| Privacy | LOCAL_CONFIRMED | LOCAL_CONFIRMED | PLATFORM_MANAGED_UNKNOWN |
| License | obligations/unclear data | Apache + CC-BY corpus | platform |
| Integration | existing CT2 path | fairseq2 heavy | already integrated |
| Streaming | pseudo | offline batch | true partials |

**Score winner local:** Whisper CS Small  
**Product primary:** Browser (until a local candidate clears all gates)

