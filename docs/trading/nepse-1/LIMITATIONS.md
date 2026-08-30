# Limitations

## The column schemas are UNVERIFIED — this is the important one

I do not have a real Meroshare, TMS, or Nepal Share export. The column aliases
in `importers/__init__.py` are derived from the public description of each
format, **not from a genuine file**.

They are almost certainly incomplete, and may be wrong.

The failure mode is contained by design: a header that does not match a known
fingerprint returns `ImportFormat.UNKNOWN` with **every row rejected**, rather
than being coerced into the closest match. An operator sees "format not
recognised; no row was imported" instead of a silently mangled portfolio.

**To pin them:** one real export of each, with values redacted if you prefer —
only the header row matters. The parsers then get fixture tests against real
files and this limitation closes.

Status until then: `NEPSE_IMPORT_SCHEMAS_UNVERIFIED`.

## Live NEPSE data remains blocked

Nothing in this milestone fetches a price. Six of the teardown's nine screens
(Market, All Stocks screener, stock detail, watchlist live columns, Brokers,
Analysis) require a live feed, and the teardown itself flags broker-wise trade
data as *"the hardest piece to source outside their own disclosures."*

SaathiOS will not scrape NEPSE or scrape a third-party app to obtain it. That
leaves a licensed or officially published source, which is a decision only you
can make. Status: `NEPSE_LIVE_DATA_BLOCKED_PROVIDER_ACCESS`.

## Not built in this milestone

- Transaction (buy/sell) import — only holdings snapshots parse today
- Excel (`.xlsx`) reading — TMS is described as Excel; only its CSV export path
  is handled. Adding `.xlsx` means a new dependency and should be a deliberate
  decision
- Applying an `ImportResult` to the Canonical Fund Ledger — deliberately a
  separate step, and the natural content of NEPSE-2
- Instrument seed data — the master defines the *shape* for all ~586 listings;
  it ships with no populated list, because a fabricated instrument list would be
  worse than an empty one
- Fundamentals, broker-wise data, sector performance, scoring model, UI

## The "AI Score" is rejected as an authority

The teardown's AI Score → Buy/Sell/Neutral Signal is a consumer feature in that
product. In SaathiOS a score may inform research commentary only. It cannot
cross into `PortfolioConstructionEngine`, and no part of this milestone creates
a path for it to.
