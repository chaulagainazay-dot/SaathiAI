# SaathiOS — NEPSE Disclosure Document Ingestion

**Builds on `123382ea`.** Ingests the official document URLs already captured by V3 into
the EXISTING evidence/research pipeline: governed fetch → MIME+signature → SHA-256 →
safe PDF text extraction → structured facts → document evidence with two-level provenance.
No second document system. **Browser Use = DEFER** (not invoked).

## Existing-capability audit (Phase 1)
- `pypdf` — SaathiOS's established PDF lib (`docs.py`, `tools/files.py` lazy-import it, even print `pip install pypdf`). **REUSE** (installed into venv; added to `requirements.txt`).
- `saathi/evidence/*` — universal evidence store. **REUSE** (document rows, department `browser_research`, project `nepse_document`).
- `saathi/browser/policy` — domain/SSRF/redirect/injection. **REUSE**.
- `saathi/browser_research/{bs_date,records,extractors,nepse_endpoint}` — dates/records/symbol index. **REUSE**.
- No prior document-ingestion contract → **built** (narrow, additive).

## New modules (additive)
- `documents.py` — `DocumentIngestionRequest/Result`, `DocumentStatus` (10 typed states), `governed_fetch` (manual redirect revalidation, SSRF/private-IP/metadata/scheme block, size cap, timeout), `_validate_type` (MIME + `%PDF-` signature; extension never trusted), `_extract_pdf` (lazy pypdf; encrypted/malformed detection; page cap; **no JS execution**), `_structured_from_text`, `ingest_document` (+ SHA-256, dedup/change detection, evidence write), `browser_document_fetcher` (bytes captured in-session).
- `endpoint_monitor.py` — `validate_schema` (notice/disclosure/security fields) + `health_from_capture` (AVAILABLE/DEGRADED/SCHEMA_CHANGED/TOKEN_FLOW_CHANGED/UNAVAILABLE).
- `nepse_capture.py` (extended) — optional in-session document byte capture; `nepse_v3.py` (extended) — bounded document ingestion + endpoint health wired into the mission.

## Governance & safety
Approved-domain only, redirect revalidation, `file://`/`data://`/`javascript:`/localhost/
private-IP/metadata all rejected. MIME **and** `%PDF-` signature required (fake `.pdf`
rejected). pypdf never executes embedded JS/attachments/launch actions. Document text is DATA:
prompt-injection markers recorded, never authority. Bounds (8 GB): `MAX_DOCUMENT_BYTES=15MB`,
`MAX_PAGES=60`, `MAX_DOCUMENTS_PER_MISSION=8`, `DOCUMENT_TIMEOUT=30s`. Typed degraded on every
failure; no crash.

## Provenance & identity
Two levels preserved: parent web fact (`parent_fact_ref`) + official document (URL, SHA-256,
tier, retrieval time). Document identity = **SHA-256** (not filename). Same URL, new SHA →
`DOCUMENT_CHANGED` (old evidence retained). Same SHA → `duplicate` flagged. Provenance stays
`BROWSER_DERIVED` / `WEB_INTELLIGENCE`; a document never becomes canonical market_data.

## Reconciliation
Existing arbitration unchanged: an official TIER_1 document (`OFFICIAL_CONFIRMS`) outranks
reputable news for an event fact (tested: official 10% beats news 12%); canonical market-data
price remains authoritative for price.

## Live validation (Phase 30) — real official PDFs
| Document | Status | Pages | Text | Facts | Evidence |
|---|---|---|---|---|---|
| NRB Monetary Policy 2083/84 | DOCUMENT_OK | 4 | 8205 ch | 1 | ✓ |
| NRB FX crypto notice | DOCUMENT_OK | 1 | 1691 ch | 1 | ✓ |
| SEBON notice PDF | DOCUMENT_OK | 6 | 8272 ch | 13 | ✓ |
Re-ingest same URL → `duplicate=true` (SHA dedup). **Peak RSS 63.8 MB, 3.0 s**, 4 evidence rows.

## Key limitation — NEPSE-hosted attachment files
NEPSE's own document host (`/api/nots/notice/file/…`) is token-gated exactly like its JSON
endpoints: **401 to a plain client AND to an in-session `context.request`** (the token is a
per-request header the Angular app computes in JS, not a cookie). Retrieving those specific
files would require replaying that token — a bot-control bypass we do **not** perform. So NEPSE
API-hosted attachments return `DOCUMENT_NOT_FOUND`; ingestion works for **all non-token-gated
official documents** (NRB, SEBON, issuer sites — proven live). This is why the verdict carries
a limitation.

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, canonical market_data
writes = 0, payments/withdrawals = 0. `documents.py`/`endpoint_monitor.py`/`nepse_capture.py`/
`nepse_v3.py` import none of them (grep + test). Read-only, evidence-only.

## Tests
`tests/test_document_ingestion_v1.py` **35 tests** (110 total across the suite) with real PDF
fixtures (normal/multipage/empty/encrypted/embedded-JS): fetch governance (off-domain/localhost/
private-IP/data:/file: blocked), MIME+signature, fake-`.pdf`, max-size, timeout, SHA-256,
duplicate, changed-hash, multipage, empty, malformed, encrypted, embedded-JS-safe, prompt-
injection-as-data, BS/AD dates, structured facts, evidence + parent linkage, official-doc
reconciliation, endpoint schema/drift/health, resource bounds, no-authority imports.

## Resource / cleanup
Document fetch is in-memory bytes (no temp files); pypdf reader released after parse; browser
capture tears down (0 orphan `headless_shell` verified). Peak RSS 63.8 MB (public-PDF path),
~39 MB (capture path).

## Verdict
Fetch/MIME/signature/hash/PDF-parse/provenance/dedup/change/endpoint-health/evidence/
reconciliation all work and are live-proven on real official documents. NEPSE's own attachment
host is token-gated (out of scope to bypass), so:

**SAATHIOS_NEPSE_DISCLOSURE_DOCUMENT_INGESTION_CERTIFIED_WITH_LIMITATIONS.**

## Next milestone (do NOT auto-start)
`M — RESEARCH_INTELLIGENCE_SURFACE`: unify NEPSE web-intelligence + ingested documents into the
Central Command research view + reconciliation-backed daily brief (still read-only,
WEB_INTELLIGENCE). Browser-use stays DEFER.
