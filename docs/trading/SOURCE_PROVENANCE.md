# M62.3 — Source Provenance

Every `ResearchSource` preserves: identity, source_type, locator (NOT a fetchable
proxy), title/publisher/author, published/retrieved/effective timestamps, content
hash (sha256), trust class, quality state, prompt-injection state, findings, tenant
scope, and parent project. Source text and model interpretation are distinct objects;
source identity is immutable even when extracted claims are revised. Source content is
never fetched from a URL by the platform (locator is a reference, not a proxy target).

Trust classes: PRIMARY_AUTHORITY … REJECTED — trust never auto-determines truth (a
high-trust source may be stale/incomplete/superseded/contradicted).
Quality findings: VALID/STALE/INCOMPLETE/MISSING_DATE/DUPLICATE/SUPERSEDED/
PROMPT_INJECTION_SUSPECTED/MALFORMED/REJECTED (+ more).
