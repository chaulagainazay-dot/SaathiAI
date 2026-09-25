# PUBLIC-MARKET-DATA-ASYNC-READER-1 — bounded ingestion, honest freshness

Branch `feature/nepse-completion`, start `f2b04c21` (recovered from repository
reality, clean). **Track A untouched**: `observation/epoch-1` @ `5206a98e`,
epoch-3 OPEN, REPLAY. Closes limitation 3 of PUBLIC-MARKET-DATA-SUPERVISOR-1.

## Discovery — the transport is synchronous

`BinanceWebSocketTransport.recv_json()` blocks on `self.ws.recv()` via
`websocket.create_connection(..., timeout=10, enable_multithread=True)`. It is
**not** rewritten. The reader awaits it in an executor thread, so one asyncio
task owns ingestion and stays cancellable at a real await point.

The consequence shapes shutdown: a thread parked in a blocking `recv` cannot be
interrupted, so **closing the transport is what frees it**. Cancelling the task
alone would leave a thread waiting on a socket nobody will feed. That is why the
shutdown order is load-bearing rather than cosmetic.

## One reconnect owner

`MarketDataSupervisor` already owns bounded reconnect: it decides BACKOFF versus
FAILED and computes the delay. **The reader never decides to retry** — it reports
the disconnect, asks what the supervisor decided, and waits the delay it is
given. Two components each deciding to reconnect is how a reconnect storm starts.
Pinned structurally: the reader contains no `.connect(`, `.subscribe(`,
`create_connection` or `reconnect_count =`, calls `next_backoff` and never calls
`connect`.

## The freshness rule, in one place

Only an **ACCEPTED market event** advances the observation clock. `_dispatch`
classifies first and drops everything else before it can reach `on_frame`:

| Frame | Counted as | Advances freshness |
|---|---|---|
| `{"e":"trade",…}` | MARKET_EVENT | **yes** |
| `{"result":null,"id":1}` subscription ack | CONTROL | no |
| `{"ping":1}` / `{"pong":1}` | CONTROL | no |
| `{"e":"kline"}` | UNSUPPORTED_EVENT | no |
| `"not json"`, `{"x":1}`, `{"e":123}` | MALFORMED | no |

A subscription acknowledgement is the most plausible false-green in the whole
chain — the socket is genuinely healthy and no market data has arrived — so it
has its own test asserting the feed still reads as insufficient evidence.

## A dead reader is not a connected feed

`NO_READER_TASK_DEATH_AS_HEALTHY`. The socket can stay open while nothing reads
it, so `snapshot()["connected"]` requires the reader to be alive whenever one was
started. Reporting an unread socket as connected is the same lie as treating
connectivity as freshness. A consumer exception is recorded with its detail
rather than vanishing with the task.

## Defect found in review

**`start_async` was not idempotent.** Each call built a new `AsyncFrameReader`,
so three calls left three tasks on one socket — interleaving `recv`, shredding
the frame order the sequence tracker depends on, and orphaning executor threads.
Now a live reader short-circuits the call, and the test asserts the task
*identity* is unchanged and the task count rises by exactly one.

## Fault matrix

Valid flow · malformed JSON · oversized frame · unsupported event · duplicate ·
sequence regression · sequence gap · slow consumer · queue overflow · socket
close (EOF) · transport error · reconnect success · reconnect exhaustion ·
reader exception · cancel while blocked in `recv` · shutdown during backoff ·
five start/stop cycles · duplicate start.

Error classes stay distinct — `TRANSPORT_CLOSED`, `TRANSPORT_ERROR`,
`DECODE_FAILED`, `FRAME_TOO_LARGE`, `CONSUMER_EXCEPTION`, `RECONNECT_EXHAUSTED`,
`CANCELLED` — never flattened. A single bad frame does not tear down a healthy
stream: decode failures are counted and reading continues up to a bound.
`CancelledError` is re-raised, never swallowed into reconnect logic.

## Bounded by construction

The reader holds **no queue of its own** — asserted: no `deque(`, `= []`,
`Queue(` or `asyncio.Queue` in the module. The runtime's `BoundedStreamController`
is the only buffer, so there is nowhere for a backlog to accumulate. 500 frames
into a queue of 8 stay at 8; 400 frames into a queue of 4 surface drops.

## Verification

**46 focused tests**; **452 passed** across reader, supervisor, runtime wiring,
Central Command, collector, producers, trading ops, provider runtime, market
observation, trading guardian, platform API, market-data and paper-crypto suites.

Integration drives fake transport → reader → runtime → supervisor → provider
tracker → collector → ops snapshot with no manual shaping. Provider reads
HEALTHY; execution stays SHADOW and `live_trading_authorized` stays `False`.

Resources: 3,000 frames leave task count flat and resident memory materially
unchanged; shutdown while blocked completes under 3 s; five cycles accumulate no
readers.

## Real public probe — still blocked

`api.binance.com` and `stream.binance.com` both fail DNS with `gaierror` while
`example.com` resolves and outbound HTTPS works. **This environment specifically
blocks Binance.** Verdict is not weakened and not inflated.

## Certification

**`PUBLIC_MARKET_DATA_ASYNC_READER_1_CERTIFIED_OFFLINE_LIVE_PROBE_BLOCKED_ENVIRONMENT`**

### Limitations

1. **No live socket has ever been read.** Every guarantee is proven against a
   scripted transport. The executor-thread bridge, in particular, has not met a
   real blocking `recv`.
2. **Trade stream only by default.** `depthUpdate` is supported and tested but
   not subscribed unless configured.
3. **Reconnect re-dials nothing yet.** The supervisor grants a backoff and the
   reader waits, but re-establishing the socket after a drop is still the
   runtime's `start()` path — a reconnecting reader loop is the natural follow-on
   once a live socket exists to reconnect to.
4. NEPSE licence-blocked, no live trading, no real broker — unchanged.

### Invariants held

`NO_READER_EXECUTION_AUTHORITY`, `NO_UNBOUNDED_READER_QUEUE`,
`NO_SOCKET_CONNECT_AS_FRESHNESS`, `NO_CONTROL_FRAME_AS_FRESHNESS`,
`NO_MALFORMED_FRAME_AS_FRESHNESS`, `NO_SEQUENCE_GAP_AS_HEALTHY`,
`NO_READER_TASK_DEATH_AS_HEALTHY`, `NO_DUPLICATE_RECONNECT_OWNER`,
`NO_BINANCE_PRIVATE_ENDPOINTS`, `NO_BINANCE_CREDENTIALS`, `NO_FALSE_LIVE_LABEL`,
`NO_LIVE_TRADING`, `NO_CROSS_EPOCH_EVIDENCE_MERGE`.
