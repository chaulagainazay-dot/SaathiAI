# M60 — Cross-Workspace Search

Route: `/platform/search`; reachable from ⌘K. Behavior:
**SEARCHING_AUTHORIZED_LOADED_RECORDS** — `searchAuthorizedRecords()` filters only
records already fetched through authorized APIs (missions, agents, approvals,
attention, executions, projects), grouped by type, with a type filter. No
unauthorized indexing, no secret-bearing snippets. Recent history is local-only. The
UI states honestly that this is not a complete server-side global search.
