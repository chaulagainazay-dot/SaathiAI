# M87–M94 — SaathiOS Knowledge and Grounding Runtime

Date: 2026-07-29

Terminal verdict: `KNOWLEDGE_GROUNDING_RUNTIME_COMPLETE_WITH_LIMITATIONS`

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M87 | Knowledge source model + ingestion foundation | Complete |
| M88 | Incremental index + lexical retrieval | Complete |
| M89 | Authority, freshness, tenancy, access policy | Complete |
| M90 | Grounding context + prompt-injection defenses | Complete |
| M91 | ConversationService + Yeti grounding integration | Complete |
| M92 | Citations, health, API, UI surfaces | Complete |
| M93 | Browser certification + focused regressions | Complete with limitations |
| M94 | Final Knowledge Runtime certification | Complete with limitations |

## Architecture

Central package: `saathi/platform/knowledge/`

- `KnowledgeService` — platform authority for ingest/search/ground/health/reindex
- `KnowledgeIngestionService` — allowlisted, incremental, idempotent ingestion
- `KnowledgeIndex` — SQLite lexical index (restart-safe)
- `KnowledgeRetriever` — lexical ranking with authority/freshness boosts
- `GroundingContextBuilder` + `CitationAssembler` + `GroundedAnswerPolicy`
- `KnowledgeAccessPolicy` — RBAC + tenant/workspace filters

Integration:

- `ConversationService` remains the sole conversational model path
- Grounding runs before provider generation when the query looks factual
- Stream event `grounding` + `ConversationResult.grounding` carry citations
- Frontend never queries indexes for model generation; uses `/knowledge/*` for admin and `/conversation/complete` for answers

Does **not** replace M19 `saathi.knowledge` multi-repo retrieval. Platform knowledge is the grounding runtime for Yeti/ConversationService.

## Source classes indexed

1. Autonomous Mission Runtime (`docs/autonomous/*` state files)
2. Repository documentation (roadmap, capability, Brain, Business, AGENTS — bounded)
3. Evidence / certification summaries under approved `docs/evidence/*` packs
4. Platform records (production policy, voice certification, domain notes)
5. Application domain docs (voice, IELTS/HCG guidance notes)

Never indexed: secrets, credentials, design-spec, node_modules, .git, caches, model weights, raw audio, private identity docs.

## Authority hierarchy

`AUTHORITATIVE_RUNTIME` > `AUTHORITATIVE_EVIDENCE` > `AUTHORITATIVE_PLATFORM_RECORD` >
`AUTHORITATIVE_DOCUMENTATION` > `DERIVED_SUMMARY` > `USER_PROVIDED_CONTEXT` >
`MODEL_PRIOR` > `UNVERIFIED`

## Retrieval

- Mode: **lexical only** (no embeddings, no auto model download)
- Semantic: not implemented (`semantic_available: false`)
- Ranking: token coverage + title/path + authority + freshness + query-intent boosts
- Bounds: top-k ≤ 12, context ≤ 4500 chars, file ≤ 512KB, total chunks ≤ 8000

## Security

- Path traversal / symlink escape blocked
- Secret path and content denial
- Prompt-injection flags + untrusted evidence boundaries
- Indexed text cannot override RBAC / Approval / ExecutionGateway / Trading Guardian
- No absolute paths in public citations
- No public listeners; no paid providers

## Permissions

- `knowledge.read`, `knowledge.search` — viewer+
- `knowledge.ingest` — operator+
- `knowledge.reindex`, `knowledge.admin` — owner+

## UI

- `/knowledge/grounding` — health, reindex (authorized), grounded Q&A (does not replace the existing knowledge graph page)
- `GroundedAnswer` — grounded badge, sources expand, freshness, conflicts, no-evidence

## Evidence

- Focused tests: `tests/test_m87_knowledge_grounding.py`
- Browser: `docs/evidence/m93/browser/M93_BROWSER_CERT.json`
- Certification summary: `docs/evidence/m94/M94_CERTIFICATION_SUMMARY.json`

## Limitations

- Lexical-only retrieval (no semantic embeddings)
- Single-host SQLite index
- English-primary UI
- Local repository/platform sources only
- Browser live Next→API dual-stack wiring is harness-sensitive; cert proves API journey + panel UI with ConversationService-certified payloads
- Production not authorized

## Production

Not authorized. No push, merge, deploy, credentials, DNS, paid-provider, or Trading Guardian change.
