# M38 — Security Validation

Preserves M31–M37 guarantees:

* reference-only secrets
* SecretHandle non-serializable, closed on all paths
* no Authorization headers in evidence
* leakscan on evidence writes
* authority non-escalation
* Trading Guardian unengaged
