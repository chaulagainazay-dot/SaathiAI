# M62.2 — Market-Data Foundation

Package `saathi/platform/market_data/` — provider-neutral, decimal-precise,
timezone-AWARE, fail-closed. Data only: no order submission, no broker, no network,
no execution authority (verified by safety scan).

## Modules
- `models.py` — `MDInstrument`, `MDQuote`, `MDBar`, `Timeframe`, `MarketDataQuality`,
  `QualityFinding`, `FreshnessPolicy`; reuses M62.1 `AssetClass`/`DataQuality`/`D`.
  Timestamps must be tz-aware (`require_aware` rejects naive).
- `quality.py` — pure validation + `classify_quote`/`classify_bar`/`classify_series`
  + `is_bar_fresh` (decision-time). Validation ≠ normalization; never repairs values.
- `calendar.py` — bounded `DEFAULT_24_5` + `RTH_UTC`; unsupported → None (fail-closed).
- `provider.py` — read-only `MarketDataProvider` ABC + `ProviderResult`/`ProviderStatus`
  (SUCCESS/NOT_FOUND/UNSUPPORTED/RATE_LIMITED/TIMEOUT/AUTH_FAILURE/UNAVAILABLE/MALFORMED).
- `fixtures.py` — deterministic `FixtureProvider` + 15 datasets + `fixture_manifest()` hashes.
- `store.py` — single-host SQLite; instruments/bars/quotes/rejects; idempotent, tenant-scoped.
- `ingest.py` — fetch→normalize→validate→classify→persist→`IngestionReport`.
- `replay.py` — deterministic step-mode `ReplayEngine` (pause/resume/stop/reset/checkpoint).

## Canonical contracts
Instrument (provider/venue/symbol/canonical_symbol/asset_class/currencies/precision/
min qty+notional/timezone/market_calendar/status); Quote (bid/ask/last/sizes/source+
ingest time/quality); Bar (timeframe/OHLCV/start+end/source+ingest time/quality).
`Decimal` for all money/price/volume.

## Freshness policy (not hidden in UI)
`FreshnessPolicy`: quote 15s, intraday-bar 600s, daily-bar 48h, instrument 7d.
Quote staleness → rejected. Bar staleness is a DECISION-TIME check on the latest bar
(`is_bar_fresh`), not a validity gate for historical bars.

## API (authenticated, tenant-scoped, bounded — read/ingest only)
`GET /market-data/instruments`, `/instruments/{symbol}`, `/quotes/{symbol}`,
`/bars/{symbol}`, `/fixtures/manifest`; `POST /fixtures/ingest` (operator+, audited),
`POST /replays`, `GET /replays/{id}`, `POST /replays/{id}/step|stop`. No order/broker
endpoint exists.

## Limitations
Single-host SQLite (no multi-node/distributed ingestion). Fixture provider only (no
external provider). Two bounded calendars. Replay registry is in-memory (checkpoints
are restart-safe values, but the live registry is process-local).
