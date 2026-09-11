# MD-1.1 Identity Contract

`venue` is the canonical internal identity concept. Provider exchange strings
remain adapter-bound strings; no duplicate exchange enum was introduced.

`resolve_market_identity` validates instrument prefix, venue, market, and asset
class. A venue-qualified instrument derives its venue; an explicit NEPSE market
may derive NEPSE. Generic omissions remain `UNKNOWN`. Contradictions and unknown
venue prefixes fail closed with deterministic codes.

NEPSE examples resolve as `NEPSE:NABIL` → venue `NEPSE`, market `NEPSE`.
`BINANCE:BTCUSDT` is representable for forward compatibility without provider
connectivity. Provider aliases are not persisted as canonical financial IDs.
