# Idempotency

Proposal keys are SHA-256 fingerprints of source transaction identity, canonical instrument, and event type. Reordered exports therefore produce the same keys; repeated rows and conflicting facts are surfaced as `DUPLICATE_EXTERNAL_EVENT` or `CONFLICT`, never silently merged.
