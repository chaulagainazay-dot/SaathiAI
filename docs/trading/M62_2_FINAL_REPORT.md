# M62.2 — Final Report: Deterministic Market-Data Quality, Storage & Replay

1. **Verdict:** `M62_2_COMPLETE`.
2. **Starting branch/SHA:** `milestone/m61-backend-workflow-persistence` @ `fc6b152`.
3. **Ending branch/SHA:** same branch @ (this commit).
4. **Commits:** one (this milestone).
5. **Reused code:** M62.1 `trading_models` (`AssetClass`, `DataQuality`, `MarketState`,
   `D`) — no duplicate models. `tools/calendar.py` (macOS app) and `tools/quote_maker.py`
   (image maker) confirmed unrelated; not reused.
6. **New modules:** `saathi/platform/market_data/{__init__,models,quality,calendar,
   provider,fixtures,store,ingest,replay}.py`; market-data endpoints in `platform/api.py`.
7. **Canonical contracts:** `MDInstrument`, `MDQuote`, `MDBar`, `Timeframe`
   (1m/5m/15m/1h/1d). Decimal money/price/volume; tz-aware timestamps enforced.
8. **Data-quality states:** VALID/STALE/INCOMPLETE/OUTLIER/GAPPED/DUPLICATE/
   OUT_OF_ORDER/UNVERIFIED/MARKET_CLOSED/PROVIDER_ERROR/INVALID_TIMESTAMP/INVALID_PRICE
   + structured findings; mapped to coarse `DataQuality` for the Guardian.
9. **Freshness policy:** quote 15s / intraday-bar 600s / daily-bar 48h / instrument 7d
   (`FreshnessPolicy`, not hidden in UI). Quote staleness rejects; bar freshness is a
   decision-time check (`is_bar_fresh`), not a validity gate for historical bars.
10. **Fixture datasets (15):** TRENDING, MEAN_REVERTING, FLAT, HIGH_VOLATILITY,
    GAP_DOWN, ILLIQUID, FLASH_CRASH_LIKE, MISSING_BARS, DUPLICATE_BARS,
    OUT_OF_ORDER_BARS, STALE_QUOTES, FUTURE_TIMESTAMPS, INVALID_OHLC, ABNORMAL_SPREAD,
    MARKET_CLOSED.
11. **Fixture hashes:** `docs/trading/m62_2_evidence/fixture_manifest.json` (stable,
    reproducible sha256 per dataset).
12. **Provider contract:** read-only `MarketDataProvider` (get_instrument/get_quote/
    get_bars/get_market_clock/list_supported_timeframes) + `ProviderResult`/
    `ProviderStatus` (8 statuses); failures never become empty-valid data.
13. **Storage schema:** `md_instruments`, `md_bars` (unique org+provider+instrument+
    timeframe+start_epoch), `md_quotes`, `md_rejects`; single-host SQLite.
14. **Ingestion:** fetch→normalize→validate→classify→persist→`IngestionReport`
    (requested/received/accepted/rejected/duplicates/gaps/outliers/stale/provider_errors/
    time_range/version/correlation_id).
15. **Duplicate handling:** unique constraint + `INSERT OR IGNORE`; series duplicate
    detection marks DUPLICATE.
16. **Gap handling:** series detects missing intervals → GAP_BEFORE.
17. **Outlier handling:** abnormal spread (quote) / abnormal jump (bar) → OUTLIER.
18. **Time-zone handling:** tz-aware required; naive rejected; UTC-normalized epochs.
19. **Market-calendar handling:** bounded `DEFAULT_24_5` + `RTH_UTC`; unsupported → None.
20. **Replay engine:** deterministic step-mode; pause/resume/stop/reset/checkpoint/
    restore (rejects corrupted/mismatched checkpoints); no orders.
21. **API endpoints:** instruments (list/get), quotes, bars, fixtures manifest+ingest,
    replays (create/get/step/stop).
22. **Auth + tenant isolation:** every endpoint requires a session; reads =
    WORKFLOW_READ, ingest/replay = WORKFLOW_WRITE; all queries org-scoped; ingest audited.
23. **Guardian integration:** market-data quality maps to coarse `DataQuality`;
    Guardian vetoes any non-VALID input (certified) — no provider logic imported.
24-27. **Tests:** unit (validation/OHLC/spread/freshness/gap/dup/order/future/session/
    provider/fixtures/replay), persistence (idempotent/range/tenant/restart/quality/
    rejects), integration (fixture→ingest→store, Guardian consume, HTTP auth+tenant),
    adversarial (naive/future/negative/crossed/invalid-OHLC/dup/unsupported-tf/malformed/
    invalid-decimal/corrupted-checkpoint). 16 M62.2 + 19 M62.1 pass; M61+M50 regression pass.
28. **Regression:** 32 pass (M62.1+M61+M50); `git diff --check` clean.
29. **Security findings:** none. Safety scan: no order-submit/broker/network/subprocess/
    secret/execution-import in `market_data/`. No public listener change.
30. **Known limitations:** single-host SQLite; fixture provider only (no external);
    two bounded calendars; in-memory replay registry.
31. **Working tree:** clean except preserved `docs/design-spec/`.
32. **Push/merge/deploy:** none.
33. **Recommended M62.3:** evidence-backed research pipeline (source provenance,
    citation verification, contradiction search, thesis versioning, independent
    challenge) consuming this market-data layer read-only.

PlatformAgentRuntime remains the canonical agent runtime.
ExecutionGateway remains the sole authority for registered tool execution.
Trading Guardian remains an independent fail-closed veto layer.
M62.2 provides deterministic market-data quality and replay infrastructure only.
It does not authorize strategy execution, paper trading, broker access, live trading,
leverage, margin, short-selling, derivatives, production deployment, or autonomous
capital use.
Services remain localhost-only.
No push, merge, deployment, or external rollout authority is granted.
