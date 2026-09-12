# SaathiOS — Browser Research Extraction Precision (V2)

**Builds on `d84d10f2`.** Improves the HTTP+Playwright browser-research stack: source-aware
extraction, interface-noise filtering, deterministic dedup, Nepali **BS→AD** date
normalization, freshness on normalized dates, and durable orchestrator integration.
**No browser-use** (stays `BROWSER_USE_DEFER`), no second research architecture, no trade
authority. HTTP first, Playwright escalation, browser-use deferred.

## New modules (additive)
- `bs_date.py` — embedded authoritative BS month table (2075–2092, anchor BS 2075-01-01 = AD 2018-04-14, extracted once from the vetted `nepali-datetime` lib — **zero runtime dep**). `bs_to_ad`, `is_valid_bs`, `parse_date` (calendar inference: BS/AD/AMBIGUOUS/UNKNOWN; Nepali numerals; raw preserved; invalid → UNKNOWN, never guessed).
- `records.py` — canonical `ExtractedRecord` + `ExtractionMethod` (HTTP_DOM/PLAYWRIGHT_DOM/TABLE/DOCUMENT_LINK/FALLBACK_TEXT) + `SymbolResolution` + deterministic `deduplicate`.
- `noise.py` — filters nav/menu/footer/social/login/language/phone/email/address/copyright/breadcrumb + multi-word nav-vocab menus.
- `extractors.py` — `GenericExtractor` + `SEBON/NRB/CDSC/NEPSE/CompanyDisclosure` (BS-hint for Nepali gov sites); category routing; symbol resolution via existing `instruments.normalize_symbol` (RESOLVED/AMBIGUOUS/UNRESOLVED, never guessed); document-link capture.
- `extract_v2.py` — page → records → dedup → FROZEN `ExtractedFact`; freshness from normalized AD ts.
- `durable.py` — `DurableBrowserResearch`: reuses `tg/research_orchestrator` for durable job tracking (real job_id, budget estimate, journal); single-worker runner executes the mission; the orchestrator's compute scheduler is never asked to run it. Degrades cleanly if the orchestrator is unavailable.
- `status.py` (extended) — Central Command projection (acquisition tier, official-source count, facts, fresh, unknown_dates, contradictions, tier counts).

## BS→AD correctness (verified)
`BS 2081-05-27 → AD 2024-09-12`, `BS 2082-01-23 → AD 2025-05-06`, `BS 2080-01-01 → AD 2023-04-14`.
The V1 bug (BS `2082` misread as AD 2082→future→UNKNOWN) is fixed. Invalid BS (`2081-13-40`)
→ UNKNOWN / raises; ambiguous overlap (`2081-05-27` no hint) → AMBIGUOUS; far-future → UNKNOWN.

## V1 → V2 benchmark (live, identical fetched content)
| Source | v1 facts | v1 noise | v2 facts | v2 noise | dupes removed | noise lines dropped | v2 dated | symbols |
|---|---|---|---|---|---|---|---|---|
| sebon.gov.np | 13 | 4 | 9 | **0** | 0 | 220/229 | 1 | 2 |
| nrb.org.np | 34 | 3 | 41 | **0** | **34** | 459/534 | 0 | 1 |
| nepalstock.com | 0 | 0 | 0 | 0 | 0 | 3/3 (SPA shell) | 0 | 0 |

Chrome noise (phone/email/©/social) → **0** in V2. Dedup real (34 on NRB). BS dates
normalize where present. Symbols resolved via canonical registry helper.

## Durable + resource (live)
Durable mission COMPLETE via the real orchestrator queue (job_id issued), `max_browser_workers=1`,
50 facts, confidence 70, official_share 1.0. **Peak RSS 64 MB, ~3.7 s** for 3 official sources.

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, canonical
market_data writes = 0, payment/credential = 0. v2 modules import none of them (grep + test).
Provenance stays `BROWSER_DERIVED` / `WEB_INTELLIGENCE`. browser-use not invoked.

## Tests
`tests/test_browser_research_v2.py` **30 tests** (+22 v1 +18 browser-use = **67 passing**):
SEBON/NRB/NEPSE extraction, noise filtering, dedup, corporate-action classification,
symbol resolution, raw-date preservation, BS recognition (incl Nepali numerals), BS→AD,
invalid BS, ambiguous calendar, freshness after conversion, document links, tier/provenance/
WEB_INTELLIGENCE preservation, prompt-injection, broker block, no gateway.execute, evidence +
confidence integration, durable queue, single-worker enforcement, timeout, cleanup, CC
projection, and a v1-vs-v2 precision benchmark assertion.

## Limitations (why CERTIFIED_WITH_LIMITATIONS)
1. **JS-heavy NEPSE deep extraction NOT achieved**: the governed READ served the nepalstock
   SPA shell over the HTTP tier (0 facts); Playwright is not auto-triggered for a full-page
   read, and selector-based Playwright deep-fetch + NEPSE public-XHR investigation (Phase 9)
   are **deferred**. This was a major milestone gate — only partially met.
2. **Date recall low on index/home pages**: per-notice dates live on detail/listing pages;
   HTTP homepage text often lacks them (SEBON 1 dated, NRB 0). Needs detail-page navigation.
3. **Section-label false positives**: without DOM structure (HTTP text only, no HTML parser
   installed), nav-ish section labels ("Laws, Policies & Guidelines") can still classify as
   REGULATORY. True fix needs DOM/selector extraction or an HTML parser.
4. Extraction/issuer resolution is format-level (no full symbol registry list loaded).

## Verdict
Precision materially improved on noise + dedup + BS-date normalization + durable integration,
authority intact and live-validated — **but the JS-heavy NEPSE deep-extraction gate is only
partially met**.

**SAATHIOS_BROWSER_RESEARCH_EXTRACTION_PRECISION_V2_CERTIFIED_WITH_LIMITATIONS.**

## Next milestone (do NOT auto-start)
`M — NEPSE_DEEP_EXTRACTION_V3`: Playwright selector-based deep extraction + NEPSE public-XHR
investigation (Phase 9 classification) + detail-page date recall + optional lightweight HTML
parser for true DOM extraction. Browser-use remains DEFER.
