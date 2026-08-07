# M62.3 — Thesis Versioning

Each synthesize/revise creates a new immutable-on-publish thesis version (parent
version chain, author, change rationale, confidence, challenge). States: DRAFT/
CHALLENGED/REVISION_REQUIRED/REVIEW_READY/PUBLISHED/SUPERSEDED/EXPIRED/REJECTED.
Published versions cannot be mutated (store returns "immutable"); corrections require
a new version. `GET /research/projects/{id}/thesis/versions` lists the chain.
