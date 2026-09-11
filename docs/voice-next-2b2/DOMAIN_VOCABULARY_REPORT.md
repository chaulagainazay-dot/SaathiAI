# DOMAIN_VOCABULARY_REPORT

## Implementation

`saathi-os/lib/voice-session/domain-vocab.js`

Deterministic repairs for known mishears:

- Saathi variants (Safi/Sathy/Sophie)
- ExecutionGateway spacing
- portfolio / drawdown spacing
- approvals truncations

## Constraints

- Not LLM-based
- Does not create tool authority
- Partial transcripts remain non-executable
- **Cannot fix** near-total NE/mixed collapse (CER ~0.7–1.0)

## Effect on gate

**None** — gate uses RAW metrics without domain repair.

