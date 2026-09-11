# ROUTING_COST_BENEFIT_ANALYSIS (analysis only — not implemented)

## Observation

No single model passes EN+NE+MIX locked gates.

Best single model: **bijay-small-ne-en** — EN OK, NE 0.57 (miss), MIX 0.52 (miss).

## Would routing help?

| Approach | Pros | Cons |
| --- | --- | --- |
| Single CS model (current best) | Simple; one mic path | Not gate-passing yet |
| Lang ID → EN generic base / NE specialized | May lift pure NE + pure EN | **Hurts mid-utterance code-switch**; 2× models RAM; switch latency |
| Always dual decode + pick | Higher quality potential | 2× compute; arbitration complexity |

## Recommendation

**Do not implement routing yet.** Gap to gate is ~0.03–0.08 intent on NE/MIX — more likely solved by:

1. better CS fine-tune / more mixed training data (product-clean license)
2. owner real-speech fine-tune loop
3. not by routing, which is weakest exactly where SaathiOS needs strength (intra-utterance switch)

If after owner data + next CS model still fails MIX while pure NE/EN pass, revisit routing.

