# M16 Data Model (NO new store)
Cell{value, source, status(ok|degraded|unavailable), observed_at, degraded_reason,
age_sec}. Overview composes guarded cells from canonical subsystems. Search
results {entity_type,title,summary,source,timestamp,link,relevance} owner-scoped.
ActionDescriptor{action_id,subsystem,operation,action_class,canonical_api,risk,
requires_approval,...}. Control Center holds NO source of truth.
