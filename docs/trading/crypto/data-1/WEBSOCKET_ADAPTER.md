# WebSocket adapter

`BoundedStreamController` is the transport-neutral lifecycle boundary for the future official Binance stream client. It provides explicit connect/disconnect state, bounded buffering, duplicate/regression/gap classification, and bounded reconnect attempts. A production socket transport is intentionally deferred to CRYPTO-DATA-2; no uncontrolled loop or unbounded queue is permitted.
