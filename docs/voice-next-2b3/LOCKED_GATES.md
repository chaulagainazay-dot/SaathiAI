# LOCKED_GATES — V-NEXT-2B.3 (defined before candidate results)

**Date locked:** 2026-08-07  
**Do not lower post-hoc.**

## Preserved from V-NEXT-2B.1 / 2B.2 (pure Nepali / NE+MIX historical)

| Metric | Threshold |
| --- | --- |
| Nepali intent preservation | ≥ **0.60** |
| First-span preservation | ≥ **0.50** |
| CER (Nepali) | ≤ **0.45** |

## Mixed-language gates (NEW — locked before benchmarks)

| Metric | Threshold | Rationale |
| --- | --- | --- |
| Mixed intent preservation | ≥ **0.60** | Same bar as product command usability for pure NE |
| Mixed first-span preservation | ≥ **0.50** | Align with pure-NE first-span |
| Mixed financial-term preservation | ≥ **0.50** | Half of target finance/SaathiOS terms must survive |
| Mixed CER | ≤ **0.50** | Slightly above pure-NE CER 0.45 for code-switch orthography; still hard |

## Universal primary additional requirements

To become **UNIVERSAL_PRIMARY_QUALIFIED** / product primary, also require:

| Metric | Threshold |
| --- | --- |
| English intent (locked EN corpus) | ≥ **0.70** |
| Numeric fidelity (special numeric set) | ≥ **0.70** exact number preservation |
| Peak RSS | ≤ **1500 MiB** on 8 GB host under idle Ollama |
| License | PRODUCT_ELIGIBLE or PRODUCT_ELIGIBLE_WITH_OBLIGATIONS |
| Privacy | LOCAL_CONFIRMED when used as local engine |

## Gate metric basis

```text
RAW metrics only
```

Normalized/domain-vocab metrics are reporting-only and never flip a FAIL to PASS.
