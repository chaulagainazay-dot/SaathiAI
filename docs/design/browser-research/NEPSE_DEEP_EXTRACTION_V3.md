# SaathiOS — NEPSE Deep Extraction (V3)

**Builds on `b959f00f`.** Closes the V2 gap: reliable extraction of useful public NEPSE
data from the JS-heavy official site. **No browser-use** (stays `BROWSER_USE_DEFER`). Contract,
tiers, provenance, freshness, reconciliation, evidence/confidence bridges, durable
orchestrator, and the one-browser-worker limit are unchanged.

## Root cause of the V2 0-fact result
`nepalstock.com` is an Angular SPA. The governed HTTP READ returned the pre-hydration shell
(~37 chars, no notices). Its data lives in JSON XHRs the SPA fetches after load.

## Network/XHR investigation (Phase 2–4)
Live governed Playwright inspection observed 14 public JSON endpoints (200). Research-relevant:
- `/api/web/notice/` — official NEPSE notices (`noticeHeading`, `modifiedDate` **AD ISO**, `noticeFilePath` document link).
- `/api/nots/news/companies/disclosure` — company disclosures / corporate actions (`newsHeadline`, `addedDate` **AD ISO**, `applicationDocumentDetailsList[].filePath`).
- `/api/nots/security` — **277 instruments** (`symbol`, `securityName`) → issuer registry for resolution.

**Direct HTTP to these → 401** (a browser-issued token gates them). Classification:
`OFFICIAL_PUBLIC_BUT_UNSTABLE`. Adoption rule: usable **only** via in-browser capture — we do
**not** replay/forge the token (that would defeat a bot control). The governed Playwright
engine loads the official page normally; the site's own JS makes the calls; we capture the
**public JSON responses** it receives. No bypass, read-only.

## Acquisition order (Phase 5)
`OFFICIAL_ENDPOINT` (governed Playwright JSON capture) → `PLAYWRIGHT/HTTP_DOM` (v2 text) →
`FALLBACK_TEXT`. Chromium is only launched for the NEPSE JS path.

## New modules (additive)
- `nepse_endpoint.py` — endpoint classification + adoption gate; `SecurityIndex` (symbol/issuer resolution from NEPSE's own `/api/nots/security`, never a 2nd registry); `NEPSEJsonExtractor` (notice + disclosure JSON → `ExtractedRecord`, category, AD date, document link, symbol). New `ExtractionMethod.OFFICIAL_ENDPOINT`.
- `nepse_capture.py` — bounded governed Playwright capturer: one context, headless, hard timeout, **read-only** (no clicks/mutation/login), per-response domain-policy revalidation (off-domain responses dropped), guaranteed teardown.
- `nepse_v3.py` — `run_nepse_deep_mission` with acquisition failover (capture injectable for deterministic tests).

## DOM parser decision (Phase 11)
**KEEP CURRENT** — no HTML parser (BeautifulSoup/lxml) added. The public JSON endpoints make
DOM scraping unnecessary for NEPSE; stdlib + JSON is sufficient and lighter on 8 GB.

## BS audit (Phase 12) — verified
Range 2075–2092, anchor BS 2075-01-01 = AD 2018-04-14. Tests at first day (→2018-04-14), last
supported day (year ≥2035), year/month boundaries, monotonicity, invalid-date rejection, raw
preservation. NEPSE API dates are AD ISO (no BS needed for the endpoint path); BS conversion
still covers gov-site (SEBON/NRB) text dates.

## Live validation (Phase 16) — real, bounded
`OFFICIAL_ENDPOINT`, both endpoints 200, **peak RSS 38.5 MB, 10.3 s**, cleanup all-closed,
0 orphan Chromium. Real facts: "Dividend for FY 2082-83 [MBL]" → CORPORATE_ACTIONS, symbol
**MBL RESOLVED**, freshness RECENT, AD date + PDF link; "Delisting of SBL Debenture [SBL]";
"Plant Shut Down [PMHPL]". 22 off-domain responses (fonts/analytics) correctly blocked by
domain-policy revalidation.

## V2 → V3 (nepalstock.com)
| | V2 | V3 |
|---|---|---|
| Facts from nepalstock | **0** (SPA shell) | real notices + disclosures |
| Dates | none | AD ISO per item |
| Document links | none | notice + disclosure PDFs |
| Symbol resolution | none | resolved via 277-security index |
| Peak RSS | — (0 facts) | 38.5 MB |

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, canonical market_data
writes = 0, payment/credential = 0. v3 modules import none of them (grep + test). Numeric
market fields in `/api/nots/security` (prices) are **never** turned into facts or canonical
market_data — only symbol/name used. Provenance stays `BROWSER_DERIVED` / `WEB_INTELLIGENCE`.
Prompt injection in captured JSON is data, never authority (tested).

## Failover / cleanup (Phase 17/19)
Capture degraded (`PLAYWRIGHT_UNAVAILABLE` / error) → typed degraded → HTTP fallback mission,
no crash, no hallucinated facts (tested). Every capture tears down page/context/browser;
0 orphan headless_shell verified.

## Tests
`tests/test_nepse_deep_v3.py` **18 tests** (85 total across the suite): endpoint
classification + adoption gate, JSON extraction, detail AD date, document links,
corporate-action classification, symbol resolution (resolved + ambiguous-never-guessed), BS
boundaries (first/last/year/month/invalid) + raw preservation, freshness after conversion,
dedup, prompt-injection-as-data, OFFICIAL_ENDPOINT mission, HTTP failover, provenance/domain
preserved, cleanup reported, no-trade-authority imports.

## Limitations
1. NEPSE notice headings are Nepali (Devanagari) — captured verbatim (WEB_INTELLIGENCE); no translation.
2. Endpoint is `OFFICIAL_PUBLIC_BUT_UNSTABLE` (browser-token-gated); if NEPSE changes its SPA/token, capture may need re-inspection — hence the HTTP failover.
3. `filePath`→document URL is a best-effort NEPSE path convention; not fetched/verified in this milestone.
4. Symbol resolution matches ticker/name substrings from NEPSE's own list; rare name collisions → AMBIGUOUS (never guessed).

## Verdict
JS-heavy NEPSE now yields real structured corporate actions, disclosures, dates, document
links, and resolved symbols via a legitimate governed-Playwright JSON capture — the V2 gate is
closed. Endpoint stability is external, so:

**SAATHIOS_NEPSE_DEEP_EXTRACTION_V3_CERTIFIED_WITH_LIMITATIONS.**

## Next milestone (do NOT auto-start)
`M — NEPSE_DISCLOSURE_DOCUMENT_INGESTION`: route captured document URLs through the existing
governed document/evidence path (PDF text extraction, hashing) + endpoint-stability monitor.
Browser-use stays DEFER.
