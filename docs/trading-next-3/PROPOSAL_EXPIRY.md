# PROPOSAL_EXPIRY

- created_at + default_ttl_seconds (86400)
- valid_until / expires_at on proposal
- validate_proposal → EXPIRED if now > expires_at
- Expired cannot proceed to approval handoff

