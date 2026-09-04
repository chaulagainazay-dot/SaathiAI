# REST adapter

The adapter uses the official Binance `/api/v3` public REST surface with TLS-verified stdlib HTTPS, a five-second timeout, an allowlisted base URL, and a bounded 2 MiB response policy. JSON/schema, symbol, price, quantity and OHLC invariants fail closed. Offline transport injection makes tests network-independent.
