# SaathiOS — Open-Session NEPSE Validation & Live Streaming (v1)

**From `f9a8344b`; Research Surface frozen `b771d761`; Fusion `4d685383`.** Adds efficient
live delivery on top of the certified live-browser observation baseline, and validates the
producer against the real site. Architecture is strictly:

```
Official NEPSE page → ONE governed Playwright producer (single-flight, bounded cadence)
  → cached NepseLiveMarketSnapshot (versioned) → publish market.nepse.snapshot
  → EXISTING Event Fabric (saathi.events.bus) → EXISTING SSE (/api/events/stream)
  → many read-only consumers (Central Command / Chat / Voice / Market Intelligence)
```

No new browser, no new scheduler, no new event system. **SSE clients never drive
acquisition** — they consume the already-acquired snapshot.

## Single-flight & cadence
`NepseLiveService.refresh()` holds a `threading.Lock` — `MAX_CONCURRENT_NEPSE_BROWSER_
ACQUISITIONS = 1`. Concurrent callers (Central Command + scheduler + chat + voice)
**coalesce** onto the one in-flight acquisition (others get the cached snapshot; a first
caller with no cache yet awaits the in-flight owner). Bounded interval skips reads that are
fresh enough (open 60 s / closed 1800 s). The producer loop (`scheduler.nepse_live_
producer_loop`, launched from `scheduler.start()`, opt-out `SAATHI_NEPSE_LIVE_PRODUCER=0`)
runs the fast cadence only during OPEN/PRE_OPEN (canonical `NepseCalendar.session_state`);
otherwise idle (one seed snapshot, then quiet).

## Event / SSE
- Event name `market.nepse.snapshot`; payload = **compact market projection** (index,
  change, %, turnover, volume, breadth, market_status, freshness, source_health, top-8
  watchlist, `version`, `snapshot_id`) — Phase 6 **strategy A**, ~1.2 KB; NOT all 345
  records. `controls: []` (no trade controls).
- Reuses `saathi.eventstream.sse_stream`, which subscribes `"*"` on the same bus and hops
  frames to each client's loop — verified the SSE bus IS `saathi.events.bus`.
- `publish_snapshot` uses `bus.publish_sync` from the threadpool/producer thread; if ever
  called on a running loop it skips (acquisition still succeeds).
- Central Command panel (`/market/nepse`) opens `EventSource('/api/events/stream?demo=0')`,
  renders `market.nepse.snapshot` in place (monotonic `version` guard), no full reload, no
  fake animation.

## Real validation (Phase 1–4, 16 — market CLOSED at run time)
3 genuine acquisitions + a 4-way concurrent burst against the live site:
- status CLOSED, freshness MARKET_CLOSED (honest), index 2,559.49, **345 securities** each,
  NABIL 552.00 — versions v1..v3, observed_at advances each run.
- **Single-flight (live):** 4 concurrent forced refreshes → version 3→4 (**delta 1**) =
  exactly one browser acquisition.
- Acquisition latency **min 20.3 s / median 21.5 s / max 25.8 s**.
- Browser child RSS **272 MB, 0.0 MB growth** across runs (no leak).
- 4 events published to the bus (versions [1,2,3,4]); payload **1201 bytes**.
- Cross-surface: Central Command / chat / voice all resolve the **same snapshot version**
  (NABIL 552.00) — Phases 10/11.
- Store audit: **md_bars = 0, md_quotes = 0**, live_market_snapshot + observation series
  written; NABIL series length grows with acquisitions (Phase 14).
- **Fields changed across the window: NONE →** reported honestly as
  `OPEN_SESSION_OBSERVED_NO_FIELD_CHANGE` because the market was closed (Sep 11 state
  frozen). No fabricated movement.

## Transitions (unit-proven)
OPEN→LIVE (as_of near now), LIVE→STALE on failure (last-good preserved, not fabricated),
OPEN→CLOSED→MARKET_CLOSED. Freshness never reports LIVE merely because a cached quote
exists.

## Browser lifecycle decision (Phase 17)
**Keep launch → read → teardown.** Measured: 0 MB RSS growth across repeated runs, clean
recovery, no lifecycle leaks. A persistent browser was NOT adopted — it adds leak/recovery
risk for no proven latency win at this cadence (the ~21 s cost is Angular render + full-
universe Filter, not process launch).

## Security / authority (reproven)
Official NEPSE domain only (seed + per-response `check_domain`); no broker/TMS/Meroshare
navigation, no cookie/token/password access, no XHR token replay, no CAPTCHA bypass, no
private-endpoint promotion, no arbitrary JS nav, **no downloads on the live path**, no order
UI. `insert_bar`/`INTO md_bars`/`ExecutionGateway.`/`place_order`/`portfolio_construction`/
`withdraw`/`leverage` absent from live+service+producer code (audited). md_bars=0,
md_quotes=0, orders=0, ExecutionGateway.execute=0, TG trade=0, portfolio writes=0.

## Tests
`tests/test_nepse_live_streaming_v1.py` **14** (OPEN→LIVE, single-flight, coalescing,
publish/compact payload, version increment, field-change, SSE-no-acquisition, cross-surface
consistency, stale, close, observation-series/no-md_bars, catalyst context, payload size,
authority+producer helper) + live v1 **18** = 32; focused/related regression **1045 passed
/ 0 failed**. Frozen `b771d761` + `4d685383` = **0 diffs**.

## Limitations
1. **Genuine market-OPEN LIVE not yet observed** — validation ran while NEPSE was CLOSED
   (opens 11:00 Asia/Kathmandu, Sun–Thu). OPEN→LIVE + real field-change are unit-proven and
   the live pipeline is proven; the genuine open-session field-change capture is pending an
   open session (run `scripts`/scratch validator during 11:00–15:00 NPT).
2. SSE delivery latency not separately instrumented over HTTP (bus fan-out + relay proven;
   HTTP frame timing not measured).
3. ~21 s/acquisition — *observed*, not real-time; cadence bounded accordingly.

## Verdict
Streaming architecture (one producer → cache → existing SSE → many consumers), single-
flight, compact fan-out, bounded cadence, all transitions, resource safety, cross-surface
consistency, security and zero authority are **proven live and by test**; the one open item
is a genuine market-OPEN LIVE field-change observation ⇒

**SAATHIOS_OPEN_SESSION_NEPSE_VALIDATION_AND_STREAMING_CERTIFIED_WITH_LIMITATIONS.**
Not frozen (freeze needs a real market-open acquisition with LIVE freshness).

## Exact next milestone
`M — OPEN_SESSION_LIVE_CAPTURE_AND_FREEZE`: during a real 11:00–15:00 NPT session, capture
genuine OPEN/LIVE snapshots with observed field changes (index/LTP/volume), confirm cadence
+ single-flight under the live producer, then freeze the LIVE_NEPSE_BROWSER_MARKET_DATA
baseline. (Do NOT start trading signals.)
