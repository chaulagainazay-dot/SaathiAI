# M36 — Response Minimization

Store only: HTTP status class, schema-valid, account fingerprint match, scope
classification, size/latency buckets, content-type match, TLS/DNS results, call
counts, safe result classification.

Discard: raw response bodies, personal email, name, avatar URL, login, biography.
Raw body is held in memory only for schema validation, then discarded.
