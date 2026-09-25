# Dataflow / Provider Audit

## Sources actually implemented (not README claims)

| Source | Module | Data | Notes |
|---|---|---|---|
| Yahoo Finance | `y_finance.py` | OHLCV, financials | inclusive date ranges fixed in 0.3.x |
| Yahoo Finance news | `yfinance_news.py` | headlines + `pub_date` | best look-ahead handling in the repo |
| Alpha Vantage | `alpha_vantage{,_common,_stock,_indicator,_news,_fundamentals}.py` | prices, indicators, news, statements, OVERVIEW | needs API key |
| FRED | `fred.py` | macro series | current vintage only, no revision history |
| Reddit | `reddit.py` | posts | `_strip_html`, graceful placeholder on failure |
| StockTwits | `stocktwits.py` | messages | resilience path tested |
| Polymarket | `polymarket.py` | prediction-market odds | genuinely novel signal source |
| stockstats | `stockstats_utils.py` | derived indicators | computed locally from OHLCV |

`interface.py` provides vendor routing with a per-capability vendor map
(`"get_fundamentals": {...}`), and `errors.py` defines a `VendorError` taxonomy.

## Contract quality

| Property | Implementation | Assessment |
|---|---|---|
| Provider interface | function-per-capability + `route_to_vendor(capability, ...)` map | Simple, readable; no formal protocol/ABC |
| Vendor fallback | routing map with per-capability vendor preference; tested (`test_vendor_routing.py`) | **Good** |
| Error normalisation | `VendorError` taxonomy (`test_vendor_errors.py`) | **Good** — worth borrowing conceptually |
| Retries | exponential backoff on yfinance fetchers | Adequate |
| Rate limiting | none explicit | **Gap** |
| Caching | file cache under data dir; no TTL policy surfaced | Weak |
| Timestamps / timezone | timezone-aware parsing, UTC normalisation in news path | **Good** where present |
| Stale-data handling | explicit stale-OHLCV rejection | **Good** |
| Missing data | placeholder strings returned into prompts (e.g. "No global news found") | **Risky** — see below |
| Provenance | none — no source id, fetch time, or vintage on records | **Gap** |
| Corporate actions | none | **Gap** |
| Look-ahead | see `LOOKAHEAD_AUDIT.md` | Mixed |
| Licensing / ToS | none | **Gap** (SaathiOS has `market_data/licensing.py`) |

## Missing-data behaviour is a correctness hazard

When a source returns nothing, the dataflow returns a human-readable placeholder
string that flows into the analyst prompt. The LLM then reasons over the absence
as if it were prose. The `SentimentReport.confidence` field partially compensates
(it instructs `low` when a source returned a placeholder), but nothing structural
prevents a report built on three empty sources from producing a confident-sounding
narrative. Degradation is silent at the type level.

SaathiOS should represent absence as a typed `Unavailable(reason, source, as_of)`
on the evidence record, never as prose.

## Comparison with SaathiOS

SaathiOS `saathi/platform/market_data/` and `saathi/platform/tg/market_data/`
already provide: `provenance.py`, `quality.py`, `reconciliation.py`,
`normalization.py`, `corporate_actions.py`, `adjustments.py`, `calendar.py`,
`catalog.py`, `registry.py`, `licensing.py`, `feature_store.py`, `replay.py`,
`ingestion.py`, `certification.py`, `bias_controls.py`, `dataset_split.py`,
`signal_validation.py`.

**Verdict: KEEP SAATHIOS as the canonical market-data plane.** Introducing a
second canonical data system would violate the SaathiOS anti-duplication rule and
would lose provenance, corporate actions, and licensing.

## What to take

1. **`VendorError` taxonomy + per-capability vendor routing map** — ADAPT. SaathiOS
   has provider governance for *LLMs* (`saathi/inference/`) but the market-data
   side would benefit from the same normalised failure vocabulary.
2. **Prediction-market odds (Polymarket) as an evidence source** — ADAPT. A
   genuinely differentiated, cheap, timestamped signal SaathiOS does not have.
3. **FRED macro adapter shape** — ADAPT, but only with vintage/revision handling
   added; the upstream version has none.
4. **Reddit / StockTwits ingestion** — DEFER. Low signal-to-noise, and the primary
   prompt-injection vector (see `SECURITY_REVIEW.md`).
5. **Everything else in the data plane** — KEEP SAATHIOS.
