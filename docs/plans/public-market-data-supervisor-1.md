# PUBLIC-MARKET-DATA-SUPERVISOR-1 — process-wide public crypto market data

Branch `feature/nepse-completion`, start `d6d9b812` (recovered from repository
reality, clean). **Track A untouched**: `observation/epoch-1` @ `5206a98e`, epoch-3
still OPEN in its own worktree.

## Discovery — the gap was ownership, exactly as Track B predicted

`saathi/platform/crypto/binance.py` already contains the whole certified stack,
and **none of it was rebuilt**:

| Component | Provides | Verdict |
|---|---|---|
| `SequenceTracker` | DUPLICATE / REGRESSION / GAP | **REUSE** |
| `BoundedStreamController` | bounded queue, backpressure, reconnect limits | **REUSE** |
| `MarketDataSupervisor` | heartbeat staleness, bounded exponential backoff, capture with overflow | **REUSE** |
| `OrderBookSynchronizer` | snapshot + contiguous-delta safety | **REUSE** |
| `BinanceWebSocketTransport` | `wss://stream.binance.com`, bounded frames, ≤4 streams | **REUSE** |
| `BinancePublicProvider` | `https://api.binance.com/api/v3`, symbol allowlist | **REUSE** |

What was missing was runtime ownership, lifecycle and composition. That is all
this milestone adds.

## The boundary

**Two hosts, and no third is reachable**: `stream.binance.com`,
`api.binance.com`. Every private surface is named in `FORBIDDEN_PATH_MARKERS` and
each is asserted absent from the whole crypto stack — `/api/v3/account`,
`/api/v3/order`, `/api/v3/openOrders`, `/api/v3/allOrders`, `/api/v3/myTrades`,
`/sapi/`, `/wapi/`, `listenKey`, `userDataStream`, `signature=`, `X-MBX-APIKEY`.

The deny-list names the forbidden paths in order to forbid them, so a naive
substring scan flags the very constant that enforces the rule. The test excises
that assignment **by AST line range** before scanning, so the exclusion is exact
and cannot silently swallow neighbouring code.

**Zero credentials**, structurally: no `api_key`, `secret`, `hmac`, `sign(`,
`signature`, `listenKey` or `keyring` token anywhere; no `hmac`/`hashlib`/
`credentials`/`keyring`/`auth` import. `requires_credentials` is `False` and no
code path can request one.

Spot only. `BTCUSDT`, `ETHUSDT`. `PUBLIC_MARKET_DATA` scope travels with provider
health so a healthy feed is never read as a healthy trading account.

## Off by default, at three levels

Nothing connects on import (asserted: no module-level call expression, no
`create_connection`/`urlopen`/`getaddrinfo` in the module), nothing connects on
construction, and **server boot opens no socket** unless
`SAATHI_PUBLIC_MARKET_DATA` is an explicit affirmative — parametrised over
`0/false/no/off/""/maybe`, all of which start nothing.

## Freshness is still not connectivity

The runtime reports `connected` and `last_valid_observation` and **states no
freshness of its own** — the collector already decides that from the observation
clock and an explicit evaluation time. Putting a second freshness rule here would
recreate the defect TRADING-HEALTH-PRODUCERS-1 fixed.

Only an **ACCEPTED** frame advances the observation clock. A duplicated,
regressing, gapped, malformed or backpressure-dropped frame is data the runtime
saw but could not trust; each is parametrised and asserted not to refresh it —
connectivity-as-freshness in another costume.

## Fault behaviour

Sequence gap → `resync_pending`, DEGRADED, never a healthy book. Non-contiguous
delta → `GAPPED`. Bounded queue holds under 5,000 frames with drops **counted and
surfaced**, never silent. Reconnect backoff never decreases and is capped;
exhaustion is `FAILED_SAFE` with `contained: True`. DNS failure, refused
connection and rate limiting map to **distinct** provider states — no generic
OFFLINE flattening. Shutdown closes the socket, releases the queue, and five
start/stop cycles leak no thread.

## Integration

Disabled → `PUBLIC_FEED_DISABLED` / `NOT_CONFIGURED` with real reasons. Enabled →
market data and provider resolve to the runtime and **its own** tracker (asserted
by `is`, not shape), and real public events flow unshaped into the ops snapshot as
HEALTHY while `live_trading_authorized` stays `False`.

## Real public probe — blocked, and precisely so

`LIVE_PUBLIC_PROBE_BLOCKED_ENVIRONMENT`. Not a general network outage:
`example.com` resolves and outbound HTTPS succeeds, while `api.binance.com` DNS
fails with `gaierror`. **This environment specifically blocks Binance.** The code
path is exercised offline through an injected transport; the live probe is
unproven here and says nothing either way about the code.

## Verification

**61 focused tests**; **406 passed** across supervisor, runtime wiring, Central
Command, collector, producers, trading ops, provider runtime, market observation,
trading guardian, platform API, market-data and paper-crypto suites.

One Track B test was legitimately superseded: it asserted the old
market-observation reason text. Market data now resolves to the real runtime, so
it asserts the still-true property — nothing fabricated, and a switched-off feed
reports as switched off.

## Certification

**`PUBLIC_MARKET_DATA_SUPERVISOR_1_CERTIFIED_OFFLINE_LIVE_PROBE_BLOCKED_ENVIRONMENT`** —
not inflated to `CERTIFIED`, because the live probe could not run.

### Limitations

1. **No live public probe was performed** — Binance DNS is blocked here. Every
   transport guarantee is proven against an injected transport, not a real socket.
2. **Trade stream only** by default; depth/book synchronisation is wired and
   tested but not subscribed.
3. **No async adapter.** The runtime is driven by `on_frame`/`on_disconnect`; a
   real socket needs a reader loop, which belongs with the live probe.
4. **Capture is in-memory and bounded** (ring buffer); no durable capture.
5. NEPSE licence-blocked, no live trading, no real broker — unchanged.

### Invariants held

`NO_BINANCE_PRIVATE_ENDPOINTS`, `NO_BINANCE_CREDENTIALS`, `NO_DERIVATIVES`,
`NO_MARGIN`, `NO_LEVERAGE`, `NO_PUBLIC_DATA_TO_EXECUTION_AUTHORITY`,
`NO_FALSE_LIVE_LABEL`, `NO_CONNECTIVITY_AS_FRESHNESS`,
`NO_UNBOUNDED_MARKET_DATA_QUEUE`, `NO_SEQUENCE_GAP_AS_HEALTHY_BOOK`,
`NO_STALE_DATA_AS_FRESH`, `NO_LIVE_TRADING`, `NO_PRIVATE_ACCOUNT_ACCESS`.
